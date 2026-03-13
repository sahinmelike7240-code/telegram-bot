import json, os, re, asyncio, datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

# --- AYARLAR ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_stats.json"
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')

REMIND_INTERVAL = 7200  # 2 saatte bir kural atar
WAITING_DELETE = 60     # Onaylanmayan linkleri 60 sn sonra siler

RULES_TEXT = (
    "🚀 X Etkileşim Grubu Kuralları\n\n"
    "🔹 Takip: Üyeler birbirini takip etmelidir.\n"
    "🔹 Limit: Günde en fazla 2 gönderi paylaşılabilir.\n"
    "🔹 Etkileşim: Beğeni + Kaydet ve anlamlı yorum şarttır.\n"
    "🔹 Liste: /liste yazarak linkleri DM alabilirsiniz.\n"
)

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

# --- VERİ YÜKLEME ---
def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            d.setdefault("last_rule_id", None)
            return d
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- KURALLARI TAZELE (ESKİYİ SİLEREK) ---
async def send_rules_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_data()
    if data.get("last_rule_id"):
        try: await context.bot.delete_message(chat_id=chat_id, message_id=data["last_rule_id"])
        except: pass
    msg = await context.bot.send_message(chat_id=chat_id, text=RULES_TEXT)
    data["last_rule_id"] = msg.message_id
    save_data(data)

# --- TÜM SİSTEM MESAJLARINI SİL ---
async def delete_system_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.delete()
    except: pass

# --- ANA MESAJ DİSİPLİNİ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    user = update.effective_user
    text = message.text.strip()
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin = member.status in ["administrator", "creator"]

    if tweet_regex.match(text):
        data = load_data()
        uid = str(user.id)
        if is_admin:
            try: await message.delete()
            except: pass
            data.setdefault("daily_links", []).append(text); save_data(data)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Link Paylaşıldı**\n\n{text}")
            return
        if data.get("users", {}).get(uid, {}).get("links", 0) >= 2:
            try: await message.delete()
            except: pass
            return
        data.setdefault("waiting", {})[uid] = text; save_data(data)
        try: await message.delete()
        except: pass
        keyboard = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
        wait_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🚨 Destek vermelisin: {text}", reply_markup=InlineKeyboardMarkup(keyboard))
        # Butonu 60 sn sonra siler, AMA onaylanan linki silmez!
        context.job_queue.run_once(lambda ctx: wait_msg.delete(), when=WAITING_DELETE, name=f"del_{wait_msg.message_id}")
    elif not is_admin:
        try: await message.delete()
        except: pass

# --- BUTON ONAYI (LİNKİ KALICI YAPAR) ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.data.split("_")[1]
    if str(query.from_user.id) != uid: return
    data = load_data(); link = data.get("waiting", {}).get(uid)
    if not link: return
    try: await query.message.delete()
    except: pass
    user_info = data.setdefault("users", {}).get(uid, {"username": query.from_user.username, "links": 0})
    user_info["links"] += 1; data["users"][uid] = user_info
    data.setdefault("daily_links", []).append(link); del data["waiting"][uid]; save_data(data)
    # Bu mesaj kalıcıdır, bot bunu ASLA silmez:
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Yorum Beğeni Ve Kaydet yapıldı**\n\n{link}")

# --- BOTU BAŞLAT ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]: return
    chat_id = update.effective_chat.id
    for j in context.job_queue.get_jobs_by_name(str(chat_id)): j.schedule_removal()
    context.job_queue.run_repeating(send_rules_job, interval=REMIND_INTERVAL, first=1, chat_id=chat_id, name=str(chat_id))
    await update.message.reply_text("✅ Sistem başarıyla kuruldu.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_system_messages))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
