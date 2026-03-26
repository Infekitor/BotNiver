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
print(f"DEBUG: MONGO_URI lido: {MONGO_URI}")

db_client = None
db_collection_aniversarios = None
db_collection_config = None

def connect_to_mongodb():
    global db_client, db_collection_aniversarios, db_collection_config
    try:
        if not MONGO_URI:
            print("❌ Variável MONGO_URI não configurada!")
            return False
        db_client = MongoClient(MONGO_URI)
        db_client.admin.command('ping')
        print("✅ Conectado ao MongoDB Atlas!")
        db = db_client["powerniver_db"]
        db_collection_aniversarios = db["aniversarios"]
        db_collection_config = db["config"]
        return True
    except ConnectionFailure as e:
        print(f"❌ Falha ao conectar ao MongoDB: {e}")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return False

connect_to_mongodb()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

client = discord.Client(intents=intents,
                        member_cache_flags=discord.MemberCacheFlags.all())


# ---------- UTILIDADES ----------
def criar_embed(titulo, descricao, cor=discord.Color.purple()):
    return discord.Embed(title=titulo, description=descricao, color=cor)


def chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# ---------- TAREFA DIÁRIA ----------
async def checar_aniversarios():
    await client.wait_until_ready()
    print("Iniciando checagem de aniversários...")

    while not client.is_closed():
        if db_client is None:
            if not connect_to_mongodb():
                await asyncio.sleep(60)
                continue

        fuso_br = timezone(timedelta(hours=-3))
        hoje = datetime.datetime.now(fuso_br)
        data_hoje = hoje.strftime("%d/%m")

        try:
            aniversarios = {d['_id']: d for d in db_collection_aniversarios.find({})}
            configuracoes = {d['_id']: d for d in db_collection_config.find({})}
        except Exception:
            continue

        for guild in client.guilds:
            gid = str(guild.id)
            conf = configuracoes.get(gid, {})
            canal_id = conf.get("channel_id")

            if not canal_id:
                continue

            canal = client.get_channel(int(canal_id))
            if not canal:
                continue

            for uid, info in aniversarios.items():
                member = guild.get_member(int(uid))
                if member and info["data"] == data_hoje:
                    embed = discord.Embed(
                        title=f"🎉 Feliz Aniversário, {info['nome']}!",
                        description=f"Parabéns {member.mention}! 🎂",
                        color=discord.Color.gold()
                    )
                    await canal.send(embed=embed)

        await asyncio.sleep(3600)


# ---------- EVENTOS ----------
@client.event
async def on_ready():
    print(f'✅ Bot conectado como {client.user}')
    client.loop.create_task(checar_aniversarios())


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    if message.content == "p!ping":
        await message.channel.send(embed=criar_embed(
            "Pong", "pong ✅", discord.Color.green()))

    if message.content.startswith("p!aniversario"):
        partes = message.content.split()
        if len(partes) != 2:
            await message.channel.send(embed=criar_embed(
                "Erro", "Use: p!aniversario DD/MM", discord.Color.red()))
            return

        data = partes[1]

        db_collection_aniversarios.update_one(
            {"_id": str(message.author.id)},
            {"$set": {"nome": message.author.display_name, "data": data}},
            upsert=True
        )

        await message.channel.send(embed=criar_embed(
            "Salvo", "🎉 Aniversário registrado!", discord.Color.green()))

    # 🔥 COMANDO CORRIGIDO
    if message.content.startswith("p!aniversariantes"):

        aniversarios = {d['_id']: d for d in db_collection_aniversarios.find({})}
        lista = []

        for uid, info in aniversarios.items():
            try:
                membro = await message.guild.fetch_member(int(uid))  # FIX AQUI
            except:
                membro = None

            if membro:
                lista.append(f"🎂 {membro.display_name} - {info['data']}")

        if not lista:
            await message.channel.send(embed=criar_embed(
                "Lista", "📭 Nenhum aniversário encontrado.",
                discord.Color.orange()))
            return

        await message.channel.send(embed=criar_embed(
            "📅 Aniversariantes",
            "\n".join(lista),
            discord.Color.purple()
        ))


# ---------- EXECUÇÃO ----------
keep_alive()
client.run(os.getenv("DISCORD_TOKEN"))
