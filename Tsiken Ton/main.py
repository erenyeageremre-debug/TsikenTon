from keep_alive import keep_alive
import discord
from discord.ext import commands
import time
from datetime import timedelta
import aiohttp
import urllib.parse
import google.generativeai as genai
import asyncio

# ================= AYARLAR =================
import os
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_KEY')
LOG_KANAL_ID = 1491524991349690430
KELIME_OYUN_ID = 1491525352986513448
GIRIS_KANAL_ID = 1470880011840917555
YONETICI_IDLERI = [1001441485901807688, 1453087302330093669] 

# ================= YAPAY ZEKA =================
genai.configure(api_key=GEMINI_API_KEY)

sistem_karakteri = "Senin adın Tsiken Ton. Sıradan, harbi ve net bir Discord botusun. Asla 'ben bu sunucunun korumasıyım', 'Vanguard'ım', 'sistem devrede' gibi cringe triplere girme. 'Ne var' gibi ukala tripler de atma. Biri sana 'Vanguard mısın', 'koruma mısın' falan sorarsa umursama, 'boş yapma' de geç. Gerekirse küfür ve argo kullanabilirsin, rahat ol. Robot gibi 'size nasıl yardımcı olabilirim' deme. Cevapların kısa, düz insan gibi olsun. Sadece Türkçe konuş."

uygun_model_adi = None
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            if '1.5' in m.name:
                uygun_model_adi = m.name
                break
            elif uygun_model_adi is None:
                uygun_model_adi = m.name
except Exception as e:
    print(f"API Tarama Hatası: {e}")

model = None
if uygun_model_adi:
    if '1.5' in uygun_model_adi:
        model = genai.GenerativeModel(model_name=uygun_model_adi, system_instruction=sistem_karakteri)
    else:
        model = genai.GenerativeModel(model_name=uygun_model_adi)

# ================= DİSCORD KURULUMU =================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

son_kelime = "elma"
son_kisi_id = None
kontrol_ediliyor = False
islem_takibi = {}
user_messages = {}

def tr_lower(text):
    return text.replace('I', 'ı').replace('İ', 'i').lower()

@bot.event
async def on_ready():
    print("----------------------------------------")
    print(f"[{bot.user.name}] AKTİF.")
    if uygun_model_adi:
        print(f"[YAPAY ZEKA] {uygun_model_adi} bağlandı.")
    print("----------------------------------------")
    
    kanal = bot.get_channel(KELIME_OYUN_ID)
    if kanal:
        embed = discord.Embed(
            title="Kelime Oyunu",
            description=f"Başlangıç kelimemiz: **{son_kelime}**\n\nKurallar:\n- Bir önceki kelimenin son harfiyle başlayan bir kelime yazılmalıdır.\n- Sadece TDK'da geçerli olan kelimeler kabul edilir.\n- Aynı kişi üst üste kelime yazamaz.\n- Kural dışı kelimeler silinir.",
            color=0x2b2d31
        )
        try:
            await kanal.send(embed=embed)
        except:
            pass

# --- YENİ GELENLERE KARŞILAMA (KAYIT FORMU) ---
@bot.event
async def on_member_join(member):
    kanal = bot.get_channel(GIRIS_KANAL_ID)
    if kanal:
        mesaj = (
            f"Sunucuya hoş geldin {member.mention}\n"
            "İsim:\n"
            "Geliş Sebebim:\n"
            "Nereden geldim:\n"
            "Etiket: <@1001441485901807688>"
        )
        try:
            await kanal.send(mesaj)
        except Exception as e:
            print(f"Karşılama mesajı atılamadı: {e}")

