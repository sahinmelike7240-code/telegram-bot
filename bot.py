import json
import os
import re
import asyncio
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

# Ayarlar
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_data.json"
BOT_ACTIVE = True # Botun genel açık/kapalı durumu

tweet_regex = re.compile(
    r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$",
    re.IGNORECASE,
)

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"shared_links": {}, "daily_users": {}, "user_stats": {}, "whitelist": [], "blacklist": [], "settings": {"limit": 1}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"shared_links": {}, "daily_users": {}, "user_stats": {}, "whitelist": [], "blacklist": [], "settings": {"limit": 1}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def current_reset_key():
    return str(datetime.now().date().toordinal())

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status in ["administrator", "creator"]
    except: return False

async def safe_delete(message):
    try: await message.delete()
    except: pass

# --- TEMEL KOMUTLAR ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"Merhaba {user.first_name}! 🚀\n"
        "X Etkileşim Botu aktif. Kuralları öğrenmek için /rules yazabilirsin."
    )
    await update.message.reply_text(text)

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules = (
        "🚀 **X ETKİLEŞİM GRUBU KURALLARI**\n\n"
        "▪️ Herkes birbirini takip etmek zorunda.\n"
        "▪️ Günde en fazla 1 gönderi paylaşılabilir.\n"
        "▪️ Atılan her gönderiye yorum, beğeni ve kaydetme zorunludur.\n"
        "▪️ Küfür, argo, siyaset yasaktır.\n"
        "▪️ 48 saat pasif kalanlar gruptan çıkarılır.\n\n"
        "💡 *Lütfen kurallara uyalım.*"
    )
    await update.message.reply_text(rules, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **Komut Listesi**\n"
        "/rules - Kuralları gösterir\n"
        "/stats - Genel istatistik\n"
        "/top - En aktif 10 üye\n"
        "/me - Profil durumun\n"
        "/today - Bugün paylaşılanlar"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# --- YÖNETİM KOMUTLARI ---

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    try:
        new_limit = int(context.args[0])
        data = load_data()
        data["settings"]["limit"] = new_limit
        save_data(data)
        await update.message.reply_text(f"✅ Günlük link limiti {new_limit} olarak güncellendi.")
    except:
        await update.message.reply_text("Kullanım: /setlimit 2")

async def off_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    global BOT_ACTIVE
    BOT_ACTIVE = not BOT_ACTIVE
    status = "AÇIK" if BOT_ACTIVE else "KAPALI"
    await update.message.reply_text(f"🤖 Bot durumu: {status}")

# --- HOŞ GELDİN ---
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        try:
            welcome_text = (
                f"Hoş geldin {user.first_name}! 👋\n\n"
                "Kuralları okumayı unutma: /rules\n"
                "Link paylaşmadan önce önceki paylaşımlara destek ver!"
            )
            await context.bot.send_message(chat_id=user.id, text=welcome_text)
        except: pass
    await safe_delete(update.message)

# --- MESAJ İŞLEME ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not BOT_ACTIVE: return
    message = update.message
    user = update.effective_user
    if not message or not user: return
    if await is_admin(update, context): return

    data = load_data()
    user_id = str(user.id)
    
    if user_id in data["blacklist"]:
        await safe_delete(message)
        return

    text = (message.text or "").strip()
    match = tweet_regex.match(text)
    
    # Sohbet yasak: Link değilse sil
    if not match:
        await safe_delete(message)
        return

    # Link kuralları kontrolü
    reset_key = current_reset_key()
    if user_id in data["daily_users"] and data["daily_users"][user_id] == reset_key and user_id not in data["whitelist"]:
        await safe_delete(message)
        # Uyarı mesajı (5 saniye sonra silinir)
        warn = await message.reply_text(f"⚠️ @{user.username} Günlük limitine ulaştın!")
        await asyncio.sleep(5)
        await safe_delete(warn)
        return

    # Kayıt
    data["daily_users"][user_id] = reset_key
    if user_id not in data["user_stats"]:
        data["user_stats"][user_id] = {"name": user.full_name, "count": 0}
    data["user_stats"][user_id]["count"] += 1
    save_data(data)

    # Hatırlatma
    rem = await message.reply_text(f"✅ @{user.username} Paylaşıldı! Lütfen önceki linklere destek ver.")
    await asyncio.sleep(10)
    await safe_delete(rem)

# --- STATS & TOP ---
async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    stats = data.get("user_stats", {})
    sorted_stats = sorted(stats.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
    
    text = "🏆 **En Çok Paylaşım Yapanlar**\n\n"
    for i, (uid, info) in enumerate(sorted_stats, 1):
        text += f"{i}. {info['name']} - {info['count']} paylaşım\n"
    await update.message.reply_text(text, parse_mode="Markdown")

def main():
    if not BOT_TOKEN: return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("rules", rules_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("off", off_on_command))
    app.add_handler(CommandHandler("on", off_on_command))
    app.add_handler(CommandHandler("setlimit", set_limit))
    
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("Fenomen Botu Aktif!")
    app.run_polling()

if __name__ == "__main__":
    main()
