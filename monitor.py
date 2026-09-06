"""O loop do cliente: lê o Journal e envia as instalações que mudaram."""

import collections
import datetime
import json
import time

import requests

import comandante
import compras
import ed_parser

INTERVALO_CHECAGEM = 60
TIMEOUT_SEGUNDOS = 30
LIMITE_DETALHE = 200

#: Resposta do servidor. ``status`` é None quando a requisição nem aconteceu.
Resposta = collections.namedtuple("Resposta", "status detalhe")


def payload_de(instalacao):
    return {
        "instalacao": instalacao.nome,
        "market_id": instalacao.market_id,
        "materiais": [
            {
                "Name_Localised": m.nome,
                "RequiredAmount": m.requerido,
                "ProvidedAmount": m.fornecido,
            }
            for m in instalacao.materiais
        ],
    }


def _resumir(texto):
    """Uma linha curta: o painel mostra um erro por linha de tabela."""
    texto = " ".join((texto or "").split())
    if len(texto) > LIMITE_DETALHE:
        texto = texto[:LIMITE_DETALHE] + "…"
    return texto


def _detalhe_da(resp):
    """O que o corpo da resposta explica sobre o status.

    Sem isso o painel mostrava só o número, e os dois 503 possíveis ficavam
    indistinguíveis: o bot do Discord ainda não pronto (o FastAPI responde
    ``{"detail": ...}``) e o edge do Render acordando o serviço hibernado
    (responde uma página HTML inteira, daí o corte em _resumir).
    """
    try:
        corpo = resp.json()
    except Exception:
        corpo = None
    if isinstance(corpo, dict) and isinstance(corpo.get("detail"), str):
        return _resumir(corpo["detail"])
    return _resumir(resp.text)


def _com_detalhe(prefixo, detalhe):
    return f"{prefixo} — {detalhe}" if detalhe else prefixo


def enviar_para_api(payload, config):
    try:
        resp = requests.post(
            config.api_url,
            json=payload,
            headers={"X-API-Token": config.api_token},
            timeout=TIMEOUT_SEGUNDOS,
        )
        return Resposta(resp.status_code, _detalhe_da(resp))
    except Exception as e:
        return Resposta(None, _resumir(f"{type(e).__name__}: {e}"))


def url_do_comandante(api_url):
    """Deriva do API_URL em vez de pedir uma linha nova no config.txt.

    Quem já instalou o cliente tem um config.txt apontando para /logdata;
    exigir uma chave nova quebraria essas instalações no dia do deploy.
    """
    return api_url.rsplit("/", 1)[0] + "/comandante"


def payload_do_comandante(retrato):
    return {
        "carga": [
            {"material": material, "quantidade": quantidade}
            for material, quantidade in retrato.carga.items()
        ],
        "alvo": {
            "market_id": retrato.alvo_market_id,
            "sistema": retrato.alvo_sistema,
        },
        "entregas": [
            {
                "quando": e.quando,
                "market_id": e.market_id,
                "material": e.material,
                "quantidade": e.quantidade,
            }
            for e in retrato.entregas
        ],
    }


def enviar_comandante(retrato, config):
    try:
        resp = requests.post(
            url_do_comandante(config.api_url),
            json=payload_do_comandante(retrato),
            headers={"X-API-Token": config.api_token},
            timeout=TIMEOUT_SEGUNDOS,
        )
        return Resposta(resp.status_code, _detalhe_da(resp))
    except Exception as e:
        return Resposta(None, _resumir(f"{type(e).__name__}: {e}"))


def sugestao_para_dicionario(sugestao):
    return {
        "material": sugestao.material,
        "faltando": sugestao.faltando,
        "consultavel": sugestao.consultavel,
        "desatualizado": sugestao.desatualizado,
        "estacoes": [
            {
                "nome": e.nome,
                "sistema": e.sistema,
                "distancia_ly": e.distancia_ly,
                "distancia_ls": e.distancia_ls,
                "estoque": e.estoque,
                "preco": e.preco,
                "carrier": e.carrier,
            }
            for e in sugestao.estacoes
        ],
    }


def sincronizar(
    log_path, memoria, config, estado_cliente,
    enviar=enviar_para_api, enviar_retrato=None, buscador=None,
):
    """Envia cada instalação cujo estado mudou e ainda não foi aceita.

    A assinatura só é gravada depois de um envio bem-sucedido, então um envio
    que falhou é naturalmente refeito no ciclo seguinte.
    """
    instalacoes = ed_parser.extrair_instalacoes(log_path)
    estado_cliente.registrar_leitura(log_path, instalacoes)

    for instalacao in instalacoes:
        if instalacao.nome == ed_parser.NOME_DESCONHECIDO or not instalacao.materiais:
            continue

        payload = payload_de(instalacao)
        assinatura = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        if memoria.get(instalacao.nome) == assinatura:
            continue

        resposta = enviar(payload, config)
        estado_cliente.registrar_envio(resposta.status or 0)

        if resposta.status is not None and 200 <= resposta.status < 300:
            memoria[instalacao.nome] = assinatura
        elif resposta.status is None:
            estado_cliente.registrar_erro(
                _com_detalhe(f"{instalacao.nome}: falha de rede ao enviar", resposta.detalhe)
            )
        else:
            estado_cliente.registrar_erro(
                _com_detalhe(
                    f"{instalacao.nome}: servidor respondeu {resposta.status}",
                    resposta.detalhe,
                )
            )

    # Padrão None e não a função real: assim nenhum teste que chame sincronizar
    # sem se importar com o retrato acaba fazendo requisição de rede. Quem manda
    # de verdade é o rodar().
    if enviar_retrato is not None:
        retrato = comandante.montar_retrato(log_path)
        resposta = enviar_retrato(retrato, config)
        if resposta.status is None or not (200 <= resposta.status < 300):
            estado_cliente.registrar_erro(
                _com_detalhe(f"comandante: envio recusado ({resposta.status})", resposta.detalhe)
            )

    if buscador is not None:
        try:
            _, sistema = comandante.alvo_atual(log_path)
            agora = datetime.datetime.now(datetime.timezone.utc)
            estado_cliente.registrar_compras(
                [sugestao_para_dicionario(s)
                 for s in buscador.sugestoes(instalacoes, sistema, agora)]
            )
        except Exception as e:
            # A consulta é acessória: o relato das obras não pode parar por causa
            # de uma API de terceiro.
            estado_cliente.registrar_erro(f"compras: {e}")


def rodar(config, estado_cliente, intervalo=INTERVALO_CHECAGEM):
    memoria = {}
    buscador = None
    while True:
        log_path = ed_parser.encontrar_log_mais_recente()
        if log_path:
            nave, capacidade = ed_parser.nave_atual(log_path)
            if capacidade:
                if buscador is None:
                    buscador = compras.Buscador(nave, capacidade)
                else:
                    # Trocar de nave no meio da sessão muda o pad exigido e o
                    # porão. O cache continua válido: ele guarda a resposta da
                    # API, e os filtros são aplicados na leitura.
                    buscador.nave = nave
                    buscador.capacidade = capacidade
            try:
                sincronizar(
                    log_path, memoria, config, estado_cliente,
                    enviar_retrato=enviar_comandante, buscador=buscador,
                )
            except Exception as e:
                estado_cliente.registrar_erro(f"erro ao processar o log: {e}")
        else:
            estado_cliente.registrar_erro("Nenhum Journal encontrado na pasta do jogo.")
        time.sleep(intervalo)
