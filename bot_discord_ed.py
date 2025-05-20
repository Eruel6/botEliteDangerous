import discord
import asyncio
import os
import json
from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CANAL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
LOG_PATH = os.getenv("LOG_FILE")

intents = discord.Intents.default()
client = discord.Client(intents=intents)

def extrair_ultimas_instalacoes(log_path):
    with open(log_path, 'r', encoding='utf-8') as f:
        log_lines = f.readlines()

    ultimas_por_instalacao = {}

    for line_number, line in enumerate(log_lines):
        try:
            registro = json.loads(line)
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

    return list(ultimas_por_instalacao.items())

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

async def adicionar_reacao_check(mensagem, materiais):
    if all(item["ProvidedAmount"] >= item["RequiredAmount"] for item in materiais):
        reacoes = [str(reacao.emoji) async for reacao in mensagem.reactions]
        if "✅" not in reacoes:
            try:
                await mensagem.add_reaction("✅")
            except discord.errors.Forbidden:
                print("⚠️ Sem permissão para adicionar reações.")

@client.event
async def on_ready():
    print(f"🤖 Bot conectado como {client.user}")
    asyncio.create_task(enviar_atualizacoes())

async def enviar_atualizacoes():
    await client.wait_until_ready()
    canal = client.get_channel(CANAL_ID)

    mensagens_enviadas = {}  # {nome_instalacao: (mensagem_obj, ultimo_conteudo)}

    while not client.is_closed():
        try:
            instalacoes = extrair_ultimas_instalacoes(LOG_PATH)

            for nome_instalacao, materiais in instalacoes:
                if nome_instalacao == "Desconhecida":
                    continue

                novo_conteudo = formatar_mensagem(nome_instalacao, materiais)

                if nome_instalacao in mensagens_enviadas:
                    mensagem, ultimo_conteudo = mensagens_enviadas[nome_instalacao]

                    if novo_conteudo != ultimo_conteudo:
                        try:
                            await mensagem.edit(content=novo_conteudo)
                            mensagens_enviadas[nome_instalacao] = (mensagem, novo_conteudo)
                            await adicionar_reacao_check(mensagem, materiais)
                        except discord.errors.NotFound:
                            nova_msg = await canal.send(novo_conteudo)
                            mensagens_enviadas[nome_instalacao] = (nova_msg, novo_conteudo)
                            await adicionar_reacao_check(nova_msg, materiais)
                else:
                    nova_msg = await canal.send(novo_conteudo)
                    mensagens_enviadas[nome_instalacao] = (nova_msg, novo_conteudo)
                    await adicionar_reacao_check(nova_msg, materiais)

        except Exception as e:
            await canal.send(f"❌ Erro ao processar log: {str(e)}")

        await asyncio.sleep(180)  # Aguarda 3 minutos

def main():
    client.run(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
