"""Bot Discord que lê o Journal local e mantém uma mensagem por instalação.

Geração anterior à arquitetura cliente/servidor: roda tudo na máquina do jogador.
Usa o Journal apontado por LOG_FILE no .env.
"""

import asyncio
import os

import discord
from dotenv import load_dotenv

import ed_parser

# Mínimo de materiais entregues para considerar a instalação finalizada (80%).
FINALIZACAO_MINIMA_ENTREGUE = 0.8
INTERVALO_SEGUNDOS = 180

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CANAL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
LOG_PATH = os.getenv("LOG_FILE")

intents = discord.Intents.default()
client = discord.Client(intents=intents)


def obter_log():
    return LOG_PATH


@client.event
async def on_ready():
    print(f"🤖 Bot conectado como {client.user}")
    asyncio.create_task(enviar_atualizacoes())


async def enviar_atualizacoes():
    await client.wait_until_ready()
    canal = client.get_channel(CANAL_ID)
    mensagens_enviadas = {}  # nome -> (mensagem, instalacao)

    while not client.is_closed():
        try:
            log_path = obter_log()
            instalacoes = ed_parser.extrair_instalacoes(log_path)
            sites_ativos = ed_parser.sinais_de_construcao(log_path)

            for instalacao in instalacoes:
                if instalacao.nome == ed_parser.NOME_DESCONHECIDO:
                    continue

                novo_conteudo = ed_parser.formatar_mensagem_discord(instalacao)

                if instalacao.nome in mensagens_enviadas:
                    mensagem, anterior = mensagens_enviadas[instalacao.nome]
                    if novo_conteudo != ed_parser.formatar_mensagem_discord(anterior):
                        try:
                            await mensagem.edit(content=novo_conteudo)
                        except discord.errors.NotFound:
                            mensagem = await canal.send(novo_conteudo)
                    mensagens_enviadas[instalacao.nome] = (mensagem, instalacao)
                else:
                    nova_msg = await canal.send(novo_conteudo)
                    mensagens_enviadas[instalacao.nome] = (nova_msg, instalacao)

            # Instalações que sumiram da lista de construction sites: marcar finalizadas.
            for nome in list(mensagens_enviadas):
                if nome.startswith(ed_parser.PREFIXO_CONSTRUCAO) and nome not in sites_ativos:
                    mensagem, instalacao = mensagens_enviadas[nome]
                    total = len(instalacao.materiais)
                    if total == 0:
                        continue

                    entregues = sum(1 for m in instalacao.materiais if m.completo)
                    if entregues / total >= FINALIZACAO_MINIMA_ENTREGUE:
                        try:
                            await mensagem.add_reaction("✅")
                        except discord.errors.Forbidden:
                            print("⚠️ Sem permissão para adicionar reação final.")
                        del mensagens_enviadas[nome]

        except Exception as e:
            await canal.send(f"❌ Erro ao processar log: {str(e)}")

        await asyncio.sleep(INTERVALO_SEGUNDOS)


def main():
    client.run(TOKEN)


if __name__ == "__main__":
    main()