@bot.event
async def on_message(message):
    global son_kelime, son_kisi_id, kontrol_ediliyor

    if message.author.bot:
        return

    # --- BOT SOHBET SİSTEMİ ---
    if bot.user.mentioned_in(message):
        if message.channel.id == KELIME_OYUN_ID:
            return
        
        soru = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        if soru and model:
            async with message.channel.typing():
                try:
                    cevap = await asyncio.to_thread(model.generate_content, soru)
                    await message.reply(cevap.text)
                except Exception as e:
                    print(f"\n[SOHBET HATASI]: {e}\n")
                    await message.reply("Şu an sistem yanıt veremiyor.")
            return

    # --- KELİME OYUNU MANTIĞI ---
    if message.channel.id == KELIME_OYUN_ID:
        if message.content.startswith('!'):
            await bot.process_commands(message)
            return

        kelime = tr_lower(message.content.strip())
        
        if kontrol_ediliyor:
            await message.delete()
            return

        kontrol_ediliyor = True
        try:
            if len(kelime.split()) > 1:
                await message.delete()
                return

            if message.author.id == son_kisi_id:
                await message.add_reaction('❌')
                uyari = await message.channel.send(f"{message.author.mention}, üst üste yazamazsın.")
                await message.delete(delay=3)
                await uyari.delete(delay=3)
                return

            beklenen_harf = son_kelime[-1]

            if not kelime.startswith(beklenen_harf):
                await message.add_reaction('❌')
                uyari = await message.channel.send(f"{message.author.mention}, kelime '{beklenen_harf}' harfi ile başlamalı.")
                await message.delete(delay=3)
                await uyari.delete(delay=3)
                return

            aranacak = urllib.parse.quote(kelime)
            async with aiohttp.ClientSession() as session:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
                async with session.get(f"https://sozluk.gov.tr/gts?ara={aranacak}", headers=headers) as resp:
                    if resp.status == 200:
                        try:
                            veri = await resp.json()
                            if isinstance(veri, dict) and "error" in veri:
                                await message.add_reaction('❌')
                                uyari = await message.channel.send(f"{message.author.mention}, bu kelime TDK'da yok.")
                                await message.delete(delay=3)
                                await uyari.delete(delay=3)
                                return
                        except:
                            pass

            son_kelime = kelime
            son_kisi_id = message.author.id
            await message.add_reaction('✅')
            
        finally:
            kontrol_ediliyor = False
            
        return

    # --- SESSİZ İNFAZ & KORUMA ---
    if message.author.id in YONETICI_IDLERI:
        await bot.process_commands(message)
        return

    if "http" in message.content or "discord.gg" in message.content:
        await message.delete()
        try:
            await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=10))
        except: pass
        return

    author_id = message.author.id
    now = time.time()
    if author_id not in user_messages: user_messages[author_id] = []
    user_messages[author_id].append(now)
    user_messages[author_id] = [t for t in user_messages[author_id] if now - t < 5]
    
    if len(user_messages[author_id]) >= 4:
        await message.delete()
        try:
            await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=10))
        except: pass
        return

    await bot.process_commands(message)

# --- KORUMA SİSTEMLERİ ---
@bot.event
async def on_member_update(before, after):
    if before.id == bot.user.id:
        alinan_roller = set(before.roles) - set(after.roles)
        if alinan_roller:
            async for entry in after.guild.audit_logs(action=discord.AuditLogAction.member_role_update, limit=1):
                if entry.target.id == bot.user.id and entry.user.id not in YONETICI_IDLERI:
                    for rol in alinan_roller:
                        try: await after.add_roles(rol)
                        except: pass
                    log = bot.get_channel(LOG_KANAL_ID)
                    if log: await log.send(f"Benden rol almaya çalıştılar. Almaya çalışan: {entry.user.mention}")

@bot.event
async def on_guild_channel_delete(channel):
    async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
        if entry.user.id in YONETICI_IDLERI: return
        await channel.category.create_text_channel(name=channel.name, overwrites=channel.overwrites)
        log = bot.get_channel(LOG_KANAL_ID)
        if log: await log.send(f"Kanal Koruması: {channel.name} silindi. Silen: {entry.user.mention}. Kanal tekrar oluşturuldu.")

@bot.event
async def on_member_remove(member):
    async for entry in member.guild.audit_logs(limit=1):
        if entry.action in [discord.AuditLogAction.kick, discord.AuditLogAction.ban]:
            u_id = entry.user.id
            now = time.time()
            if u_id not in islem_takibi: islem_takibi[u_id] = []
            islem_takibi[u_id].append(now)
            islem_takibi[u_id] = [t for t in islem_takibi[u_id] if now - t < 10]
            if len(islem_takibi[u_id]) >= 3 and u_id not in YONETICI_IDLERI:
                await entry.user.edit(roles=[])
                log = bot.get_channel(LOG_KANAL_ID)
                if log: await log.send(f"Anti-Nuke: {entry.user.mention} yetkileri alındı.")

keep_alive()
bot.run(TOKEN)