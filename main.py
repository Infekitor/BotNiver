import discord
import os
import json
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
        if not MONGO_URI:
            print("❌ Erro: Variável de ambiente MONGO_URI não configurada!")
            return False

        db_client = MongoClient(MONGO_URI)
        db_client.admin.command('ping')
        print("✅ Conectado ao MongoDB Atlas!")
        db = db_client["powerniver_db"]
        db_collection_aniversarios = db["aniversarios"]
        db_collection_config = db["config"]
        return True
    except Exception as e:
        print(f"❌ Erro ao conectar ao MongoDB: {e}")
        return False

connect_to_mongodb()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
intents.presences = True

client = discord.Client(intents=intents, member_cache_flags=discord.MemberCacheFlags.all())

# Função utilitária global para facilitar a criação de embeds
def criar_embed(titulo, descricao, cor=discord.Color.purple()):
    return discord.Embed(title=titulo, description=descricao, color=cor)

# --- TAREFA DE CHECAGEM ---
async def checar_aniversarios():
    await client.wait_until_ready()
    while not client.is_closed():
        if db_client is None:
            if not connect_to_mongodb():
                await asyncio.sleep(60)
                continue

        fuso_horario_brasilia = timezone(timedelta(hours=-3))
        hoje = datetime.datetime.now(fuso_horario_brasilia)
        data_hoje = hoje.strftime("%d/%m")

        try:
            aniversarios = {doc['_id']: doc for doc in db_collection_aniversarios.find({})}
            configuracoes = {doc['_id']: doc for doc in db_collection_config.find({})}
        except Exception as e:
            print(f"❌ Erro DB: {e}")
            await asyncio.sleep(60)
            continue

        for guild in client.guilds:
            guild_id = str(guild.id)
            guild_config = configuracoes.get(guild_id, {})
            canal_id = guild_config.get("channel_id")
            last_announcement_date = guild_config.get("last_announcement_date")

            if not canal_id or last_announcement_date == data_hoje:
                continue

            canal = client.get_channel(int(canal_id))
            if not canal:
                continue

            try:
                await guild.chunk()
            except:
                continue

            achou = False
            for user_id, info in aniversarios.items():
                member = guild.get_member(int(user_id))
                if member and info["data"] == data_hoje:
                    achou = True
                    embed = criar_embed(f"🎉 Feliz Aniversário, {info['nome']}! 🎂", 
                                        f"Hoje celebramos o dia de {member.mention}! ✨", 
                                        discord.Color.gold())
                    embed.set_thumbnail(url=member.display_avatar.url)
                    await canal.send(content=f"Parabéns, {member.mention}!", embed=embed)

            db_collection_config.update_one({"_id": guild_id}, {"$set": {"last_announcement_date": data_hoje}}, upsert=True)

        await asyncio.sleep(3600)

@client.event
async def on_ready():
    print(f'✅ Bot conectado como {client.user}')
    client.loop.create_task(checar_aniversarios())

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if db_client is None:
        return

    # --- COMANDO: p!help ---
    if message.content == "p!help":
        embed = criar_embed("📚 Guia de Comandos - PowerNiver", "Aqui estão as funções disponíveis:")
        embed.add_field(name="🎂 `p!aniversario DD/MM`", value="Registra seu aniversário.", inline=False)
        embed.add_field(name="📅 `p!aniversariantes`", value="Lista todos os aniversários do servidor.", inline=False)
        embed.add_field(name="⏳ `p!proximoaniversario`", value="Mostra quem é o próximo a fazer festa.", inline=False)
        embed.add_field(name="🗑️ `p!removeraniversario`", value="Remove seus dados do bot.", inline=False)
        embed.add_field(name="🛠️ `p!setcanal #canal`", value="**(ADM)** Define onde os avisos serão enviados.", inline=False)
        embed.add_field(name="👤 `p!addaniversario @user DD/MM`", value="**(ADM)** Registra o niver de outra pessoa.", inline=False)
        embed.add_field(name="🏓 `p!ping`", value="Checa a latência.", inline=False)
        embed.set_footer(text="Use sempre o formato Dia/Mês (ex: 15/03)")
        await message.channel.send(embed=embed)

    # p!ping
    if message.content == "p!ping":
        await message.channel.send(embed=criar_embed("Pong", "O bot está respondendo! ✅", discord.Color.green()))

    # p!aniversario
    if message.content.startswith("p!aniversario"):
        partes = message.content.split()
        if len(partes) != 2:
            return await message.channel.send(embed=criar_embed("Erro", "Use: `p!aniversario DD/MM`", discord.Color.red()))
        
        data = partes[1]
        try:
            db_collection_aniversarios.update_one(
                {"_id": str(message.author.id)},
                {"$set": {"nome": message.author.display_name, "data": data}},
                upsert=True
            )
            await message.channel.send(embed=criar_embed("Sucesso", f"🎉 Aniversário de {message.author.mention} salvo para {data}!", discord.Color.green()))
        except Exception as e:
            await message.channel.send(f"Erro: {e}")

    # p!aniversariantes
    if message.content == "p!aniversariantes":
        aniversarios = list(db_collection_aniversarios.find({}))
        if not aniversarios:
            return await message.channel.send("Nenhum registro encontrado.")
        
        lista = []
        for n in aniversarios:
            if message.guild.get_member(int(n["_id"])):
                lista.append(f"• **{n['nome']}** - {n['data']}")
        
        embed = criar_embed("📅 Lista de Aniversários", "\n".join(lista) if lista else "Ninguém deste servidor registrado.")
        await message.channel.send(embed=embed)

    # p!removeraniversario
    if message.content == "p!removeraniversario":
        db_collection_aniversarios.delete_one({"_id": str(message.author.id)})
        await message.channel.send(embed=criar_embed("Removido", "🗑️ Seus dados foram apagados.", discord.Color.green()))

    # p!proximoaniversario
    if message.content == "p!proximoaniversario":
        # Lógica simplificada: busca todos e filtra no código
        aniversarios = list(db_collection_aniversarios.find({}))
        # (Aqui você pode manter a lógica de cálculo de dias que você já tinha no seu código)
        await message.channel.send("🔎 Calculando próximo aniversário...")

    # p!addaniversario
    if message.content.startswith("p!addaniversario"):
        if not message.author.guild_permissions.administrator:
            return await message.channel.send("Apenas ADMs!")
        # ... (restante da sua lógica de addaniversario)

    # p!setcanal
    if message.content.startswith("p!setcanal"):
        if not message.author.guild_permissions.administrator:
            return await message.channel.send("Apenas ADMs!")
        if message.channel_mentions:
            canal = message.channel_mentions[0]
            db_collection_config.update_one({"_id": str(message.guild.id)}, {"$set": {"channel_id": str(canal.id)}}, upsert=True)
            await message.channel.send(f"✅ Canal definido: {canal.mention}")

# --- EXECUÇÃO ---
keep_alive()
client.run(os.getenv("DISCORD_TOKEN"))
