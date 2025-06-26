import discord
import os
import json
import asyncio
import datetime
from datetime import timezone, timedelta
from flask import Flask
from threading import Thread

# --- KEEP ALIVE ---
app = Flask('')

@app.route('/')
def home():
    return "PowerNiver bot está rodando! 🎉"

def keep_alive():
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8080}).start()

# --- DISCORD BOT ---

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # EXPLICITAMENTE ATIVAR A INTENT DE MEMBROS
intents.presences = True # Também é bom garantir que presences esteja ativa para ver status, se necessário para outras coisas.

# Configura o cliente com as intents e cache de membros
client = discord.Client(intents=intents, member_cache_flags=discord.MemberCacheFlags.all())

# Arquivos para armazenar dados
ARQUIVO_ANIVERSARIOS = "aniversarios.json"
ARQUIVO_CONFIG = "config.json" # Novo arquivo para configurações do servidor

# Cria arquivos se não existirem
if not os.path.exists(ARQUIVO_ANIVERSARIOS):
    with open(ARQUIVO_ANIVERSARIOS, "w") as f:
        json.dump({}, f)

if not os.path.exists(ARQUIVO_CONFIG):
    with open(ARQUIVO_CONFIG, "w") as f:
        json.dump({}, f) # Estrutura: {"guild_id": {"channel_id": "..."}}

async def checar_aniversarios():
    await client.wait_until_ready()
    print("Iniciando checagem de aniversários...")

    while not client.is_closed():
        # Define o fuso horário para Brasília (UTC-3)
        fuso_horario_brasilia = timezone(timedelta(hours=-3))
        hoje = datetime.datetime.now(fuso_horario_brasilia)
        data_hoje = hoje.strftime("%d/%m")
        print(f"🔎 Checando aniversários para: {data_hoje}")

        with open(ARQUIVO_ANIVERSARIOS, "r") as f:
            aniversarios = json.load(f)

        with open(ARQUIVO_CONFIG, "r") as f:
            configuracoes = json.load(f)

        for guild in client.guilds:
            # CORREÇÃO: Usando guild.chunk() para garantir que o cache de membros esteja completo
            try:
                await guild.chunk() # Garante que o cache de membros do servidor esteja completo
                print(f"🔄 Cache de membros carregado para o servidor: {guild.name} ({len(guild.members)} membros no cache)")
            except discord.Forbidden:
                print(f"⚠️ Sem permissão para carregar membros no servidor {guild.name}. Verifique as intents do bot.")
                continue # Pula para o próximo servidor se não tiver permissão

            guild_id = str(guild.id)
            if guild_id in configuracoes and "channel_id" in configuracoes[guild_id]:
                canal_id = configuracoes[guild_id]["channel_id"]
                canal = client.get_channel(int(canal_id))

                if canal is None:
                    print(f"❌ Canal não encontrado para o servidor {guild.name} (ID: {guild_id}). Verifique o ID configurado.")
                    continue

                achou_no_servidor = False
                for user_id, info in aniversarios.items():
                    member = guild.get_member(int(user_id))
                    if member and info["data"] == data_hoje:
                        achou_no_servidor = True
                        
                        # --- INÍCIO DA ATUALIZAÇÃO PARA ENVIAR COM EMBED ---
                        embed_aniversario = discord.Embed(
                            title=f"🎉 Feliz Aniversário, {info['nome']}! 🎂",
                            description=f"Hoje é o dia de celebrar o nosso querido(a) **{info['nome']}**! Desejamos um dia cheio de alegria, paz e muitos presentes! ✨",
                            color=discord.Color.gold() # Cor do embed (amarelo dourado)
                        )
                        # Adiciona a foto de perfil do aniversariante
                        embed_aniversario.set_thumbnail(url=member.display_avatar.url) 
                        embed_aniversario.set_footer(text="Que este novo ciclo seja incrível!")

                        await canal.send(content=f"Parabéns, {member.mention}!", embed=embed_aniversario)
                        # --- FIM DA ATUALIZAÇÃO ---

                        print(f"🎉 Parabéns enviados para {info['nome']} no servidor {guild.name}")

                if not achou_no_servidor:
                    print(f"📭 Nenhum aniversariante hoje no servidor {guild.name}.")
            else:
                print(f"⚠️ Servidor {guild.name} (ID: {guild_id}) não tem um canal de aniversário configurado.")

        await asyncio.sleep(3600)  # espera 1 hora antes de checar novamente

