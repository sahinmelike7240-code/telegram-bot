import json
import os
import re
import asyncio
from datetime import datetime, time
import pytz # Saat dilimi için

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
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')

tweet_regex = re.compile(
    r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$",
    re.IGNORECASE,
)

def load_data():
    if not os.path.exists(DATA_FILE): return {"daily_users": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"daily_users": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def daily_reset(context: ContextTypes.DEFAULT_TYPE):
    save_data({"daily_users": {}})
    if GROUP_ID:
        await context.bot.send_message(chat_id=GROUP_ID, text="🌙 **Grup Mesaisi Bitmiştir.** Günlük limitler sıfırlandı. Sabah 08:00'de görüşmek üzere!")

async def send_rules_periodically(context: ContextTypes.DEFAULT_TYPE):
    if GROUP_ID:
        rules_text = (
            "📢 **KURAL HATIRLATMASI**\n\n"
            "▪️ Takip zorunludur!\n"
            "▪️ Günde 2 link hakkı (08:00 - 02:00 arası).\n"
            "▪️ Önceki linklere yorum/beğeni/kaydetme şart.\n"
            "▪️ Küfür ve alakasız sohbet yasaktır."
        )
        await context.bot.send_message(chat_id=GROUP_ID, text=rules_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GROUP_ID
    GROUP_ID = update.effective_chat.id
    message = update.message
    user = update.effective_user
    if not message or not user: return

    # Admin muafiyeti
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    if member.status in ["administrator", "creator"]: return

    # Türkiye saatine göre kontrol
    now = datetime.now(TR_TIMEZONE)
    if 2 <= now.hour < 8:
        try: await message.delete()
        except: pass
        warn = await message.reply_text(f"😴 @{user.username} Grup kapalı. 08:00'de açılacaktır.")
        await asyncio.sleep(5)
        await warn.delete()
        return

    text = (message.text or "").strip()
    if not tweet_regex.match(text):
        try: await message.delete()
        except: pass
        return

    data = load_data()
    user_id = str(user.id)
    user_count = data["daily_users"].get(user_id, 0)

    if user_count >= 2:
        try: await message.delete()
        except: pass
        warn = await message.reply_text(f"⚠️ @{user.username} Günlük 2 limitin doldu!")
        await asyncio.sleep(5)
        await warn.delete()
        return

    data["daily_users"][user_id] = user_count + 1
    save_data(data)
    
    rem = await message.reply_text(f"✅ @{user.username} Linkin alındı ({user_count + 1}/2).")
    await asyncio.sleep(10)
    try: await rem.delete()
    except: pass

def main():
    if not BOT_TOKEN: return
    # JobQueue desteğiyle uygulamayı kur
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Zamanlayıcıları kur
    jq = app.job_queue
    jq.run_repeating(send_rules_periodically, interval=14400, first=10)
    jq.run_daily(daily_reset, time=time(2, 1, tzinfo=TR_TIMEZONE))
    
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("Bot başlatıldı...")
    app.run_polling()

if __name__ == "__main__":
    main()
