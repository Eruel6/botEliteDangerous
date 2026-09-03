"""API que recebe os dados do cliente e mantém uma mensagem por instalação no Discord.

O estado (qual mensagem corresponde a qual instalação) fica em SQLite, porque o
plano gratuito do Render hiberna o serviço e o processo perde a memória.
"""

import asyncio
import datetime
import os
from contextlib import asynccontextmanager

import discord
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

import armazenamento
import ed_parser

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
API_TOKEN = os.getenv("API_TOKEN")

TEMPO_FINALIZACAO_HORAS = 2
MENSAGENS_A_VARRER = 200
INTERVALO_VERIFICACAO_SEGUNDOS = 600
CHECK = "✅"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
banco = armazenamento.Armazenamento()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tarefas = [
        asyncio.create_task(client.start(DISCORD_BOT_TOKEN)),
        asyncio.create_task(verificar_finalizacoes()),
    ]
    try:
        yield
    finally:
        for tarefa in tarefas:
            tarefa.cancel()
        await client.close()
        await asyncio.gather(*tarefas, return_exceptions=True)


app = FastAPI(lifespan=lifespan)


@client.event
async def on_ready():
    print(f"Bot conectado como {client.user}")
    canal = client.get_channel(DISCORD_CHANNEL_ID)
    if canal is not None:
        try:
            await reconciliar_com_o_canal(canal, autor=client.user)
        except Exception as e:
            print(f"Erro ao reconstruir estado do canal: {e}")


def conferir_token(token):
    """401 se o token não bate; 503 se o servidor foi subido sem API_TOKEN."""
    if not API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Servidor sem API_TOKEN configurado; endpoint desabilitado.",
        )
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido.")


async def adicionar_reacao_check(mensagem, materiais):
    if all(m.completo for m in materiais):
        if CHECK not in [str(r.emoji) for r in mensagem.reactions]:
            await mensagem.add_reaction(CHECK)


async def buscar_mensagem(canal, message_id):
    """Recupera a mensagem pelo id guardado; None se ela não existe mais."""
    try:
        return await canal.fetch_message(message_id)
    except (discord.NotFound, discord.Forbidden):
        return None


async def reconciliar_com_o_canal(canal, autor):
    """Reconstrói o estado lendo as mensagens que o próprio bot já postou.

    O disco do Render é efêmero (não há disco persistente no plano gratuito),
    então o SQLite some a cada restart. O canal do Discord é a fonte de verdade
    que sobrevive: cada mensagem carrega o nome da instalação e a tabela.
    """
    recuperadas = 0
    async for mensagem in canal.history(limit=MENSAGENS_A_VARRER):
        if mensagem.author is not autor:
            continue
        nome = ed_parser.nome_na_mensagem(mensagem.content)
        if not nome or banco.obter(nome) is not None:
            continue
        materiais = ed_parser.materiais_na_mensagem(mensagem.content)
        instalacao = ed_parser.Instalacao(market_id=None, nome=nome, materiais=materiais)
        banco.salvar(instalacao, message_id=mensagem.id)
        recuperadas += 1
    if recuperadas:
        print(f"Estado reconstruído a partir do canal: {recuperadas} instalação(ões).")
    return recuperadas


async def verificar_finalizacoes():
    while True:
        agora = datetime.datetime.now(datetime.timezone.utc)
        canal = client.get_channel(DISCORD_CHANNEL_ID)
        for registro in banco.listar(pendentes=True):
            horas = (agora - registro.ultima_atualizacao).total_seconds() / 3600
            if horas < TEMPO_FINALIZACAO_HORAS:
                continue
            try:
                mensagem = await buscar_mensagem(canal, registro.message_id)
                if mensagem is not None:
                    await adicionar_reacao_check(mensagem, registro.instalacao.materiais)
                banco.marcar_finalizado(registro.instalacao.nome)
                print(f"{CHECK} Finalizado automaticamente: {registro.instalacao.nome}")
            except Exception as e:
                print(f"Erro ao finalizar {registro.instalacao.nome}: {e}")
        await asyncio.sleep(INTERVALO_VERIFICACAO_SEGUNDOS)


@app.post("/logdata")
async def receber_dados(request: Request, x_api_token: str = Header(default=None)):
    conferir_token(x_api_token)

    if not client.is_ready():
        raise HTTPException(status_code=503, detail="Bot do Discord ainda não está pronto.")

    data = await request.json()
    nome_instalacao = data.get("instalacao")
    materiais = data.get("materiais")

    if not nome_instalacao or not isinstance(materiais, list):
        raise HTTPException(status_code=400, detail="Dados inválidos.")

    instalacao = ed_parser.instalacao_de_payload(nome_instalacao, materiais)
    porcentagem = f"{instalacao.porcentagem:.1f}%"
    msg_formatada = ed_parser.formatar_mensagem_discord(instalacao, porcentagem)

    canal = client.get_channel(DISCORD_CHANNEL_ID)

    # O Discord não deixa editar mensagem antiga do jeito que precisamos aqui,
    # então a anterior é apagada e uma nova é postada no lugar.
    anterior = banco.obter(nome_instalacao)
    if anterior is not None:
        mensagem_antiga = await buscar_mensagem(canal, anterior.message_id)
        if mensagem_antiga is not None:
            try:
                await mensagem_antiga.delete()
            except Exception as e:
                print(f"Erro ao deletar mensagem anterior: {e}")

    nova_msg = await canal.send(msg_formatada)
    banco.salvar(instalacao, message_id=nova_msg.id)
    await adicionar_reacao_check(nova_msg, instalacao.materiais)

    return JSONResponse(content={"status": "ok"})


@app.get("/health")
async def health():
    return {"discord_pronto": client.is_ready(), "instalacoes": len(banco.listar())}
