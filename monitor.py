"""O loop do cliente: lê o Journal e envia as instalações que mudaram."""

import json
import time

import requests

import ed_parser

INTERVALO_CHECAGEM = 60
TIMEOUT_SEGUNDOS = 30


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


def enviar_para_api(payload, config):
    """Status HTTP da resposta, ou None se a requisição nem aconteceu."""
    try:
        resp = requests.post(
            config.api_url,
            json=payload,
            headers={"X-API-Token": config.api_token},
            timeout=TIMEOUT_SEGUNDOS,
        )
        return resp.status_code
    except Exception:
        return None


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

        status = enviar(payload, config)
        estado_cliente.registrar_envio(status or 0)

        if status is not None and 200 <= status < 300:
            memoria[instalacao.nome] = assinatura
        elif status is None:
            estado_cliente.registrar_erro(f"{instalacao.nome}: falha de rede ao enviar")
        else:
            estado_cliente.registrar_erro(f"{instalacao.nome}: servidor respondeu {status}")


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
