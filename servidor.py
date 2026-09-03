# servidor.py

import os
import asyncio
import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import discord
from dotenv import load_dotenv

import ed_parser

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
FINALIZACAO_MINIMA_ENTREGUE = 0.8
TEMPO_FINALIZACAO_HORAS = 2

app = FastAPI()

intents = discord.Intents.default()
client = discord.Client(intents=intents)
loop = asyncio.get_event_loop()

rastreio_instalacoes = {} 

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(client.start(DISCORD_BOT_TOKEN))
    asyncio.create_task(verificar_finalizacoes())


async def adicionar_reacao_check(mensagem, materiais):
    if all(m.completo for m in materiais):
        reacoes = [str(r.emoji) async for r in mensagem.reactions]
        if "\u2705" not in reacoes:
            await mensagem.add_reaction("\u2705")

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
        await asyncio.sleep(600)



@app.post("/logdata")
async def receber_dados(request: Request):
    if not client.is_ready():
        raise HTTPException(status_code=503, detail="Bot do Discord ainda não está pronto.")

    data = await request.json()
    nome_instalacao = data.get("instalacao")
    materiais = data.get("materiais")

    if not nome_instalacao or not isinstance(materiais, list):
        raise HTTPException(status_code=400, detail="Dados inválidos.")

    instalacao = ed_parser.instalacao_de_payload(nome_instalacao, materiais)
    porcentagem_formatada = f"{instalacao.porcentagem:.1f}%"

    canal = client.get_channel(DISCORD_CHANNEL_ID)
    msg_formatada = ed_parser.formatar_mensagem_discord(instalacao, porcentagem_formatada)


    if nome_instalacao in rastreio_instalacoes:
        dados = rastreio_instalacoes[nome_instalacao]
        try:
            await dados["mensagem"].delete()
        except Exception as e:
            print(f"Erro ao deletar mensagem anterior: {e}")

    nova_msg = await canal.send(msg_formatada)
    rastreio_instalacoes[nome_instalacao] = {
        "mensagem": nova_msg,
        "materiais": instalacao.materiais,
        "ultima_atualizacao": datetime.datetime.utcnow(),
        "finalizado": False
    }
    await adicionar_reacao_check(nova_msg, instalacao.materiais)

    return JSONResponse(content={"status": "ok"})
