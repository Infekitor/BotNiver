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

# Configurações do MongoDB
# O URI de conexão será obtido das variáveis de ambiente do Render
MONGO_URI = os.getenv("MONGO_URI")
print(f"DEBUG: MONGO_URI lido: {MONGO_URI}")

db_client = None # Variável global para o cliente do MongoDB
db_collection_aniversarios = None
db_collection_config = None

def connect_to_mongodb():
    global db_client, db_collection_aniversarios, db_collection_config
    try:
        if MONGO_URI is None or MONGO_URI == "":
            print("❌ Erro: Variável de ambiente MONGO_URI não configurada ou vazia!")
            return False

        db_client = MongoClient(MONGO_URI)
        # Teste a conexão
        db_client.admin.command('ping')
        print("✅ Conectado ao MongoDB Atlas!")
        db = db_client["powerniver_db"] # Nome do seu banco de dados
        db_collection_aniversarios = db["aniversarios"] # Coleção para os aniversários
        db_collection_config = db["config"] # Coleção para as configurações do servidor (canais)
        return True
    except ConnectionFailure as e:
        print(f"❌ Falha ao conectar ao MongoDB Atlas: {e}")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado ao conectar ao MongoDB: {e}")
        return False

# Inicializa a conexão com o MongoDB logo no início
connect_to_mongodb()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # EXPLICITAMENTE ATIVAR A INTENT DE MEMBROS
intents.presences = True

client = discord.Client(intents=intents, member_cache_flags=discord.MemberCacheFlags.all())

async def checar_aniversarios():
    await client.wait_until_ready()
    print("Iniciando checagem de aniversários...")

    while not client.is_closed():
        # Reconnecta ao MongoDB se a conexão estiver perdida
        if db_client is None:
            print("Attempting to reconnect to MongoDB...")
            if not connect_to_mongodb():
                await asyncio.sleep(60) # Espera 1 minuto antes de tentar novamente se a conexão falhar
                continue

        fuso_horario_brasilia = timezone(timedelta(hours=-3))
        hoje = datetime.datetime.now(fuso_horario_brasilia)
        data_hoje = hoje.strftime("%d/%m")
        print(f"🔎 Checando aniversários para: {data_hoje}")

        try: # Bloco try-except para lidar com erros na leitura do DB
            # Carrega aniversários do MongoDB
            aniversarios_cursor = db_collection_aniversarios.find({})
            aniversarios = {doc['_id']: doc for doc in aniversarios_cursor}

            # Carrega configurações do MongoDB
            configuracoes_cursor = db_collection_config.find({})
            configuracoes = {doc['_id']: doc for doc in configuracoes_cursor}
        except Exception as e:
            print(f"❌ Erro ao carregar dados do MongoDB: {e}")
            aniversarios = {}
            configuracoes = {}
            # Tentar reconectar ou pular essa iteração se o DB não estiver disponível
            if not connect_to_mongodb():
                await asyncio.sleep(60) # Espera 1 minuto antes de tentar novamente
            continue # Pula para a próxima iteração do loop

        for guild in client.guilds:
            guild_id = str(guild.id)
            guild_config = configuracoes.get(guild_id, {})
            canal_id = guild_config.get("channel_id")
            last_announcement_date = guild_config.get("last_announcement_date")

            if canal_id is None:
                print(f"⚠️ Servidor {guild.name} (ID: {guild_id}) não tem um canal de aniversário configurado.")
                continue

            # Verifica se os parabéns já foram enviados hoje para este servidor
            if last_announcement_date == data_hoje:
                print(f"✅ Aniversários já verificados e anunciados para hoje no servidor {guild.name}.")
                continue # Pula para o próximo servidor

            canal = client.get_channel(int(canal_id))

            if canal is None:
                print(f"❌ Canal não encontrado para o servidor {guild.name} (ID: {guild_id}). Verifique o ID configurado.")
                continue

            try:
                await guild.chunk()
                print(f"🔄 Cache de membros carregado para o servidor: {guild.name} ({len(guild.members)} membros no cache)")
            except discord.Forbidden:
                print(f"⚠️ Sem permissão para carregar membros no servidor {guild.name}. Verifique as intents do bot.")
                continue

            achou_no_servidor = False
            for user_id, info in aniversarios.items():
                member = guild.get_member(int(user_id))
                if member and info["data"] == data_hoje:
                    achou_no_servidor = True

                    embed_aniversario = discord.Embed(
                        title=f"🎉 Feliz Aniversário, {info['nome']}! 🎂",
                        description=f"Hoje é o dia de celebrar o nosso querido(a) **{info['nome']}**! Desejamos um dia cheio de alegria, paz e muitos presentes! ✨",
                        color=discord.Color.gold()
                    )
                    embed_aniversario.set_thumbnail(url=member.display_avatar.url)
                    embed_aniversario.set_footer(text="Que este novo ciclo seja incrível!")

                    await canal.send(content=f"Parabéns, {member.mention}!", embed=embed_aniversario)

                    print(f"🎉 Parabéns enviados para {info['nome']} no servidor {guild.name}")

            # Após processar todos os usuários para o servidor atual, atualiza a data da última verificação.
            # Isso garante que, mesmo que não haja aniversariantes, a verificação do dia seja marcada como feita.
            try:
                db_collection_config.update_one(
                    {"_id": guild_id},
                    {"$set": {"last_announcement_date": data_hoje}},
                    upsert=True
                )
                print(f"📅 Data de última verificação de aniversário atualizada para {data_hoje} no servidor {guild.name}.")
            except Exception as e:
                print(f"❌ Erro ao atualizar last_announcement_date para {guild.name}: {e}")

            if not achou_no_servidor:
                print(f"📭 Nenhum aniversariante hoje no servidor {guild.name}.")

        await asyncio.sleep(3600)  # espera 1 hora antes de checar novamente

