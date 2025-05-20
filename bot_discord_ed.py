import discord
import asyncio
import os
from dotenv import load_dotenv
from parserMaterials import extrair_materiais_construcao

# Carregar .env
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CANAL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
LOG_PATH = os.getenv("LOG_FILE")

intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"🤖 Bot conectado como {client.user}")
    asyncio.create_task(enviar_atualizacao())  # inicia a tarefa em background

async def enviar_atualizacao():
    await client.wait_until_ready()
    canal = client.get_channel(CANAL_ID)

    while not client.is_closed():
        materiais, nome_instalacao = extrair_materiais_construcao(LOG_PATH)

        if materiais:
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
            msg = "\n".join(linhas)
        else:
            msg = "⚠️ Nenhum dado de materiais de construção encontrado."

        await canal.send(msg)
        await asyncio.sleep(180)

def main():
    client.run(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
