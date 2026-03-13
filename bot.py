import json, os, re, asyncio, datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

# --- AYARLAR ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_stats.json"
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')

REMIND_INTERVAL = 7200
DELETE_AFTER = 300
WAITING_DELETE = 60

RULES_TEXT = (
    "🚀 X Etkileşim Grubu Kuralları\n\n"
    "Grubun düzenli kalması için kurallarımız:\n"
    "🔹 Takip: Üyeler birbirini takip etmelidir.\n"
    "🔹 Günlük Limit: Günde en fazla 2 gönderi paylaşılabilir.\n"
    "🔹 Etkileşim: Beğeni + Kaydet ve anlamlı yorum şarttır.\n"
    "🔹 Liste: /liste yazarak linkleri DM alabilirsiniz.\n"
)

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

# --- VERİ İŞLEMLERİ ---
def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- SIFIRLAMA GÖREVİ ---
async def daily_reset(context: ContextTypes.DEFAULT_TYPE):
    data = {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}
    save_data(data)

# --- SERVİS MESAJLARI VE DM ---
async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.new_chat_members:
        for new_user in update.message.new_chat_members:
            if not new_user.is_bot:
                try:
                    welcome_dm = f"👋 Merhaba {new_user.first_name}!\nSistemi kullanmak için önce beni buradan BAŞLAT demelisin.\n\nGünlük 2 link hakkın var. İyi etkileşimler!"
                    await context.bot.send_message(chat_id=new_user.id, text=welcome_dm)
                except: pass
    try: await update.message.delete()
    except: pass

# --- DİĞER FONKSİYONLAR (ADMİN, LİSTE, HANDLE) ---
# (Geceki stabil fonksiyonların aynısı korunmuştur)

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]: return
    data = load_data(); users = data.get("users", {})
    rapor = "📊 GÜNLÜK RAPOR\n"
    for uid, info in users.items():
        rapor += f"👤 @{info.get('username')}: {info.get('links')} Link - {info.get('list_count')} Liste\n"
    await context.bot.send_message(chat_id=update.effective_user.id, text=rapor)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    text = message.text.strip()
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    is_admin = member.status in ["administrator", "creator"]

    if tweet_regex.match(text):
        data = load_data()
        if is_admin:
            try: await message.delete()
            except: pass
            data.setdefault("daily_links", []).append(text); save_data(data)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ Admin Paylaşımı:\n{text}")
            return
        # Üye kontrolü... (Buradaki yapı aynı)
    else:
        if not is_admin: await message.delete()

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Zamanlayıcıları kur
    app.job_queue.run_daily(daily_reset, time=datetime.time(hour=2, minute=0, tzinfo=TR_TIMEZONE))
    
    app.add_handler(CommandHandler("hepsi", admin_stats))
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service_messages))
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
