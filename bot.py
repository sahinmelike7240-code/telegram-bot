import json, os, re, asyncio
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

# --- AYARLAR ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_stats.json"
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')

REMIND_INTERVAL = 7200  # 2 saat
DELETE_AFTER = 300      # 5 dakika

# --- SENİN İSTEDİĞİN YENİ KURAL METNİ ---
RULES_TEXT = (
    "🚀 X Etkileşim Grubu Kuralları\n\n"
    "Grubun düzenli kalması ve herkesin adil şekilde etkileşim almasını sağlamak için birkaç basit kuralımız var:\n\n"
    "🔹 Takip:\n"
    "Gruptaki üyelerin birbirini takip etmesi gerekiyor. Takibi bırakan hesaplar tespit edilirse gruptan çıkarılabilir.\n\n"
    "🔹 Günlük paylaşım:\n"
    "Herkesin eşit faydalanabilmesi için günde en fazla 2 gönderi paylaşabilirsiniz.\n\n"
    "🔹 Etkileşim şekli:\n"
    "Paylaşılan gönderilere Beğeni + Kaydet yapıp en az 4–5 kelimelik anlamlı bir yorum bırakılması gerekiyor.\n"
    "(Sadece emoji veya tek kelimelik yorumlar sayılmıyor.)\n\n"
    "🔹 Liste sistemi:\n"
    "Gruba /liste yazdığınızda, sabah 08:00 ile gece 02:00 arasında grupta paylaşılan tüm gönderiler size özel mesaj olarak gönderilir.\n\n"
    "⚠️ Not:\n"
    "Listeyi kullanabilmek için önce Telegram’da @xlinkkontrol_bot hesabını bulup Başlat (Start) demeniz gerekiyor.\n\n"
    "Herkes kurallara uyarsa hem düzen korunur hem de etkileşimler çok daha verimli olur. 🙌\n"
    "━━━━━━━━━━━━━━━\n"
    "⏰ Bu bilgilendirme 5 dakika içinde gruptan kaldırılacaktır."
)

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

# --- VERİ İŞLEMLERİ ---
def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}, "last_reset": ""}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- SERVİS MESAJLARINI SİL (YENİ EK) ---
async def delete_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.delete()
    except: pass

# --- KURALLAR DÖNGÜSÜ ---
async def remind_rules(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    msg = await context.bot.send_message(chat_id=job.chat_id, text=RULES_TEXT)
    await asyncio.sleep(DELETE_AFTER)
    await msg.delete()

# --- KOMUTLAR ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    # Admin kontrolü
    member = await context.bot.get_
