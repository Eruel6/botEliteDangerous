# servidor.py

import os
import json
import asyncio
import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import discord
from dotenv import load_dotenv

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
FINALIZACAO_MINIMA_ENTREGUE = 0.8
TEMPO_FINALIZACAO_HORAS = 2

app = FastAPI()

intents = discord.Intents.default()
client = discord.Client(intents=intents)
loop = asyncio.get_event_loop()

# Novo rastreio completo com timestamps e status
rastreio_instalacoes = {}  # {nome_instalacao: {mensagem, materiais, ultima_atualizacao, finalizado}}

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(client.start(DISCORD_BOT_TOKEN))
    asyncio.create_task(verificar_finalizacoes())

# Formata a mensagem enviada ao Discord
def formatar_mensagem(nome_instalacao, materiais):
    linhas = [f"\ud83d\udccd **Materiais para instalação:** `{nome_instalacao}`\n"]
    linhas.append("```")
    linhas.append(f"{'Material':<25} | {'Req.':>5} | {'Fornec.':>7} | {'Faltam':>6}")
    linhas.append("-" * 52)
    for m in materiais:
        nome = m.get("Name_Localised", "?")
        req = m.get("RequiredAmount", 0)
        prov = m.get("ProvidedAmount", 0)
        faltando = req - prov
        linhas.append(f"{nome:<25} | {req:>5} | {prov:>7} | {faltando:>6}")
    linhas.append("```")
    return "\n".join(linhas)

# Adiciona check na mensagem se todos os materiais foram entregues
async def adicionar_reacao_check(mensagem, materiais):
    if all(item["ProvidedAmount"] >= item["RequiredAmount"] for item in materiais):
        reacoes = [str(r.emoji) async for r in mensagem.reactions]
        if "\u2705" not in reacoes:
            await mensagem.add_reaction("\u2705")

# Verifica se deve marcar a instalação como finalizada após 2h de inatividade
async def verificar_finalizacoes():
    while True:
        agora = datetime.datetime.utcnow()
        for nome, dados in list(rastreio_instalacoes.items()):
            if not dados["finalizado"]:
                diff = agora - dados["ultima_atualizacao"]
                horas = diff.total_seconds() / 3600
                if horas >= TEMPO_FINALIZACAO_HORAS:
                    try:
                        await adicionar_reacao_check(dados["mensagem"], dados["materiais"])
                        dados["finalizado"] = True
                        print(f"\u2705 Finalizado automaticamente: {nome}")
                    except Exception as e:
                        print(f"Erro ao finalizar {nome}: {e}")
        await asyncio.sleep(600)  # Verifica a cada 10 minutos

# Recebe dados dos clientes (jogadores)
@app.post("/logdata")
async def receber_dados(request: Request):
    if not client.is_ready():
        raise HTTPException(status_code=503, detail="Bot do Discord ainda não está pronto.")

    data = await request.json()
    nome_instalacao = data.get("instalacao")
    materiais = data.get("materiais")

    if not nome_instalacao or not isinstance(materiais, list):
        raise HTTPException(status_code=400, detail="Dados inválidos.")

    canal = client.get_channel(DISCORD_CHANNEL_ID)
    msg_formatada = formatar_mensagem(nome_instalacao, materiais)

    if nome_instalacao in rastreio_instalacoes:
        dados = rastreio_instalacoes[nome_instalacao]
        conteudo_antigo = formatar_mensagem(nome_instalacao, dados["materiais"])

        if msg_formatada != conteudo_antigo:
            try:
                await dados["mensagem"].edit(content=msg_formatada)
                rastreio_instalacoes[nome_instalacao]["materiais"] = materiais
                rastreio_instalacoes[nome_instalacao]["ultima_atualizacao"] = datetime.datetime.utcnow()
            except Exception as e:
                print(f"Erro ao editar mensagem: {e}")
    else:
        nova_msg = await canal.send(msg_formatada)
        rastreio_instalacoes[nome_instalacao] = {
            "mensagem": nova_msg,
            "materiais": materiais,
            "ultima_atualizacao": datetime.datetime.utcnow(),
            "finalizado": False
        }

    return JSONResponse(content={"status": "ok"})