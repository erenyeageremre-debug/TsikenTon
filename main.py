import discord
from discord.ext import commands
import time
from datetime import timedelta
import aiohttp
import urllib.parse
import google.generativeai as genai
import asyncio
import os
import traceback
from keep_alive import keep_alive

# ================= AYARLAR =================
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_KEY')

KELIME_OYUN_ID = 1491525352986513448
GIRIS_KANAL_ID = 1470880011840917555
YONETICI_IDLERI = [1001441485901807688, 1453087302330093669]
PATRON_ID = 1453087302330093669 

# ================= YAPAY ZEKA =================
genai.configure(api_key=GEMINI_API_KEY)
# Kişilik tamamen düzeltildi. Cringe sıfır.
sistem_karakteri = "Senin adın Tsiken Ton. Sıradan birisin, asla bot gibi konuşma. Kasıntı laflar etme, şov yapma. Biri sana soru sorarsa dümdüz, kısa ve net cevap ver. Argo kullanabilirsin."

model = genai.GenerativeModel(model_name="gemini-1.5-flash", system_instruction=sistem_karakteri)

# ================= BOT KURULUMU =================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

son_kelime = "elma"
son_kisi_id = None
kontrol_ediliyor = False
kullanilan_kelimeler = ["elma"]
islem_takibi = {}
user_messages = {}

def tr_lower(text):
    return text.replace('I', 'ı').replace('İ', 'i').lower()

async def patrona_rapor_ver(mesaj):
    try:
        patron = bot.get_user(PATRON_ID) or await bot.fetch_user(PATRON_ID)
        if patron:
            await patron.send(mesaj)
    except: pass

@bot.event
async def on_ready():
    print(f"[{bot.user.name}] Aktif.")
    # Sadece sana sessizce mesaj atar, chate şov yapmaz.
    await patrona_rapor_ver("🟢 **Sistem Aktif.** Sessiz modda nöbetteyim.")

# --- SESSİZ HATA YAKALAMA ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    await patrona_rapor_ver(f"⚠️ **Hata:** `{ctx.message.content}` -> `{str(error)}`")

# --- KOMUTLAR ---
@bot.command()
async def sil(ctx, miktar: int):
    if ctx.author.id in YONETICI_IDLERI or ctx.author.guild_permissions.manage_messages:
        await ctx.channel.purge(limit=miktar + 1)

@bot.command()
async def mute(ctx, member: discord.Member, sure: int = 10):
    if ctx.author.id in YONETICI_IDLERI or ctx.author.guild_permissions.moderate_members:
        try:
            await member.timeout(timedelta(minutes=sure))
            msg = await ctx.send(f"{member.mention} susturuldu ({sure}dk).")
            await msg.delete(delay=3) # Chati kirletmemek için mesajı siler
        except: pass

# --- MESAJ İŞLEMLERİ ---
@bot.event
async def on_message(message):
    global son_kelime, son_kisi_id, kontrol_ediliyor, kullanilan_kelimeler
    if message.author.bot: return

    # 1. KELİME OYUNU (ERENSI STYLE - TERTEMİZ)
    if message.channel.id == KELIME_OYUN_ID:
        if message.content.startswith('!'):
            await bot.process_commands(message)
            return

        kelime = tr_lower(message.content.strip())
        if kontrol_ediliyor:
            await message.delete(); return
        
        kontrol_ediliyor = True
        try:
            # Temel hata kontrolü (sessizce siler, uyarı atıp chati kirletmez)
            if len(kelime.split()) > 1 or message.author.id == son_kisi_id or not kelime.startswith(son_kelime[-1]) or kelime in kullanilan_kelimeler:
                await message.add_reaction('❌')
                await message.delete(delay=2)
                return
            
            # TDK Kontrolü
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://sozluk.gov.tr/gts?ara={urllib.parse.quote(kelime)}") as resp:
                    if resp.status == 200:
                        veri = await resp.json()
                        if isinstance(veri, dict) and "error" in veri:
                            await message.add_reaction('❌')
                            await message.delete(delay=2)
                            return
                    else: return

            # Kelime doğruysa
            kullanilan_kelimeler.append(kelime)
            son_kelime = kelime
            son_kisi_id = message.author.id
            await message.add_reaction('✅')
            
            # Bitiş durumu
            if kelime.endswith('ğ'):
                embed = discord.Embed(description=f"🎉 {message.author.mention} oyunu kazandı!\n\nYeni kelime: **kitap**", color=0x2b2d31)
                await message.channel.send(embed=embed)
                son_kelime = "kitap"; son_kisi_id = None; kullanilan_kelimeler = ["kitap"]
        finally:
            kontrol_ediliyor = False
        return

    # 2. YAPAY ZEKA (Sohbet)
    if bot.user.mentioned_in(message):
        soru = message.content.replace(f'<@{bot.user.id}>', '').strip()
        async with message.channel.typing():
            try:
                cevap = await asyncio.to_thread(model.generate_content, soru)
                await message.reply(cevap.text)
            except: 
                pass # Hata verirse chate "meşgulüm" bile yazmasın, susup geçsin (havalı durur)
        return

    # 3. KORUMALAR (Sessiz İnfaz)
    if message.author.id not in YONETICI_IDLERI:
        # Link
        if "http" in message.content or "discord.gg" in message.content:
            await message.delete()
            try: await message.author.timeout(timedelta(minutes=10))
            except: pass
            return

        # Spam
        now = time.time()
        uid = message.author.id
        if uid not in user_messages: user_messages[uid] = []
        user_messages[uid].append(now)
        user_messages[uid] = [t for t in user_messages[uid] if now - t < 5]
        if len(user_messages[uid]) >= 4:
            await message.delete()
            try: await message.author.timeout(timedelta(minutes=10))
            except: pass
            return

    await bot.process_commands(message)

# --- SESSİZ KORUMA (ANTI-NUKE) ---
@bot.event
async def on_guild_channel_delete(channel):
    async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
        if entry.user.id in YONETICI_IDLERI: return
        await channel.category.create_text_channel(name=channel.name, overwrites=channel.overwrites)
        await patrona_rapor_ver(f"🛡️ **Kanal Koruma:** {entry.user.mention} isimli kişi `{channel.name}` kanalını sildi, anında geri açtım.")

@bot.event
async def on_member_join(member):
    kanal = bot.get_channel(GIRIS_KANAL_ID)
    if kanal: 
        await kanal.send(f"Hoş geldin {member.mention}\nİsim:\nGeliş Sebebim:\nEtiket: <@1001441485901807688>")

keep_alive()
bot.run(TOKEN)