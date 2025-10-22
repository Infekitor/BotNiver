import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from pymongo import MongoClient
import pytz
import os

# === CONFIGURAÇÕES ===
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# === CONEXÃO COM MONGODB ===
MONGO_URI = os.getenv("MONGO_URI")  # ou coloque direto sua string aqui temporariamente
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["powerniver"]
collection = db["aniversarios"]

# === CANAL DE PARABÉNS ===
CANAL_PARABENS_ID = 1339658651555594342

# === FUSO HORÁRIO ===
fuso_brasilia = pytz.timezone('America/Sao_Paulo')


# === EVENTOS ===
@bot.event
async def on_ready():
    print(f"✅ Bot {bot.user} conectado com sucesso!")
    verificar_aniversarios.start()


# === FUNÇÕES ===
def formatar_data(data_str):
    try:
        data = datetime.strptime(data_str, "%d/%m")
        return data.strftime("%d/%m")
    except ValueError:
        return None


# === COMANDO: REGISTRAR ANIVERSÁRIO ===
@bot.command()
async def aniversario(ctx, *, data: str = None):
    if not data:
        await ctx.send(embed=discord.Embed(
            title="❌ Erro",
            description="Use: `!aniversario DD/MM`",
            color=discord.Color.red()))
        return

    data_formatada = formatar_data(data)
    if not data_formatada:
        await ctx.send(embed=discord.Embed(
            title="❌ Data inválida!",
            description="Use o formato `DD/MM` (ex: 25/12).",
            color=discord.Color.red()))
        return

    existente = collection.find_one({"id": ctx.author.id})
    if existente:
        collection.update_one({"id": ctx.author.id}, {"$set": {"data": data_formatada}})
        msg = "🎂 Data de aniversário atualizada!"
    else:
        collection.insert_one({
            "id": ctx.author.id,
            "nome": ctx.author.display_name,
            "data": data_formatada
        })
        msg = "🎉 Aniversário registrado com sucesso!"

    await ctx.send(embed=discord.Embed(
        title=msg,
        color=discord.Color.green()
    ))


# === COMANDO: LISTAR ANIVERSARIANTES (com avatar e paginação) ===
@bot.command()
async def aniversariantes(ctx):
    aniversarios = list(collection.find({}).sort("data", 1))

    if not aniversarios:
        await ctx.send(embed=discord.Embed(
            title="🎂 Nenhum aniversário registrado!",
            color=discord.Color.red()
        ))
        return

    paginas = [aniversarios[i:i + 5] for i in range(0, len(aniversarios), 5)]

    class Paginador(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            self.ind = 0

        async def _gerar_embeds(self):
            embeds = []
            for i in paginas[self.ind]:
                user = ctx.guild.get_member(i["id"])
                nome = i["nome"]
                data = i["data"]

                e = discord.Embed(
                    title=f"🎂 {nome}",
                    description=f"📅 **{data}**",
                    color=discord.Color.purple()
                )
                if user and user.avatar:
                    e.set_thumbnail(url=user.avatar.url)
                else:
                    e.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/168/168726.png")

                embeds.append(e)
            return embeds

        async def _mostrar(self, interaction: discord.Interaction):
            embeds = await self._gerar_embeds()
            self.first_button.disabled = self.prev_button.disabled = (self.ind == 0)
            self.next_button.disabled = self.last_button.disabled = (self.ind == len(paginas) - 1)
            await interaction.response.edit_message(embeds=embeds, view=self)

        @discord.ui.button(label='⏮', style=discord.ButtonStyle.grey)
        async def first_button(self, interaction: discord.Interaction, _):
            self.ind = 0
            await self._mostrar(interaction)

        @discord.ui.button(label='◀', style=discord.ButtonStyle.grey)
        async def prev_button(self, interaction: discord.Interaction, _):
            if self.ind > 0:
                self.ind -= 1
            await self._mostrar(interaction)

        @discord.ui.button(label='▶', style=discord.ButtonStyle.grey)
        async def next_button(self, interaction: discord.Interaction, _):
            if self.ind < len(paginas) - 1:
                self.ind += 1
            await self._mostrar(interaction)

        @discord.ui.button(label='⏭', style=discord.ButtonStyle.grey)
        async def last_button(self, interaction: discord.Interaction, _):
            self.ind = len(paginas) - 1
            await self._mostrar(interaction)

    view = Paginador()
    embeds_iniciais = await view._gerar_embeds()
    await ctx.send(embeds=embeds_iniciais, view=view)


# === COMANDO: REMOVER ANIVERSÁRIO ===
@bot.command()
async def removeraniversario(ctx):
    resultado = collection.delete_one({"id": ctx.author.id})
    if resultado.deleted_count > 0:
        msg = "🗑️ Seu aniversário foi removido!"
        cor = discord.Color.orange()
    else:
        msg = "❌ Você não tinha aniversário registrado!"
        cor = discord.Color.red()

    await ctx.send(embed=discord.Embed(title=msg, color=cor))


# === COMANDO: PRÓXIMO ANIVERSÁRIO ===
@bot.command()
async def proximoaniversario(ctx):
    agora = datetime.now(fuso_brasilia)
    hoje = agora.strftime("%d/%m")

    aniversarios = list(collection.find({}))
    if not aniversarios:
        await ctx.send(embed=discord.Embed(
            title="🎂 Nenhum aniversário registrado!",
            color=discord.Color.red()
        ))
        return

    datas = []
    for i in aniversarios:
        d = datetime.strptime(i["data"], "%d/%m").replace(year=agora.year)
        if d < agora:
            d = d.replace(year=agora.year + 1)
        datas.append((i, d))

    proximo = min(datas, key=lambda x: x[1])
    dias_restantes = (proximo[1] - agora).days

    e = discord.Embed(
        title="🎉 Próximo aniversário!",
        description=f"**{proximo[0]['nome']}** 🎂 em **{proximo[0]['data']}**\nFaltam **{dias_restantes} dias**!",
        color=discord.Color.gold()
    )
    await ctx.send(embed=e)


# === TAREFA AUTOMÁTICA DE PARABÉNS ===
@tasks.loop(hours=24)
async def verificar_aniversarios():
    agora = datetime.now(fuso_brasilia)
    data_hoje = agora.strftime("%d/%m")

    aniversariantes = list(collection.find({"data": data_hoje}))
    if aniversariantes:
        canal = bot.get_channel(CANAL_PARABENS_ID)
        if canal:
            for pessoa in aniversariantes:
                user = canal.guild.get_member(pessoa["id"])
                if user:
                    e = discord.Embed(
                        title=f"🎉 Feliz aniversário, {user.display_name}!",
                        description="Espero que tenha um dia incrível! 🎂",
                        color=discord.Color.random()
                    )
                    e.set_thumbnail(url=user.avatar.url if user.avatar else None)
                    await canal.send(content=f"🎈 {user.mention}", embed=e)
    print(f"Verificação diária executada em {data_hoje}")


# === COMANDO: PING ===
@bot.command()
async def ping(ctx):
    await ctx.send(embed=discord.Embed(
        title="🏓 Pong!",
        description=f"Latência: `{round(bot.latency * 1000)}ms`",
        color=discord.Color.blurple()
    ))


# === INICIAR BOT ===
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
