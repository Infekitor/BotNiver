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

# Configurações do MongoDB (Render → Environment)
MONGO_URI = os.getenv("MONGO_URI")
print(f"DEBUG: MONGO_URI lido: {MONGO_URI}")

db_client = None
db_collection_aniversarios = None
db_collection_config = None

def connect_to_mongodb():
    global db_client, db_collection_aniversarios, db_collection_config
    try:
        if not MONGO_URI:
            print("❌ Variável de ambiente MONGO_URI não configurada!")
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
    """Divide lista em sub‑listas de tamanho n"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# ---------- TAREFA DIÁRIA ----------
async def checar_aniversarios():
    await client.wait_until_ready()
    print("Iniciando checagem de aniversários...")

    while not client.is_closed():
        if db_client is None:
            print("Tentando reconectar ao MongoDB...")
            if not connect_to_mongodb():
                await asyncio.sleep(60)
                continue

        fuso_br = timezone(timedelta(hours=-3))
        hoje = datetime.datetime.now(fuso_br)
        data_hoje = hoje.strftime("%d/%m")
        print(f"🔎 Checando aniversários para: {data_hoje}")

        try:
            aniversarios = {d['_id']: d for d in db_collection_aniversarios.find({})}
            configuracoes = {d['_id']: d for d in db_collection_config.find({})}
        except Exception as e:
            print(f"❌ Erro lendo MongoDB: {e}")
            if not connect_to_mongodb():
                await asyncio.sleep(60)
            continue

        for guild in client.guilds:
            gid = str(guild.id)
            conf = configuracoes.get(gid, {})
            canal_id = conf.get("channel_id")
            last_date = conf.get("last_announcement_date")

            if not canal_id:
                print(f"⚠️ Servidor {guild.name} não configurou canal.")
                continue
            if last_date == data_hoje:
                continue

            canal = client.get_channel(int(canal_id))
            if not canal:
                print(f"❌ Canal {canal_id} não encontrado em {guild.name}.")
                continue

            try:
                await guild.chunk()
            except discord.Forbidden:
                print(f"⚠️ Sem permissão para chunk em {guild.name}.")
                continue

            houve_parabens = False
            for uid, info in aniversarios.items():
                member = guild.get_member(int(uid))
                if member and info["data"] == data_hoje:
                    houve_parabens = True
                    embed = discord.Embed(
                        title=f"🎉 Feliz Aniversário, {info['nome']}! 🎂",
                        description=f"Hoje é dia de celebrar **{info['nome']}**! "
                                    "Desejamos alegria, paz e muitos presentes! ✨",
                        color=discord.Color.gold()
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text="Que este novo ciclo seja incrível!")

                    await canal.send(
                        content=f"@everyone Parabéns, {member.mention}!",
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions(
                            everyone=True, users=True)
                    )
                    print(f"🎉 Parabéns enviados para {info['nome']} em {guild.name}")

            # marca como verificado (mesmo sem aniversariante)
            try:
                db_collection_config.update_one(
                    {"_id": gid},
                    {"$set": {"last_announcement_date": data_hoje}},
                    upsert=True
                )
            except Exception as e:
                print(f"❌ Erro ao atualizar last_date: {e}")

            if not houve_parabens:
                print(f"📭 Sem aniversariantes hoje em {guild.name}.")

        await asyncio.sleep(3600)  # 1 h


# ---------- EVENTOS ----------
@client.event
async def on_ready():
    print(f'✅ Bot conectado como {client.user}')
    client.loop.create_task(checar_aniversarios())


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    if db_client is None:
        await message.channel.send(embed=criar_embed(
            "Erro de Conexão",
            "❌ Não foi possível conectar ao banco de dados.",
            discord.Color.red()))
        return

    # ----- p!help -----
    if message.content == "p!help":
        embed = criar_embed("Comandos do PowerNiver Bot",
                            "Aqui estão todos os comandos:",
                            discord.Color.blue())
        embed.add_field(name="`p!help`", value="Mostra esta ajuda.", inline=False)
        embed.add_field(name="`p!ping`", value="Teste de latência.", inline=False)
        embed.add_field(name="`p!aniversario DD/MM`",
                        value="Registra seu aniversário.", inline=False)
        embed.add_field(name="`p!aniversariantes`",
                        value="Lista aniversários deste servidor (paginado).", inline=False)
        embed.add_field(name="`p!removeraniversario`",
                        value="Remove seu aniversário.", inline=False)
        embed.add_field(name="`p!proximoaniversario`",
                        value="Mostra o próximo aniversário.", inline=False)
        embed.add_field(name="`p!addaniversario @user DD/MM`",
                        value="**ADM** – adiciona aniversário de outro usuário.",
                        inline=False)
        embed.add_field(name="`p!setcanal #canal`",
                        value="**ADM** – define o canal de avisos.",
                        inline=False)
        embed.add_field(name="`p!testealerta [@alvo]`",
                        value="**ADM** – mostra como fica o embed diário.",
                        inline=False)
        embed.set_footer(text="Aproveite o bot! 🎉")
        await message.channel.send(embed=embed)

    # ----- p!ping -----
    if message.content == "p!ping":
        await message.channel.send(embed=criar_embed(
            "Pong", "pong ✅", discord.Color.green()))

    # ----- p!aniversario (registro) -----
    if message.content.startswith("p!aniversario"):
        partes = message.content.split()
        if len(partes) != 2:
            await message.channel.send(embed=criar_embed(
                "Erro", "Use: `p!aniversario DD/MM`", discord.Color.red()))
            return
        data = partes[1]
        try:
            dia, mes = map(int, data.split("/"))
            if dia not in range(1, 32) or mes not in range(1, 13):
                raise ValueError
        except ValueError:
            await message.channel.send(embed=criar_embed(
                "Erro", "Data inválida. Use DD/MM.", discord.Color.red()))
            return
        try:
            db_collection_aniversarios.update_one(
                {"_id": str(message.author.id)},
                {"$set": {"nome": message.author.display_name, "data": data}},
                upsert=True)
            await message.channel.send(embed=criar_embed(
                "Aniversário Registrado",
                f"🎉 {message.author.mention} em {data}!",
                discord.Color.green()))
        except Exception as e:
            await message.channel.send(embed=criar_embed(
                "Erro", f"DB error: {e}", discord.Color.red()))

    # ----- p!aniversariantes (paginado) -----
    if message.content.startswith("p!aniversariantes"):
        if message.guild:
            try:
                await message.guild.chunk()
            except discord.Forbidden:
                await message.channel.send(embed=criar_embed(
                    "Permissão", "Sem permissão para listar membros.",
                    discord.Color.red()))
                return
        try:
            aniversarios = {d['_id']: d for d in db_collection_aniversarios.find({})}
        except Exception as e:
            await message.channel.send(embed=criar_embed(
                "Erro", f"DB error: {e}", discord.Color.red()))
            return

        lista = [info for uid, info in aniversarios.items()
                 if message.guild.get_member(int(uid))]
        if not lista:
            await message.channel.send(embed=criar_embed(
                "Lista", "📭 Nenhum aniversário neste servidor.",
                discord.Color.orange()))
            return

        lista.sort(key=lambda x: (int(x['data'][3:]), int(x['data'][:2])))
        paginas = list(chunk(lista, 10))

        class Paginador(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=120)
                self.ind = 0
                self._update_buttons()

            def _embed(self):
                e = discord.Embed(title="📅 Lista de Aniversariantes",
                                  color=discord.Color.purple())
                for i in paginas[self.ind]:
                    e.add_field(name=i['nome'],
                                value=f"🎂 {i['data']}", inline=False)
                e.set_footer(text=f"Página {self.ind+1}/{len(paginas)}")
                return e

            def _update_buttons(self):
                self.first.disabled = self.prev.disabled = (self.ind == 0)
                self.next.disabled = self.last.disabled = (
                    self.ind == len(paginas) - 1)

            @discord.ui.button(label='⏮', style=discord.ButtonStyle.grey)
            async def first(self, interaction: discord.Interaction, _):
                self.ind = 0; self._update_buttons()
                await interaction.response.edit_message(embed=self._embed(), view=self)

            @discord.ui.button(label='◀', style=discord.ButtonStyle.grey)
            async def prev(self, interaction: discord.Interaction, _):
                self.ind -= 1; self._update_buttons()
                await interaction.response.edit_message(embed=self._embed(), view=self)

            @discord.ui.button(label='▶', style=discord.ButtonStyle.grey)
            async def next(self, interaction: discord.Interaction, _):
                self.ind += 1; self._update_buttons()
                await interaction.response.edit_message(embed=self._embed(), view=self)

            @discord.ui.button(label='⏭', style=discord.ButtonStyle.grey)
            async def last(self, interaction: discord.Interaction, _):
                self.ind = len(paginas) - 1; self._update_buttons()
                await interaction.response.edit_message(embed=self._embed(), view=self)

        view = Paginador()
        await message.channel.send(embed=view._embed(), view=view)

    # ----- p!removeraniversario -----
    if message.content.startswith("p!removeraniversario"):
        try:
            result = db_collection_aniversarios.delete_one(
                {"_id": str(message.author.id)})
            if result.deleted_count:
                await message.channel.send(embed=criar_embed(
                    "Removido", "🗑️ Aniversário removido.",
                    discord.Color.green()))
            else:
                await message.channel.send(embed=criar_embed(
                    "Aviso", "⚠️ Você não tinha aniversário registrado.",
                    discord.Color.orange()))
        except Exception as e:
            await message.channel.send(embed=criar_embed(
                "Erro", f"DB error: {e}", discord.Color.red()))

    # ----- p!proximoaniversario -----
    if message.content.startswith("p!proximoaniversario"):
        fuso_br = timezone(timedelta(hours=-3))
        hoje = datetime.datetime.now(fuso_br)
        try:
            aniversarios = {d['_id']: d for d in db_collection_aniversarios.find({})}
        except Exception as e:
            await message.channel.send(embed=criar_embed(
                "Erro", f"DB error: {e}", discord.Color.red()))
            return
        if not aniversarios:
            await message.channel.send(embed=criar_embed(
                "Próximo", "📭 Nenhum aniversário registrado.",
                discord.Color.orange()))
            return

        def faltam(data_str):
            d, m = map(int, data_str.split("/"))
            ano = hoje.year
            alvo = datetime.datetime(ano, m, d, tzinfo=fuso_br)
            if alvo < hoje:
                alvo = alvo.replace(year=ano + 1)
            return (alvo - hoje).days

        alvos = {uid: info for uid, info in aniversarios.items()
                 if message.guild.get_member(int(uid))}
        if not alvos:
            await message.channel.send(embed=criar_embed(
                "Próximo", "📭 Nenhum aniversário neste servidor.",
                discord.Color.orange()))
            return

        prox_uid, info = min(alvos.items(), key=lambda x: faltam(x[1]['data']))
        dias = faltam(info['data'])

        await message.channel.send(embed=criar_embed(
            "Próximo Aniversário",
            f"⏳ **{info['nome']}** em **{dias}** dia(s) — {info['data']} 🎉",
            discord.Color.green()))

    # ----- p!addaniversario (ADM) -----
    if message.content.startswith("p!addaniversario"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send(embed=criar_embed(
                "Permissão", "❌ Apenas administradores.",
                discord.Color.red()))
            return
        partes = message.content.split()
        if len(partes) != 3 or not message.mentions:
            await message.channel.send(embed=criar_embed(
                "Erro", "Use: `p!addaniversario @user DD/MM`",
                discord.Color.red()))
            return
        membro = message.mentions[0]
        data = partes[2]
        try:
            dia, mes = map(int, data.split("/"))
            if dia not in range(1, 32) or mes not in range(1, 13):
                raise ValueError
        except ValueError:
            await message.channel.send(embed=criar_embed(
                "Erro", "Data inválida.", discord.Color.red()))
            return
        try:
            db_collection_aniversarios.update_one(
                {"_id": str(membro.id)},
                {"$set": {"nome": membro.display_name, "data": data}},
                upsert=True)
            await message.channel.send(embed=criar_embed(
                "Adicionado",
                f"🎉 {membro.mention} em {data}!",
                discord.Color.green()))
        except Exception as e:
            await message.channel.send(embed=criar_embed(
                "Erro", f"DB error: {e}", discord.Color.red()))

    # ----- p!setcanal (ADM) -----
    if message.content.startswith("p!setcanal"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send(embed=criar_embed(
                "Permissão", "❌ Apenas administradores.",
                discord.Color.red()))
            return
        partes = message.content.split()
        if len(partes) < 2:
            await message.channel.send(embed=criar_embed(
                "Erro", "Use: `p!setcanal #canal` ou ID.",
                discord.Color.red()))
            return
        canal_sel = message.channel_mentions[0] if message.channel_mentions else None
        if not canal_sel:
            try:
                cid = int(partes[1].replace('<#', '').replace('>', ''))
                canal_sel = client.get_channel(cid)
            except ValueError:
                await message.channel.send(embed=criar_embed(
                    "Erro", "ID inválido.", discord.Color.red()))
                return
        if not canal_sel:
            await message.channel.send(embed=criar_embed(
                "Erro", "Canal não encontrado.", discord.Color.red()))
            return
        try:
            db_collection_config.update_one(
                {"_id": str(message.guild.id)},
                {"$set": {"channel_id": str(canal_sel.id)}},
                upsert=True)
            await message.channel.send(embed=criar_embed(
                "Configuração",
                f"✅ Canal de avisos: {canal_sel.mention}",
                discord.Color.green()))
        except Exception as e:
            await message.channel.send(embed=criar_embed(
                "Erro", f"DB error: {e}", discord.Color.red()))

    # ----- p!testealerta (ADM) -----
    if message.content.startswith("p!testealerta"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send(embed=criar_embed(
                "Permissão", "❌ Apenas administradores.",
                discord.Color.red()))
            return
        alvo = message.mentions[0] if message.mentions else message.author
        embed_teste = discord.Embed(
            title=f"🎉 Feliz Aniversário, {alvo.display_name}! 🎂",
            description=f"Hoje é o dia de celebrar **{alvo.display_name}**! "
                        "Desejamos um dia cheio de alegria, paz e muitos presentes! ✨",
            color=discord.Color.gold())
        embed_teste.set_thumbnail(url=alvo.display_avatar.url)
        embed_teste.set_footer(text="Que este novo ciclo seja incrível!")
        await message.channel.send(
            content=f"@everyone Parabéns, {alvo.mention}! (🎈 *mensagem de teste*)",
            embed=embed_teste,
            allowed_mentions=discord.AllowedMentions(everyone=True, users=True)
        )


# ---------- EXECUÇÃO ----------
keep_alive()
client.run(os.getenv("DISCORD_TOKEN"))
