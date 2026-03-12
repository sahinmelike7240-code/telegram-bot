import json
import os
import re
from datetime import datetime, time, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Ortam değişkeninden tokenı alıyoruz
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_data.json"

tweet_regex = re.compile(
    r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$",
    re.IGNORECASE,
)

SPAM_LIMIT = 5
SPAM_SECONDS = 60
MUTE_MINUTES = 10

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"shared_links": {}, "daily_users": {}, "pending_approvals": {}, "user_stats": {}, "spam": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"shared_links": {}, "daily_users": {}, "pending_approvals": {}, "user_stats": {}, "spam": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def current_reset_key():
    now = datetime.now()
    reset_hour = 9
    if now.time() < time(reset_hour, 0):
        base_date = now.date().toordinal() - 1
    else:
        base_date = now.date().toordinal()
    return str(base_date)

def normalize_link(text):
    text = text.strip()
    match = tweet_regex.match(text)
    if not match: return None
    text = text.replace("twitter.com", "x.com")
    if text.startswith("http://"): text = text.replace("http://", "https://", 1)
    elif not text.startswith("https://"): text = "https://" + text
    return text.split("?")[0]

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status in ["administrator", "creator"]
    except: return False

async def safe_delete(message):
    try: await message.delete()
    except: pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    if not message or not user: return
    if await is_admin(update, context): return

    data = load_data()
    reset_key = current_reset_key()
    user_id = str(user.id)

    # Temizlik ve Spam Kontrolü
    text = (message.text or "").strip()
    link = normalize_link(text)
    if not link:
        await safe_delete(message)
        return

    if link in data["shared_links"]:
        await safe_delete(message)
        return

    if user_id in data["daily_users"] and data["daily_users"][user_id].get("reset_key") == reset_key:
        await safe_delete(message)
        return

    # Paylaşım İşlemi
    data["shared_links"][link] = {"user_id": user_id, "created_at": datetime.now().isoformat(), "reset_key": reset_key}
    data["daily_users"][user_id] = {"reset_key": reset_key}
    
    if user_id not in data["user_stats"]:
        data["user_stats"][user_id] = {"name": user.full_name, "total_shares": 0}
    data["user_stats"][user_id]["total_shares"] += 1
    
    save_data(data)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    total = len(data["shared_links"])
    await update.message.reply_text(f"Toplam paylaşılan link sayısı: {total}")

def main():
    if not BOT_TOKEN:
        print("HATA: BOT_TOKEN bulunamadı!")
        return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("Bot çalışıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
