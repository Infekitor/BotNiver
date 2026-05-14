import discord
import os
import asyncio
import datetime
from datetime import timezone, timedelta
from flask import Flask
from threading import Thread
from pymongo import MongoClient
from discord.ext import tasks

# --- MANTENDO O BOT ONLINE (KEEP ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "PowerNiver bot está rodando! 🎉"

def keep_alive():
    # Roda o servidor Flask em uma thread separada
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8080}).start()

# --- CONFIGURAÇÃO DO BANCO DE DADOS (MONGODB) ---
MONGO_URI = os.getenv("MONGO_URI")
db_client = MongoClient(MONGO_URI)
db = db_client["powerniver_db"]
db_collection_aniversarios = db["aniversarios"]
db_collection_config = db["config"]

# --- CONFIGURAÇÃO DO BOT (DISCORD) ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # LEMBRE-SE: Ative "Server Members Intent" no Developer Portal!

client = discord.Client(intents=intents)

def criar_embed(titulo, descricao, cor=discord.Color.purple()):
    return discord.Embed(title=titulo, description=descricao, color=cor)

# --- TAREFA AUTOMÁTICA DE CHECAGEM ---
@tasks.loop(minutes=30)
async def rotina_aniversarios():
    """Verifica se há aniversariantes e envia mensagens nos canais configurados."""
    fuso = timezone(timedelta(hours=-3)) # Horário de Brasília
    hoje = datetime.datetime.now(fuso).strftime("%d/%m")
    
    configs = db_collection_config.find({})
    for config in configs:
        guild_id = config["_id"]
        canal_id = config.get("channel_id")
        last_date = config.get("last_announcement_date")

        # Evita anunciar mais de uma vez no mesmo dia
        if not canal_id or last_date == hoje:
            continue

        guild = client.get_guild(int(guild_id))
        if not guild: continue
        
        canal = guild.get_channel(int(canal_id))
        if not canal: continue

        # Busca todos os aniversariantes registrados para hoje
        aniversariantes = db_collection_aniversarios.find({"data": hoje})
        
        achou_alguem = False
        for niver in aniversariantes:
            user_id = int(niver["_id"])
            member = guild.get_member(user_id)
            
            if member:
                achou_alguem = True
                embed = criar_embed(
                    f"🎉 Feliz Aniversário, {niver['nome']}! 🎂", 
                    f"Hoje celebramos o dia de {member.mention}! ✨", 
                    discord.Color.gold()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                await canal.send(content=f"Parabéns, {member.mention}!", embed=embed)

        if achou_alguem:
            db_collection_config.update_one({"_id": guild_id}, {"$set": {"last_announcement_date": hoje}})

# --- EVENTOS E COMANDOS ---
@client.event
async def on_ready():
    print(f'✅ Bot conectado como {client.user}')
    if not rotina_aniversarios.is_running():
        rotina_aniversarios.start()

@client.event
async def on_message(message):
    if message.author.bot:
        return

    # p!help
    if message.content == "p!help":
        embed = criar_embed("📚 Guia de Comandos", "Funções do PowerNiver:")
        embed.add_field(name="🎂 `p!aniversario DD/MM`", value="Registra seu aniversário.", inline=False)
        embed.add_field(name="👤 `p!addaniversario @user DD/MM`", value="**(ADM)** Registra o niver de outro membro.", inline=False)
        embed.add_field(name="📅 `p!aniversariantes`", value="Lista os aniversários salvos.", inline=False)
        embed.add_field(name="🛠️ `p!setcanal #canal`", value="**(ADM)** Define onde os avisos serão enviados.", inline=False)
        embed.add_field(name="🏓 `p!ping`", value="Verifica a latência.", inline=False)
        await message.channel.send(embed=embed)

    # p!ping
    if message.content == "p!ping":
        latencia = round(client.latency * 1000)
        await message.channel.send(f"🏓 Pong! ({latencia}ms)")

    # p!aniversario (Auto-registro)
    if message.content.startswith("p!aniversario"):
        partes = message.content.split()
        if len(partes) != 2:
            return await message.channel.send("❌ Use: `p!aniversario DD/MM` (Ex: 15/08)")
        
        data = partes[1]
        db_collection_aniversarios.update_one(
            {"_id": str(message.author.id)},
            {"$set": {"nome": message.author.display_name, "data": data}},
            upsert=True
        )
        await message.channel.send(f"🎉 {message.author.mention}, seu aniversário foi salvo para **{data}**!")

    # p!addaniversario (Para ADMs, conforme a imagem image_bc5fdd.png)
    if message.content.startswith("p!addaniversario"):
        if not message.author.guild_permissions.administrator:
            return await message.channel.send("❌ Apenas administradores podem usar este comando.")

        partes = message.content.split()
        if len(partes) < 3 or not message.mentions:
            return await message.channel.send("❌ Use: `p!addaniversario @usuario DD/MM`")

        usuario_alvo = message.mentions[0]
        data = partes[-1] # Pega a última parte do texto (a data)

        db_collection_aniversarios.update_one(
            {"_id": str(usuario_alvo.id)},
            {"$set": {"nome": usuario_alvo.display_name, "data": data}},
            upsert=True
        )
        embed = criar_embed("Sucesso!", f"✅ O aniversário de {usuario_alvo.mention} foi definido para **{data}**.", discord.Color.green())
        await message.channel.send(embed=embed)

    # p!aniversariantes
    if message.content == "p!aniversariantes":
        registros = db_collection_aniversarios.find({})
        lista = []
        for r in registros:
            # Mostra apenas quem está neste servidor
            if message.guild.get_member(int(r["_id"])):
                lista.append(f"• **{r['nome']}** - {r['data']}")
        
        desc = "\n".join(lista) if lista else "Nenhum registro encontrado."
        await message.channel.send(embed=criar_embed("📅 Lista de Aniversários", desc))

    # p!setcanal
    if message.content.startswith("p!setcanal"):
        if not message.author.guild_permissions.administrator:
            return await message.channel.send("❌ Sem permissão de Administrador.")
        
        if message.channel_mentions:
            canal = message.channel_mentions[0]
            db_collection_config.update_one(
                {"_id": str(message.guild.id)}, 
                {"$set": {"channel_id": str(canal.id)}}, 
                upsert=True
            )
            await message.channel.send(f"✅ Os avisos de aniversário serão enviados em {canal.mention}")

# --- EXECUÇÃO DO BOT ---
keep_alive() # Inicia o Flask
try:
    client.run(os.getenv("DISCORD_TOKEN"))
except Exception as e:
    print(f"❌ Erro fatal ao iniciar o bot: {e}")
