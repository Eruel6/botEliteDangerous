"""O loop do cliente: lê o Journal e envia as instalações que mudaram."""

import collections
import json
import time

import requests

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


def sincronizar(log_path, memoria, config, estado_cliente, enviar=enviar_para_api):
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


def rodar(config, estado_cliente, intervalo=INTERVALO_CHECAGEM):
    memoria = {}
    while True:
        log_path = ed_parser.encontrar_log_mais_recente()
        if log_path:
            try:
                sincronizar(log_path, memoria, config, estado_cliente)
            except Exception as e:
                estado_cliente.registrar_erro(f"erro ao processar o log: {e}")
        else:
            estado_cliente.registrar_erro("Nenhum Journal encontrado na pasta do jogo.")
        time.sleep(intervalo)
