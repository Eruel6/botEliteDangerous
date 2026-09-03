"""Roda na máquina do jogador: lê o Journal e envia as instalações para a API."""

import json
import os
import time

import requests
from dotenv import load_dotenv

import ed_parser

load_dotenv()
API_ADRESS = os.getenv("API_ADRESS")
API_TOKEN = os.getenv("API_TOKEN")
API_URL = f"https://{API_ADRESS}.onrender.com/logdata"
INTERVALO_CHECAGEM = 60
TIMEOUT_SEGUNDOS = 30


def payload_de(instalacao):
    return {
        "instalacao": instalacao.nome,
        "materiais": [
            {
                "Name_Localised": m.nome,
                "RequiredAmount": m.requerido,
                "ProvidedAmount": m.fornecido,
            }
            for m in instalacao.materiais
        ],
    }


def enviar_para_api(payload):
    try:
        resp = requests.post(
            API_URL,
            json=payload,
            headers={"X-API-Token": API_TOKEN},
            timeout=TIMEOUT_SEGUNDOS,
        )
        print(f"[API] {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar dados: {e}")


def sincronizar(log_path, memoria, enviar=enviar_para_api):
    """Envia cada instalação cujo estado mudou desde a última vez.

    ``memoria`` mapeia nome -> assinatura do último envio e é atualizada aqui.
    """
    for instalacao in ed_parser.extrair_instalacoes(log_path):
        if instalacao.nome == ed_parser.NOME_DESCONHECIDO or not instalacao.materiais:
            continue
        payload = payload_de(instalacao)
        assinatura = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        if memoria.get(instalacao.nome) == assinatura:
            continue
        enviar(payload)
        memoria[instalacao.nome] = assinatura


def main():
    print("Iniciando monitoramento de log...")
    memoria = {}
    while True:
        log_path = ed_parser.encontrar_log_mais_recente()
        if log_path:
            sincronizar(log_path, memoria)
        time.sleep(INTERVALO_CHECAGEM)


if __name__ == "__main__":
    main()