@client.event
async def on_ready():
    print(f'✅ Bot conectado como {client.user}')
    client.loop.create_task(checar_aniversarios())

@client.event
async def on_message(message):
    if message.author == client.user:
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

        with open(ARQUIVO_ANIVERSARIOS, "r") as f:
            aniversarios = json.load(f)

        aniversarios[str(message.author.id)] = {
            "nome": message.author.display_name,
            "data": data
        }

        with open(ARQUIVO_ANIVERSARIOS, "w") as f:
            json.dump(aniversarios, f, indent=2)

        await message.channel.send(embed=criar_embed("Aniversário Registrado", f"🎉 Aniversário de {message.author.mention} registrado como {data}!", discord.Color.green()))

    # p!aniversariantes (lista todos os membros do servidor atual)
    if message.content.startswith("p!aniversariantes"):
        # Garante que o cache de membros esteja atualizado para o servidor atual
        if message.guild:
            try:
                await message.guild.chunk()
                print(f"🔄 Cache de membros recarregado para o comando: {message.guild.name} ({len(message.guild.members)} membros no cache)")
            except discord.Forbidden:
                await message.channel.send(embed=criar_embed("Erro de Permissão", "❌ O bot não tem permissão para carregar a lista completa de membros. Verifique as intents e permissões.", discord.Color.red()))
                return

        with open(ARQUIVO_ANIVERSARIOS, "r") as f:
            aniversarios = json.load(f)

        if not aniversarios:
            await message.channel.send(embed=criar_embed("Lista de Aniversariantes", "📭 Nenhum aniversário registrado ainda.", discord.Color.orange()))
            return

        embed = discord.Embed(title="📅 Lista de Aniversariantes", color=discord.Color.purple())
        aniversariantes_do_servidor = [] 
        for user_id, info in aniversarios.items():
            member = message.guild.get_member(int(user_id))
            if member: # Se o membro for encontrado no servidor
                aniversariantes_do_servidor.append(info)
        
        # Ordena a lista de aniversariantes por mês e depois por dia
        aniversariantes_do_servidor.sort(key=lambda x: (int(x['data'].split('/')[1]), int(x['data'].split('/')[0])))

        if not aniversariantes_do_servidor: 
            await message.channel.send(embed=criar_embed("Lista de Aniversariantes", "📭 Nenhum aniversário registrado para este servidor ainda.", discord.Color.orange()))
        else:
            for info in aniversariantes_do_servidor:
                embed.add_field(name=info["nome"], value=f"🎂 {info['data']}", inline=False)
            await message.channel.send(embed=embed)


    # p!removeraniversario (remove o próprio)
    if message.content.startswith("p!removeraniversario"):
        with open(ARQUIVO_ANIVERSARIOS, "r") as f:
            aniversarios = json.load(f)

        user_id = str(message.author.id)

        if user_id in aniversarios:
            del aniversarios[user_id]
            with open(ARQUIVO_ANIVERSARIOS, "w") as f:
                json.dump(aniversarios, f, indent=2)
            await message.channel.send(embed=criar_embed("Removido", "🗑️ Seu aniversário foi removido da lista.", discord.Color.green()))
        else:
            await message.channel.send(embed=criar_embed("Aviso", "⚠️ Você não tinha um aniversário registrado.", discord.Color.orange()))

    # p!proximoaniversario (próximo aniversário)
    if message.content.startswith("p!proximoaniversario"):
        fuso_horario_brasilia = timezone(timedelta(hours=-3))
        hoje = datetime.datetime.now(fuso_horario_brasilia)

        with open(ARQUIVO_ANIVERSARIOS, "r") as f:
            aniversarios = json.load(f)

        if not aniversarios:
            await message.channel.send(embed=criar_embed("Próximo Aniversário", "📭 Nenhum aniversário registrado.", discord.Color.orange()))
            return

        def dias_faltando(data_str):
            d, m = map(int, data_str.split("/"))
            ano = hoje.year
            
            # Tenta com o ano atual
            data_aniver_este_ano = datetime.datetime(ano, m, d, tzinfo=fuso_horario_brasilia)
            
            # Se o aniversário já passou este ano, calcula para o próximo ano
            if data_aniver_este_ano < hoje:
                data_aniver_este_ano = datetime.datetime(ano + 1, m, d, tzinfo=fuso_horario_brasilia)
            
            return (data_aniver_este_ano - hoje).days

        # Filtra aniversários para considerar apenas membros do servidor atual
        aniversarios_do_servidor = {
            uid: info for uid, info in aniversarios.items()  
            if message.guild and message.guild.get_member(int(uid)) # Agora mais confiável com o cache completo
        }

        if not aniversarios_do_servidor:
            await message.channel.send(embed=criar_embed("Próximo Aniversário", "📭 Nenhum aniversário registrado para este servidor.", discord.Color.orange()))
            return

        # Ordena para encontrar o mais próximo, garantindo que "hoje" ou "passado" seja ajustado
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

        with open(ARQUIVO_ANIVERSARIOS, "r") as f:
            aniversarios = json.load(f)

        aniversarios[str(membro.id)] = {
            "nome": membro.display_name,
            "data": data
        }

        with open(ARQUIVO_ANIVERSARIOS, "w") as f:
            json.dump(aniversarios, f, indent=2)

        await message.channel.send(embed=criar_embed("Aniversário Adicionado", f"🎉 Aniversário de {membro.mention} registrado como {data}!", discord.Color.green()))

    # p!setcanal (configura o canal de avisos)
    if message.content.startswith("p!setcanal"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send(embed=criar_embed("Permissão Negada", "❌ Você precisa ser administrador para usar esse comando.", discord.Color.red()))
            return

        partes = message.content.split()
        if len(partes) < 2:
            await message.channel.send(embed=criar_embed("Erro", "❌ Use assim: `p!setcanal #canal` ou `p!setcanal <ID_do_canal>`", discord.Color.red()))
            return

        # Tenta obter o canal pela menção
        canal_selecionado = message.channel_mentions[0] if message.channel_mentions else None

        # Se não houver menção, tenta pelo ID
        if not canal_selecionado:
            try:
                canal_id_str = partes[1]
                # Remove caracteres de menção de canal se presentes
                canal_id = int(canal_id_str.replace('<#', '').replace('>', ''))
                canal_selecionado = client.get_channel(canal_id)
            except ValueError:
                await message.channel.send(embed=criar_embed("Erro", "❌ Formato de ID de canal inválido. Use um ID numérico ou mencione o canal.", discord.Color.red()))
                return

        if not canal_selecionado:
            await message.channel.send(embed=criar_embed("Erro", "❌ Canal não encontrado. Certifique-se de que o ID ou a menção estão corretos.", discord.Color.red()))
            return

        if not message.guild: # Certifica-se de que o comando foi usado em um servidor
            await message.channel.send(embed=criar_embed("Erro", "❌ Este comando só pode ser usado em um servidor.", discord.Color.red()))
            return

        guild_id = str(message.guild.id)

        with open(ARQUIVO_CONFIG, "r") as f:
            configuracoes = json.load(f)

        if guild_id not in configuracoes:
            configuracoes[guild_id] = {}

        configuracoes[guild_id]["channel_id"] = str(canal_selecionado.id)

        with open(ARQUIVO_CONFIG, "w") as f:
            json.dump(configuracoes, f, indent=2)

        await message.channel.send(embed=criar_embed("Configuração Concluída", f"✅ O canal de avisos de aniversário foi definido para {canal_selecionado.mention}!", discord.Color.green()))


# INICIA KEEP ALIVE E BOT
keep_alive()
client.run(os.getenv("DISCORD_TOKEN"))
