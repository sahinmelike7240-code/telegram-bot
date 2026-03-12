import json
import os
import re
import asyncio
from datetime import datetime, time
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
    CommandHandler,
)

# Ayarlar
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_data.json"
GROUP_ID = None 

# X (Twitter) Link Kontrolü
tweet_regex = re.compile(
    r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$",
    re.IGNORECASE,
)

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"daily_users": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"daily_users": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- GÜN SONU SIFIRLAMA (Gece 02:01) ---
async def daily_reset(context: ContextTypes.DEFAULT_TYPE):
    data = {"daily_users": {}} 
    save_data(data)
    if GROUP_ID:
        await context.bot.send_message(chat_id=GROUP_ID, text="🌙 **Grup Mesaisi Bitmiştir.** Günlük limitler sıfırlandı. Sabah 08:00'de görüşmek üzere!")

# --- 4 SAATTE BİR KURAL HATIRLATMA ---
async def send_rules_periodically(context: ContextTypes.DEFAULT_TYPE):
    if GROUP_ID:
        rules_text = (
            "📢 **KURAL HATIRLATMASI**\n\n"
            "▪️ Takip zorunludur! (Yönetim kontrol ediyor)\n"
            "▪️ Günde 2 link hakkı (08:00 - 02:00 arası).\n"
            "▪️ Önceki linklere yorum/beğeni/kaydetme şart.\n"
            "▪️ Küfür ve alakasız sohbet kesinlikle yasaktır."
        )
        await context.bot.send_message(chat_id=GROUP_ID, text=rules_text)

# --- KOMUTLAR ---
async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules_text = (
        "🚀 **X ETKİLEŞİM GRUBU KURALLARI**\n\n"
        "▪️ Herkes birbirini takip etmek zorunda.\n"
        "▪️ Günde en fazla 2 gönderi paylaşılabilir.\n"
        "▪️ Atılan her gönderiye yorum, beğeni ve kaydetme zorunludur.\n"
        "▪️ Küfür, argo, siyaset yasaktır.\n"
        "▪️ 48 saat pasif kalanlar gruptan çıkarılır."
    )
    await update.message.reply_text(rules_text)

# --- ANA MESAJ İŞLEME ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GROUP_ID
    GROUP_ID = update.effective_chat.id
    
    message = update.message
    user = update.effective_user
    if not message or not user: return

    # Admin muafiyeti
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    if member.status in ["administrator", "creator"]: return

    # ZAMAN KONTROLÜ (08:00 - 02:00 arası izinli)
    now_hour = datetime.now().hour
    if 2 <= now_hour < 8:
        try: await message.delete()
        except: pass
        warn = await message.reply_text(f"😴 @{user.username} Grup şu an kapalı. Paylaşımlar sabah 08:00'de başlayacaktır.")
        await asyncio.sleep(5)
        await warn.delete()
        return

    text = (message.text or "").strip()
    match = tweet_regex.match(text)
    
    # SOHBET YASAK
    if not match:
        try: await message.delete()
        except: pass
        return

    # GÜNLÜK 2 LİNK LİMİTİ
    data = load_data()
    user_id = str(user.id)
    user_count = data["daily_users"].get(user_id, 0)

    if user_count >= 2:
        try: await message.delete()
        except: pass
        warn = await message.reply_text(f"⚠️ @{user.username} Günlük 2 link hakkını zaten kullandın!")
        await asyncio.sleep(5)
        await warn.delete()
        return

    # Kayıt ve Onay
    data["daily_users"][user_id] = user_count + 1
    save_data(data)
    
    rem = await message.reply_text(f"✅ @{user.username} Linkin alındı ({user_count + 1}/2). Lütfen diğer fenomenlere destek ver!")
    
    async def del_rem():
        await asyncio.sleep(10)
        try: await rem.delete()
        except: pass
    asyncio.create_task(del_rem())

def main():
    if not BOT_TOKEN: return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    job_queue = app.job_queue
    job_queue.run_repeating(send_rules_periodically, interval=14400, first=10)
    job_queue.run_daily(daily_reset, time=time(2, 1))
    
    app.add_handler(CommandHandler("rules", rules_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("2 Link Limitli Bot Aktif!")
    app.run_polling()

if __name__ == "__main__":
    main()
