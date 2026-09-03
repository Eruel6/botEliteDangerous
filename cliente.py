"""Roda na máquina do jogador: lê o Journal e envia a instalação atual para a API."""

import json
import os
import time

import requests
from dotenv import load_dotenv

import ed_parser

load_dotenv()
API_ADRESS = os.getenv("API_ADRESS")
API_URL = f"https://{API_ADRESS}.onrender.com/logdata"
INTERVALO_CHECAGEM = 60


def enviar_para_api(instalacao):
    payload = {
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
    try:
        resp = requests.post(API_URL, json=payload)
        print(f"[API] {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar dados: {e}")
    return payload


def main():
    print("Iniciando monitoramento de log...")
    ultimo_envio = ""

    while True:
        log_path = ed_parser.encontrar_log_mais_recente()
        if log_path:
            instalacao = ed_parser.ultima_instalacao(log_path)
            if instalacao and instalacao.materiais:
                atual = json.dumps(
                    {
                        "instalacao": instalacao.nome,
                        "materiais": [
                            (m.nome, m.requerido, m.fornecido) for m in instalacao.materiais
                        ],
                    },
                    sort_keys=True,
                )
                if atual != ultimo_envio:
                    enviar_para_api(instalacao)
                    ultimo_envio = atual
        time.sleep(INTERVALO_CHECAGEM)


if __name__ == "__main__":
    main()
