import discord
import os
import asyncio
import datetime
from datetime import timezone, timedelta
from flask import Flask
from threading import Thread
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# --- KEEP ALIVE (Para manter o bot online 24/7) ---
app = Flask('')

@app.route('/')
def home():
    return "PowerNiver bot está rodando! 🎉"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- DISCORD BOT ---

MONGO_URI = os.getenv("MONGO_URI")

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
    except Exception as e:
        print(f"❌ Erro ao conectar ao MongoDB: {e}")
        return False

connect_to_mongodb()

# Configuração de Intents (Permissões)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 

client = discord.Client(intents=intents)

# ---------- UTILIDADES ----------
def criar_embed(titulo, descricao, cor=discord.Color.purple()):
    return discord.Embed(title=titulo, description=descricao, color=cor)

# ---------- TAREFA DIÁRIA (Otimizada) ----------
async def checar_aniversarios():
    await client.wait_until_ready()
    print("Iniciando monitoramento de aniversários...")

    while not client.is_closed():
        fuso_br = timezone(timedelta(hours=-3))
        agora = datetime.datetime.now(fuso_br)
        data_hoje = agora.strftime("%d/%m")

        # Busca apenas quem faz niver hoje
        aniversariantes_hoje = list(db_collection_aniversarios.find({"data": data_hoje}))

        if aniversariantes_hoje:
            # Pega as configurações de canais de todos os servidores
            configuracoes = {d['_id']: d for d in db_collection_config.find({})}

            for guild in client.guilds:
                gid = str(guild.id)
                conf = configuracoes.get(gid)
                
                if not conf or not conf.get("channel_id"):
                    continue

                canal = client.get_channel(int(conf["channel_id"]))
                if not canal:
                    continue

                for niver in aniversariantes_hoje:
                    # Verifica se o aniversariante pertence a este servidor
                    membro = guild.get_member(int(niver["_id"]))
                    if membro:
                        embed = discord.Embed(
                            title=f"🎉 Feliz Aniversário, {niver['nome']}!",
                            description=f"Parabéns {membro.mention}! Muita saúde e felicidade! 🎂",
                            color=discord.Color.gold()
                        )
                        await canal.send(embed=embed)

        # Cálculo para rodar apenas na próxima meia-noite (evita spam)
        amanha = (agora + timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
        espera = (amanha - agora).total_seconds()
        print(f"Próxima checagem em: {espera/3600:.2f} horas.")
        await asyncio.sleep(espera)

# ---------- EVENTOS ----------
@client.event
async def on_ready():
    print(f'✅ Bot conectado como {client.user}')
    # Inicia o loop de aniversários se não estiver rodando
    if not hasattr(client, 'niver_task_started'):
        client.loop.create_task(checar_aniversarios())
        client.niver_task_started = True

@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Comando: Ping
    if message.content == "p!ping":
        await message.channel.send(embed=criar_embed("Pong 🏓", "Estou online!", discord.Color.green()))

    # Comando: Registrar Aniversário
    if message.content.startswith("p!aniversario"):
        partes = message.content.split()
        if len(partes) != 2:
            return await message.channel.send(embed=criar_embed("Erro", "Use: `p!aniversario DD/MM`", discord.Color.red()))

        data = partes[1]
        
        # Validação de data real
        try:
            datetime.datetime.strptime(data, "%d/%m")
        except ValueError:
            return await message.channel.send(embed=criar_embed("Erro", "Data inválida! Use o formato `DD/MM` (Ex: 25/12)", discord.Color.red()))

        db_collection_aniversarios.update_one(
            {"_id": str(message.author.id)},
            {"$set": {"nome": message.author.display_name, "data": data}},
            upsert=True
        )
        await message.channel.send(embed=criar_embed("Sucesso", f"🎉 Aniversário de {message.author.display_name} salvo para o dia {data}!", discord.Color.green()))

    # Comando: Setar Canal de Avisos
    if message.content == "p!config":
        db_collection_config.update_one(
            {"_id": str(message.guild.id)},
            {"$set": {"channel_id": str(message.channel.id)}},
            upsert=True
        )
        await message.channel.send(embed=criar_embed("Configuração", "✅ Este canal agora receberá os avisos de aniversário!", discord.Color.blue()))

    # Comando: Listar Aniversariantes
    if message.content == "p!aniversariantes":
        aniversarios = list(db_collection_aniversarios.find({}))
        
        if not aniversarios:
            return await message.channel.send(embed=criar_embed("Lista", "Nenhum aniversário registrado.", discord.Color.orange()))

        lista_final = []
        for n in aniversarios:
            membro = message.guild.get_member(int(n["_id"]))
            if membro:
                lista_final.append(f"🎂 **{membro.display_name}** - {n['data']}")

        if not lista_final:
            return await message.channel.send(embed=criar_embed("Lista", "Nenhum aniversariante deste servidor encontrado.", discord.Color.orange()))

        await message.channel.send(embed=criar_embed("📅 Próximos Aniversariantes", "\n".join(lista_final)))

# ---------- EXECUÇÃO ----------
keep_alive()
client.run(os.getenv("DISCORD_TOKEN"))
