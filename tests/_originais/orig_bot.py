# import discord
import asyncio
import os
import json
from dotenv import load_dotenv

# Configuração: mínimo de materiais entregues para considerar finalização (ex: 80%)
FINALIZACAO_MINIMA_ENTREGUE = 0.8  # 80%

# Carregar variáveis do .env

TOKEN = None
CANAL_ID = None
LOG_PATH = None

# intents = discord.Intents.default()
# client = discord.Client(intents=intents)

def extrair_ultimas_instalacoes(log_path):
    with open(log_path, 'r', encoding='utf-8') as f:
        log_lines = f.readlines()

    ultimas_por_instalacao = {}
    eventos = []

    for line_number, line in enumerate(log_lines):
        try:
            registro = json.loads(line)
            eventos.append(registro)

            listas_validas = []

            if isinstance(registro, list) and all(
                isinstance(item, dict) and
                'Name_Localised' in item and
                'RequiredAmount' in item and
                'ProvidedAmount' in item
                for item in registro
            ):
                listas_validas = [registro]

            elif isinstance(registro, dict):
                listas_validas = [
                    valor for valor in registro.values()
                    if isinstance(valor, list) and all(
                        isinstance(item, dict) and
                        'Name_Localised' in item and
                        'RequiredAmount' in item and
                        'ProvidedAmount' in item
                        for item in valor
                    )
                ]

            for lista in listas_validas:
                nome_instalacao = "Desconhecida"
                for i in range(line_number, -1, -1):
                    try:
                        reg = json.loads(log_lines[i])
                        if reg.get("event") == "ApproachSettlement":
                            nome = reg.get("Name", "")
                            if nome.startswith("Planetary Construction Site:"):
                                nome_instalacao = nome
                                break
                    except json.JSONDecodeError:
                        continue

                ultimas_por_instalacao[nome_instalacao] = lista

        except json.JSONDecodeError:
            continue

    return list(ultimas_por_instalacao.items()), eventos

def formatar_mensagem(nome_instalacao, materiais):
    linhas = [f"📍 **Materiais para instalação:** `{nome_instalacao}`\n"]
    linhas.append("```")
    linhas.append(f"{'Material':<25} | {'Req.':>5} | {'Fornec.':>7} | {'Faltam':>6}")
    linhas.append("-" * 52)

    for m in materiais:
        if all(k in m for k in ("Name_Localised", "RequiredAmount", "ProvidedAmount")):
            nome = m["Name_Localised"]
            req = m["RequiredAmount"]
            prov = m["ProvidedAmount"]
            faltando = req - prov
            linhas.append(f"{nome:<25} | {req:>5} | {prov:>7} | {faltando:>6}")
    linhas.append("```")
    return "\n".join(linhas)

# @client.event


def main():
    client.run(TOKEN)

