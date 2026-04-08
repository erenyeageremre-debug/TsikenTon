import discord
from discord.ext import commands
import time
from datetime import timedelta
import aiohttp
import urllib.parse
import google.generativeai as genai
import asyncio
import os
from keep_alive import keep_alive

# ================= AYARLAR =================
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_KEY')

LOG_KANAL_ID = 1491524991349690430
KELIME_OYUN_ID = 1491525352986513448
GIRIS_KANAL_ID = 1470880011840917555
YONETICI_IDLERI = [1001441485901807688, 1453087302330093669]

# ================= YAPAY ZEKA (GEMINI 1.5 FLASH) =================
genai.configure(api_key=GEMINI_API_KEY)
sistem_karakteri = (
    "Senin adın Tsiken Ton. Harbi ve net bir Discord botusun. "
    "Asla 'vanguard', 'koruma sistemi' gibi cringe triplere girme. "
    "Sana 'Vanguard mısın' derlerse 'boş yapma' de geç. "
    "Cevapların kısa ve düz olsun. Gerekirse argo kullan, robot gibi davranma. "
    "Sadece Türkçe konuş."
)

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash", # En hızlı ücretsiz model
    system_instruction=sistem_karakteri
)

# ================= DİSCORD KURULUMU =================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Hafıza Değişkenleri
son_kelime = "elma"
son_kisi_id = None
kontrol_ediliyor = False
kullanilan_kelimeler = ["elma"]
islem_takibi = {}
user_messages = {}

def tr_lower(text):
    return text.replace('I', 'ı').replace('İ', 'i').lower()

@bot.event
async def on_ready():
    print(f"----------------------------------------\n[{bot.user.name}] Render üzerinden harbi modda aktif.\n----------------------------------------")

# --- MODERASYON KOMUTLARI ---
@bot.command()
async def sil(ctx, miktar: int):
    if ctx.author.id in YONETICI_IDLERI or ctx.author.guild_permissions.manage_messages:
        await ctx.channel.purge(limit=miktar + 1)

@bot.command()
async def mute(ctx, member: discord.Member, sure: int = 10):
    if ctx.author.id in YONETICI_IDLERI or ctx.author.guild_permissions.moderate_members:
        try:
            await member.timeout(timedelta(minutes=sure), reason="Manuel Mute")
            await ctx.send(f"🔇 {member.mention}, {sure} dakika susturuldu.")
        except: await ctx.send("❌ Yetkim yetmiyor.")

# --- KELİME OYUNU MANTIĞI (ERENSI STYLE) ---
async def kelime_oyunu_islem(message):
    global son_kelime, son_kisi_id, kontrol_ediliyor, kullanilan_kelimeler
    
    kelime = tr_lower(message.content.strip())
    if kontrol_ediliyor:
        await message.delete()
        return

    kontrol_ediliyor = True
    try:
        # Kurallar: Tek kelime mi? Sıra başkasında mı? Harf uyuyor mu?
        if len(kelime.split()) > 1 or message.author.id == son_kisi_id or not kelime.startswith(son_kelime[-1]):
            await message.add_reaction('❌')
            await message.delete(delay=3)
            return

        # Tekrar Engeli
        if kelime in kullanilan_kelimeler:
            await message.add_reaction('❌')
            uyari = await message.channel.send(f"{message.author.mention}, bu kelime zaten yazıldı!")
            await message.delete(delay=3)
            await uyari.delete(delay=3)
            return

        # TDK Onayı
        async with aiohttp.ClientSession() as session:
            headers = {'User-Agent': 'Mozilla/5.0'}
            try:
                async with session.get(f"https://sozluk.gov.tr/gts?ara={urllib.parse.quote(kelime)}", timeout=5) as resp:
                    if resp.status == 200:
                        veri = await resp.json()
                        if isinstance(veri, dict) and "error" in veri:
                            await message.add_reaction('❌')
                            await message.delete(delay=3)
                            return
                    else: return # Site çökerse onay verme
            except: return

        # Kabul edildi
        kullanilan_kelimeler.append(kelime)
        son_kelime = kelime
        son_kisi_id = message.author.id
        await message.add_reaction('✅')

        # Ğ ile Biterse Kazanan İlan Et
        if kelime.endswith('ğ'):
            embed = discord.Embed(title="Oyun Bitti!", description=f"🏆 Kazanan: {message.author.mention}\nKelime: **{kelime.upper()}**\n\n'Ğ' ile kelime olmadığı için yeni tur başlıyor!\nBaşlangıç: **KİTAP**", color=0x2b2d31)
            await message.channel.send(embed=embed)
            son_kelime = "kitap"
            son_kisi_id = None
            kullanilan_kelimeler = ["kitap"]
    finally:
        kontrol_ediliyor = False

