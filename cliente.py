# cliente.py

import os
import json
import glob
import time
import requests
from dotenv import load_dotenv

load_dotenv()
API_ADRESS = os.getenv("API_ADRESS")

API_URL = f"https://{API_ADRESS}.onrender.com/logdata" 
FINALIZACAO_MINIMA_ENTREGUE = 0.8
INTERVALO_CHECAGEM = 60  

def obter_log_mais_recente():
    pasta_logs = os.path.expanduser(r"~\Saved Games\Frontier Developments\Elite Dangerous")
    arquivos = glob.glob(os.path.join(pasta_logs, "Journal.*.log"))
    if not arquivos:
        return None
    return max(arquivos, key=os.path.getmtime)

def extrair_ultima_instalacao_e_materiais(log_path):
    with open(log_path, 'r', encoding='utf-8') as f:
        linhas = f.readlines()

    approaches = []
    listas = []

    for i, line in enumerate(linhas):
        try:
            dado = json.loads(line)
            if dado.get("event") == "ApproachSettlement" and "Planetary Construction Site:" in dado.get("Name", ""):
                approaches.append((i, dado.get("Name")))

            elif isinstance(dado, list):
                if all(k in item for item in dado for k in ("Name_Localised", "RequiredAmount", "ProvidedAmount")):
                    listas.append((i, dado))
            elif isinstance(dado, dict):
                for v in dado.values():
                    if isinstance(v, list) and all(k in item for item in v for k in ("Name_Localised", "RequiredAmount", "ProvidedAmount")):
                        listas.append((i, v))
        except:
            continue

    if not listas:
        return None, None

    idx_lista, materiais = listas[-1]
    nome_instalacao = "Desconhecida"
    for idx, nome in reversed(approaches):
        if idx < idx_lista:
            nome_instalacao = nome
            break

    return nome_instalacao, materiais

def enviar_para_api(instalacao, materiais):
    payload = {
        "instalacao": instalacao,
        "materiais": materiais
    }
    try:
        resp = requests.post(API_URL, json=payload)
        print(f"[API] {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar dados: {e}")

if __name__ == "__main__":
    print("Iniciando monitoramento de log...")
    ultimo_envio = ""

    while True:
        log_path = obter_log_mais_recente()
        if log_path:
            nome, materiais = extrair_ultima_instalacao_e_materiais(log_path)
            if nome and materiais:
                conteudo_atual = json.dumps({"instalacao": nome, "materiais": materiais}, sort_keys=True)
                if conteudo_atual != ultimo_envio:
                    enviar_para_api(nome, materiais)
                    ultimo_envio = conteudo_atual
        time.sleep(INTERVALO_CHECAGEM)
