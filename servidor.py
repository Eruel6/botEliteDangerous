"""API que recebe os dados do cliente e mantém uma mensagem por instalação no Discord.

O estado (qual mensagem corresponde a qual instalação) fica em SQLite, porque o
plano gratuito do Render hiberna o serviço e o processo perde a memória.
"""

import asyncio
import datetime
import os
import secrets
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
API_TOKENS_BRUTO = os.getenv("API_TOKENS", "")
API_TOKEN = os.getenv("API_TOKEN")

TEMPO_FINALIZACAO_HORAS = 2
MENSAGENS_A_VARRER = 200
INTERVALO_VERIFICACAO_SEGUNDOS = 600
CHECK = "✅"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
banco = armazenamento.Armazenamento()


def carregar_tokens():
    """Mapa token -> nome de quem reporta.

    API_TOKENS traz uma linha "nome=token" por pessoa. API_TOKEN sozinho
    continua valendo como uma entrada sem nome, para o deploy atual não
    quebrar durante a transição.
    """
    tokens = {}
    for linha in API_TOKENS_BRUTO.splitlines():
        linha = linha.strip()
        if not linha or "=" not in linha:
            continue
        nome, token = linha.split("=", 1)
        if nome.strip() and token.strip():
            tokens[token.strip()] = nome.strip()
    if API_TOKEN:
        tokens.setdefault(API_TOKEN, "desconhecido")
    return tokens


def conferir_token(token):
    """Nome de quem enviou. 401 se o token não bate, 503 se não há nenhum."""
    tokens = carregar_tokens()
    if not tokens:
        raise HTTPException(
            status_code=503,
            detail="Servidor sem API_TOKENS configurado; endpoint desabilitado.",
        )
    for conhecido, nome in tokens.items():
        # compare_digest para o tempo de resposta não revelar quanto do token
        # está correto.
        if secrets.compare_digest(token or "", conhecido):
            return nome
    raise HTTPException(status_code=401, detail="Token inválido.")


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
        # client.user e message.author são objetos distintos para o mesmo bot;
        # o discord.py só os considera iguais pelo id.
        if mensagem.author.id != autor.id:
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


def esta_pronta(instalacao):
    """Obra sem material nenhum não conta como pronta: all([]) é True."""
    return bool(instalacao.materiais) and all(m.completo for m in instalacao.materiais)


def finalizar_se_pronta(banco_alvo, registro):
    """Marca finalizado só quando os materiais estão completos.

    Antes isto era incondicional depois de TEMPO_FINALIZACAO_HORAS, e
    'finalizado' acabava significando 'ninguém reportou nas últimas 2 horas'.
    O consolidado depende de 'finalizado' querer dizer 'pronta'.
    """
    if not esta_pronta(registro.instalacao):
        return False
    banco_alvo.marcar_finalizado(registro.instalacao.nome)
    return True


async def verificar_finalizacoes():
    while True:
        agora = datetime.datetime.now(datetime.timezone.utc)
        canal = client.get_channel(DISCORD_CHANNEL_ID)
        for registro in banco.listar(pendentes=True):
            horas = (agora - registro.ultima_atualizacao).total_seconds() / 3600
            if horas < TEMPO_FINALIZACAO_HORAS:
                continue
            if not esta_pronta(registro.instalacao):
                continue
            try:
                mensagem = await buscar_mensagem(canal, registro.message_id)
                if mensagem is not None:
                    await adicionar_reacao_check(mensagem, registro.instalacao.materiais)
                finalizar_se_pronta(banco, registro)
                print(f"{CHECK} Finalizado automaticamente: {registro.instalacao.nome}")
            except Exception as e:
                print(f"Erro ao finalizar {registro.instalacao.nome}: {e}")
        await asyncio.sleep(INTERVALO_VERIFICACAO_SEGUNDOS)


def total_fornecido(instalacao):
    return sum(m.fornecido for m in instalacao.materiais)


def chave_de(instalacao):
    """Identidade da obra: o MarketID quando existe, senão o nome.

    Os dois usos precisam concordar — um decide publicar ou ignorar, o outro
    decide qual mensagem apagar. Se divergirem, o servidor compara contra um
    registro e apaga a mensagem de outro.
    """
    return instalacao.market_id if instalacao.market_id is not None else instalacao.nome


def deve_publicar(instalacao):
    """Só publica relato estritamente mais completo que o guardado.

    O total fornecido só cresce ao longo de uma construção, então "maior
    total" é uma aproximação segura de "mais recente". Isso é o que impede
    N clientes reportando a mesma obra de virarem N apaga-e-reposta por
    minuto no canal.
    """
    anterior = banco.obter(chave_de(instalacao), nome=instalacao.nome)
    if anterior is None:
        return True
    return total_fornecido(instalacao) > total_fornecido(anterior.instalacao)


@app.post("/logdata")
async def receber_dados(request: Request, x_api_token: str = Header(default=None)):
    quem = conferir_token(x_api_token)

    if not client.is_ready():
        raise HTTPException(status_code=503, detail="Bot do Discord ainda não está pronto.")

    data = await request.json()
    nome_instalacao = data.get("instalacao")
    materiais = data.get("materiais")

    if not nome_instalacao or not isinstance(materiais, list):
        raise HTTPException(status_code=400, detail="Dados inválidos.")

    instalacao = ed_parser.instalacao_de_payload(
        nome_instalacao, materiais, market_id=data.get("market_id")
    )

    if not deve_publicar(instalacao):
        return JSONResponse(content={"status": "ignorado"})

    porcentagem = f"{instalacao.porcentagem:.1f}%"
    agora = datetime.datetime.now(datetime.timezone.utc)
    rodape = f"atualizado por {quem} às {agora.strftime('%H:%M')} UTC"
    msg_formatada = ed_parser.formatar_mensagem_discord(instalacao, porcentagem, rodape)

    canal = client.get_channel(DISCORD_CHANNEL_ID)

    # O Discord não deixa editar mensagem antiga do jeito que precisamos aqui,
    # então a anterior é apagada e uma nova é postada no lugar.
    anterior = banco.obter(chave_de(instalacao), nome=instalacao.nome)
    if anterior is not None:
        mensagem_antiga = await buscar_mensagem(canal, anterior.message_id)
        if mensagem_antiga is not None:
            try:
                await mensagem_antiga.delete()
            except Exception as e:
                print(f"Erro ao deletar mensagem anterior: {e}")

    nova_msg = await canal.send(msg_formatada)
    banco.salvar(instalacao, message_id=nova_msg.id, reportado_por=quem)
    await adicionar_reacao_check(nova_msg, instalacao.materiais)

    return JSONResponse(content={"status": "ok"})


@app.get("/health")
async def health():
    return {"discord_pronto": client.is_ready(), "instalacoes": len(banco.listar())}
