import discord
import os
import asyncio
import datetime
from datetime import timezone, timedelta
from flask import Flask
from threading import Thread
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# --- KEEP ALIVE ---
app = Flask('')

@app.route('/')
def home():
    return "PowerNiver bot está rodando! 🎉"

def keep_alive():
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8080}).start()


# --- DISCORD BOT ---

MONGO_URI = os.getenv("MONGO_URI")

db_client = None
db_collection_aniversarios = None
db_collection_config = None

def connect_to_mongodb():
    global db_client, db_collection_aniversarios, db_collection_config
    try:
        db_client = MongoClient(MONGO_URI)
        db_client.admin.command('ping')
        db = db_client["powerniver_db"]
        db_collection_aniversarios = db["aniversarios"]
        db_collection_config = db["config"]
        print("✅ MongoDB conectado")
        return True
    except Exception as e:
        print(f"❌ Erro MongoDB: {e}")
        return False

connect_to_mongodb()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

def criar_embed(titulo, descricao, cor=discord.Color.purple()):
    return discord.Embed(title=titulo, description=descricao, color=cor)

def chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# ---------- EVENTOS ----------
@client.event
async def on_ready():
    print(f'✅ Logado como {client.user}')


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # ----- ping -----
    if message.content == "p!ping":
        await message.channel.send(embed=criar_embed("Pong", "pong ✅", discord.Color.green()))

    # ----- registrar aniversário -----
    if message.content.startswith("p!aniversario"):
        partes = message.content.split()

        if len(partes) != 2:
            await message.channel.send(embed=criar_embed("Erro", "Use: p!aniversario DD/MM", discord.Color.red()))
            return

        data = partes[1]

        try:
            dia, mes = map(int, data.split("/"))
        except:
            await message.channel.send(embed=criar_embed("Erro", "Data inválida", discord.Color.red()))
            return

        db_collection_aniversarios.update_one(
            {"_id": str(message.author.id)},
            {"$set": {"nome": message.author.display_name, "data": data}},
            upsert=True
        )

        await message.channel.send(embed=criar_embed("Sucesso", "Aniversário salvo 🎉", discord.Color.green()))

    # =========================
    # ✅ COMANDO CORRIGIDO AQUI
    # =========================
    if message.content.startswith("p!aniversariantes"):

        try:
            aniversarios = {d['_id']: d for d in db_collection_aniversarios.find({})}
        except Exception as e:
            await message.channel.send(embed=criar_embed("Erro", f"DB error: {e}", discord.Color.red()))
            return

        lista = []

        for uid, info in aniversarios.items():
            try:
                membro = await message.guild.fetch_member(int(uid))
            except:
                membro = None

            if membro:
                lista.append({
                    "nome": membro.display_name,
                    "data": info.get("data", "??/??")
                })

        if not lista:
            await message.channel.send(embed=criar_embed(
                "Lista", "📭 Nenhum aniversário encontrado.", discord.Color.orange()))
            return

        lista.sort(key=lambda x: (int(x['data'][3:]), int(x['data'][:2])))

        texto = ""
        for pessoa in lista:
            texto += f"🎂 **{pessoa['nome']}** - {pessoa['data']}\n"

        await message.channel.send(embed=criar_embed(
            "📅 Aniversariantes", texto, discord.Color.purple()))

# ---------- EXECUÇÃO ----------
keep_alive()
client.run(os.getenv("DISCORD_TOKEN"))