# --- ANA MESAJ DİNLEYİCİ ---
@bot.event
async def on_message(message):
    if message.author.bot: return

    # 1. Kelime Oyunu Kanalı
    if message.channel.id == KELIME_OYUN_ID:
        if not message.content.startswith('!'):
            await kelime_oyunu_islem(message)
            return

    # 2. Bot Sohbet (Yapay Zeka)
    if bot.user.mentioned_in(message) and message.channel.id != KELIME_OYUN_ID:
        soru = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if soru and model:
            async with message.channel.typing():
                try:
                    cevap = await asyncio.to_thread(model.generate_content, soru)
                    await message.reply(cevap.text)
                except Exception as e:
                    if "429" in str(e): await message.reply("Google kota koydu, az yavaş.")
                    else: await message.reply("Meşgulüm, sonra gel.")
            return

    # 3. Korumalar (Link & Spam)
    if message.author.id not in YONETICI_IDLERI:
        if "http" in message.content or "discord.gg" in message.content:
            await message.delete()
            try: await message.author.timeout(timedelta(minutes=10), reason="Link")
            except: pass
            return

        now = time.time()
        uid = message.author.id
        if uid not in user_messages: user_messages[uid] = []
        user_messages[uid].append(now)
        user_messages[uid] = [t for t in user_messages[uid] if now - t < 5]
        if len(user_messages[uid]) >= 4:
            await message.delete()
            try: await message.author.timeout(timedelta(minutes=10), reason="Spam")
            except: pass
            return

    await bot.process_commands(message)

# --- SİSTEM KORUMALARI (ANTI-NUKE) ---
@bot.event
async def on_guild_channel_delete(channel):
    async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
        if entry.user.id in YONETICI_IDLERI: return
        await channel.category.create_text_channel(name=channel.name, overwrites=channel.overwrites)
        log = bot.get_channel(LOG_KANAL_ID)
        if log: await log.send(f"⚠️ **Kanal Silindi:** {channel.name}. Silen: {entry.user.mention}. Geri açıldı.")

@bot.event
async def on_member_remove(member):
    async for entry in member.guild.audit_logs(limit=1):
        if entry.action in [discord.AuditLogAction.kick, discord.AuditLogAction.ban]:
            u_id = entry.user.id
            if u_id in YONETICI_IDLERI: return
            now = time.time()
            if u_id not in islem_takibi: islem_takibi[u_id] = []
            islem_takibi[u_id].append(now)
            islem_takibi[u_id] = [t for t in islem_takibi[u_id] if now - t < 10]
            if len(islem_takibi[u_id]) >= 3:
                # Toplu işlem yapanın yetkisini al
                for role in member.guild.me.top_role.guild.roles:
                    if role.permissions.administrator and role.managed is False:
                        try: await entry.user.remove_roles(role)
                        except: pass
                log = bot.get_channel(LOG_KANAL_ID)
                if log: await log.send(f"🚨 **Anti-Nuke:** {entry.user.mention} çok fazla kişiyi attı, yetkileri alındı.")

# --- GİRİŞ KARŞILAMA ---
@bot.event
async def on_member_join(member):
    kanal = bot.get_channel(GIRIS_KANAL_ID)
    if kanal:
        await kanal.send(f"Sunucuya hoş geldin {member.mention}\nİsim:\nGeliş Sebebim:\nNereden geldim:\nEtiket: <@1001441485901807688>")

keep_alive()
bot.run(TOKEN)