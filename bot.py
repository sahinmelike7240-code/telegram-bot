import json, os, re, asyncio, datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

# --- AYARLAR ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_stats.json"
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')
WAITING_DELETE = 60

RULES_TEXT = (
    "🚀 X Etkileşim Grubu Kuralları\n\n"
    "🔹 Takip: Üyeler birbirini takip etmelidir.\n"
    "🔹 Limit: Günde en fazla 1 gönderi paylaşabilirsiniz.\n"
    "🔹 Etkileşim: Beğeni + Kaydet ve anlamlı yorum şarttır.\n"
    "🔹 Liste: /liste yazarak linkleri DM alabilirsiniz.\n"
    "🚫 Gece 01:00 ile Sabah 08:00 arası paylaşım yasaktır."
)

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

# --- VERİ MERKEZİ ---
def load_data():
    if not os.path.exists(DATA_FILE): 
        return {"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None, "msg_map": {}, "admins": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            for k in ["users", "waiting", "daily_links", "msg_map", "admins"]: d.setdefault(k, [] if k in ["daily_links", "admins"] else {})
            return d
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None, "msg_map": {}, "admins": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- GÖREVLER ---
async def daily_reset(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    new_data = {"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": data.get("last_rule_id"), "msg_map": {}, "admins": data.get("admins", [])}
    save_data(new_data)

async def send_rules_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_data()
    if data.get("last_rule_id"):
        try: await context.bot.delete_message(chat_id=chat_id, message_id=data["last_rule_id"])
        except: pass
    msg = await context.bot.send_message(chat_id=chat_id, text=RULES_TEXT)
    data["last_rule_id"] = msg.message_id
    save_data(data)

# --- ÜYE KATILDI/ÇIKTI TEMİZLİĞİ ---
async def clean_status_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.delete()
    except: pass
    if update.message.left_chat_member:
        user = update.message.left_chat_member
        uid = str(user.id); data = load_data()
        if uid in data.get("msg_map", {}):
            for mid in data["msg_map"][uid]:
                try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=mid)
                except: pass
            del data["msg_map"][uid]
        patt = f"/{user.username}/status/" if user.username else "temp_xyz"
        data["daily_links"] = [l for l in data["daily_links"] if patt not in l]
        if uid in data["users"]: del data["users"][uid]
        save_data(data)

# --- KOMUTLAR ---
async def hepsi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_data()
    if update.effective_