@client.event
async def on_ready():
    print(f'✅ Bot conectado como {client.user}')
    client.loop.create_task(checar_aniversarios())

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Certifica-se de que o MongoDB está conectado antes de processar comandos
    if db_client is None:
        await message.channel.send(embed=criar_embed("Erro de Conexão", "❌ O bot não conseguiu se conectar ao banco de dados. Tente novamente mais tarde ou contate o administrador.", discord.Color.red()))
        return

    def criar_embed(titulo, descricao, cor=discord.Color.purple()):
        return discord.Embed(title=titulo, description=descricao, color=cor)

    # p!help
    if message.content == "p!help":
        embed = criar_embed("Comandos do PowerNiver Bot", "Aqui estão todos os comandos que você pode usar:", discord.Color.blue())
        embed.add_field(name="`p!help`", value="Exibe esta mensagem de ajuda.", inline=False)
        embed.add_field(name="`p!ping`", value="Verifica se o bot está online.", inline=False)
        embed.add_field(name="`p!aniversario DD/MM`", value="Registra seu aniversário no formato Dia/Mês (ex: `p!aniversario 25/12`).", inline=False)
        embed.add_field(name="`p!aniversariantes`", value="Mostra a lista de todos os aniversários registrados neste servidor.", inline=False)
        embed.add_field(name="`p!removeraniversario`", value="Remove seu aniversário da lista.", inline=False)
        embed.add_field(name="`p!proximoaniversario`", value="Informa o próximo aniversário registrado neste servidor.", inline=False)
        embed.add_field(name="`p!addaniversario @usuario DD/MM`", value="**(Apenas ADM)** Adiciona o aniversário de outro usuário (ex: `p!addaniversario @fulano 01/01`).", inline=False)
        embed.add_field(name="`p!setcanal #canal`", value="**(Apenas ADM)** Define o canal onde o bot irá enviar os avisos de aniversário (ex: `p!setcanal #geral`).", inline=False)
        embed.set_footer(text="Aproveite o bot de aniversários! 🎉")
        await message.channel.send(embed=embed)

    # p!ping
    if message.content == "p!ping":
        await message.channel.send(embed=criar_embed("Pong", "pong ✅", discord.Color.green()))

    # p!aniversario (registrar o próprio aniversário)
    if message.content.startswith("p!aniversario"):
        partes = message.content.split()
        if len(partes) != 2:
            await message.channel.send(embed=criar_embed("Erro", "❌ Use assim: `p!aniversario DD/MM`", discord.Color.red()))
            return

        data = partes[1]
        try:
            dia, mes = map(int, data.split("/"))
            if not (1 <= dia <= 31 and 1 <= mes <= 12):
                raise ValueError
        except ValueError:
            await message.channel.send(embed=criar_embed("Erro", "❌ Data inválida. Use o formato DD/MM.", discord.Color.red()))
            return

        # Salva no MongoDB
        try:
            db_collection_aniversarios.update_one(
                {"_id": str(message.author.id)}, # ID do usuário como chave única
                {"$set": {"nome": message.author.display_name, "data": data}}, # Dados a salvar
                upsert=True # Insere se não existir, atualiza se existir
            )
            await message.channel.send(embed=criar_embed("Aniversário Registrado", f"🎉 Aniversário de {message.author.mention} registrado como {data}!", discord.Color.green()))
        except Exception as e:
            await message.channel.send(embed=criar_embed("Erro no DB", f"❌ Não foi possível registrar o aniversário: {e}", discord.Color.red()))


    # p!aniversariantes (lista todos os membros do servidor atual)
    if message.content.startswith("p!aniversariantes"):
        if message.guild:
            try:
                await message.guild.chunk()
                print(f"🔄 Cache de membros recarregado para o comando: {message.guild.name} ({len(message.guild.members)} membros no cache)")
            except discord.Forbidden:
                await message.channel.send(embed=criar_embed("Erro de Permissão", "❌ O bot não tem permissão para carregar a lista completa de membros. Verifique as intents e permissões.", discord.Color.red()))
                return

        try:
            # Carrega aniversários do MongoDB
            aniversarios_cursor = db_collection_aniversarios.find({})
            aniversarios = {doc['_id']: doc for doc in aniversarios_cursor}
        except Exception as e:
            await message.channel.send(embed=criar_embed("Erro no DB", f"❌ Não foi possível carregar a lista de aniversários: {e}", discord.Color.red()))
            aniversarios = {}


        if not aniversarios:
            await message.channel.send(embed=criar_embed("Lista de Aniversariantes", "📭 Nenhum aniversário registrado ainda.", discord.Color.orange()))
            return

        embed = discord.Embed(title="📅 Lista de Aniversariantes", color=discord.Color.purple())
        aniversariantes_do_servidor = []
        for user_id, info in aniversarios.items():
            member = message.guild.get_member(int(user_id))
            if member:
                aniversariantes_do_servidor.append(info)

        aniversariantes_do_servidor.sort(key=lambda x: (int(x['data'].split('/')[1]), int(x['data'].split('/')[0])))

        if not aniversariantes_do_servidor:
            await message.channel.send(embed=criar_embed("Lista de Aniversariantes", "📭 Nenhum aniversário registrado para este servidor ainda.", discord.Color.orange()))
        else:
            for info in aniversariantes_do_servidor:
                embed.add_field(name=info["nome"], value=f"🎂 {info['data']}", inline=False)
            await message.channel.send(embed=embed)


    # p!removeraniversario (remove o próprio)
    if message.content.startswith("p!removeraniversario"):
        user_id = str(message.author.id)

        try:
            # Remove do MongoDB
            result = db_collection_aniversarios.delete_one({"_id": user_id})

            if result.deleted_count > 0:
                await message.channel.send(embed=criar_embed("Removido", "🗑️ Seu aniversário foi removido da lista.", discord.Color.green()))
            else:
                await message.channel.send(embed=criar_embed("Aviso", "⚠️ Você não tinha um aniversário registrado.", discord.Color.orange()))
        except Exception as e:
            await message.channel.send(embed=criar_embed("Erro no DB", f"❌ Não foi possível remover o aniversário: {e}", discord.Color.red()))

    # p!proximoaniversario (próximo aniversário)
    if message.content.startswith("p!proximoaniversario"):
        fuso_horario_brasilia = timezone(timedelta(hours=-3))
        hoje = datetime.datetime.now(fuso_horario_brasilia)

        try:
            # Carrega aniversários do MongoDB
            aniversarios_cursor = db_collection_aniversarios.find({})
            aniversarios = {doc['_id']: doc for doc in aniversarios_cursor}
        except Exception as e:
            await message.channel.send(embed=criar_embed("Erro no DB", f"❌ Não foi possível carregar a lista de aniversários: {e}", discord.Color.red()))
            aniversarios = {}


        if not aniversarios:
            await message.channel.send(embed=criar_embed("Próximo Aniversário", "📭 Nenhum aniversário registrado.", discord.Color.orange()))
            return

        def dias_faltando(data_str):
            d, m = map(int, data_str.split("/"))
            ano = hoje.year

            data_aniver_este_ano = datetime.datetime(ano, m, d, tzinfo=fuso_horario_brasilia)

            if data_aniver_este_ano < hoje:
                data_aniver_este_ano = datetime.datetime(ano + 1, m, d, tzinfo=fuso_horario_brasilia)

            return (data_aniver_este_ano - hoje).days

        aniversarios_do_servidor = {
            uid: info for uid, info in aniversarios.items()
            if message.guild and message.guild.get_member(int(uid))
        }

        if not aniversarios_do_servidor:
            await message.channel.send(embed=criar_embed("Próximo Aniversário", "📭 Nenhum aniversário registrado para este servidor.", discord.Color.orange()))
            return

        proximos = sorted(aniversarios_do_servidor.items(), key=lambda x: dias_faltando(x[1]["data"]))

        proximo_id, info = proximos[0]
        dias = dias_faltando(info["data"])

        await message.channel.send(embed=criar_embed("Próximo Aniversário", f"⏳ O próximo aniversário é de **{info['nome']}** em **{dias}** dia(s) — {info['data']} 🎉", discord.Color.green()))

    # p!addaniversario @usuario DD/MM (ADM só)
    if message.content.startswith("p!addaniversario"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send(embed=criar_embed("Permissão Negada", "❌ Você precisa ser administrador para usar esse comando.", discord.Color.red()))
            return

        partes = message.content.split()
        if len(partes) != 3:
            await message.channel.send(embed=criar_embed("Erro", "❌ Use assim: `p!addaniversario @usuario DD/MM`", discord.Color.red()))
            return

        membro = message.mentions[0] if message.mentions else None
        data = partes[2]

        if membro is None:
            await message.channel.send(embed=criar_embed("Erro", "❌ Você precisa mencionar um usuário válido.", discord.Color.red()))
            return

        try:
            dia, mes = map(int, data.split("/"))
            if not (1 <= dia <= 31 and 1 <= mes <= 12):
                raise ValueError
        except ValueError:
            await message.channel.send(embed=criar_embed("Erro", "❌ Data inválida. Use o formato DD/MM.", discord.Color.red()))
            return

        try:
            # Salva no MongoDB
            db_collection_aniversarios.update_one(
                {"_id": str(membro.id)},
                {"$set": {"nome": membro.display_name, "data": data}},
                upsert=True
            )
            await message.channel.send(embed=criar_embed("Aniversário Adicionado", f"🎉 Aniversário de {membro.mention} registrado como {data}!", discord.Color.green()))
        except Exception as e:
            await message.channel.send(embed=criar_embed("Erro no DB", f"❌ Não foi possível adicionar o aniversário: {e}", discord.Color.red()))

    # p!setcanal (configura o canal de avisos)
    if message.content.startswith("p!setcanal"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send(embed=criar_embed("Permissão Negada", "❌ Você precisa ser administrador para usar esse comando.", discord.Color.red()))
            return

        partes = message.content.split()
        if len(partes) < 2:
            await message.channel.send(embed=criar_embed("Erro", "❌ Use assim: `p!setcanal #canal` ou `p!setcanal <ID_do_canal>`", discord.Color.red()))
            return

        canal_selecionado = message.channel_mentions[0] if message.channel_mentions else None

        if not canal_selecionado:
            try:
                canal_id_str = partes[1]
                canal_id = int(canal_id_str.replace('<#', '').replace('>', ''))
                canal_selecionado = client.get_channel(canal_id)
            except ValueError:
                await message.channel.send(embed=criar_embed("Erro", "❌ Formato de ID de canal inválido. Use um ID numérico ou mencione o canal.", discord.Color.red()))
                return

        if not canal_selecionado:
            await message.channel.send(embed=criar_embed("Erro", "❌ Canal não encontrado. Certifique-se de que o ID ou a menção estão corretos.", discord.Color.red()))
            return

        if not message.guild:
            await message.channel.send(embed=criar_embed("Erro", "❌ Este comando só pode ser usado em um servidor.", discord.Color.red()))
            return

        guild_id = str(message.guild.id)

        try:
            # Salva no MongoDB
            db_collection_config.update_one(
                {"_id": guild_id},
                {"$set": {"channel_id": str(canal_selecionado.id)}},
                upsert=True
            )
            await message.channel.send(embed=criar_embed("Configuração Concluída", f"✅ O canal de avisos de aniversário foi definido para {canal_selecionado.mention}!", discord.Color.green()))
        except Exception as e:
            await message.channel.send(embed=criar_embed("Erro no DB", f"❌ Não foi possível configurar o canal: {e}", discord.Color.red()))


# INICIA KEEP ALIVE E BOT
keep_alive()
client.run(os.getenv("DISCORD_TOKEN"))
