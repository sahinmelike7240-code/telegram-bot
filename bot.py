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

# --- YENİ SADE KURALLAR METNİ ---
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
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}, "last_reset": ""}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- SERVİS MESAJLARI (KATILDI/AYRILDI) ---
async def delete_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.delete()
    except: pass

# --- ZAMANLANMIŞ GÖREV ---
async def remind_rules(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    try:
        msg = await context.bot.send_message(chat_id=job.chat_id, text=RULES_TEXT)
        await asyncio.sleep(DELETE_AFTER)
        await msg.delete()
    except: pass

# --- ANA MESAJ YÖNETİMİ ---
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message: return
    
    chat_id = update.effective_chat.id
    user = update.effective_user
    text = message.text or ""
    
    # Yönetici mi kontrol et
    member = await context.bot.get_chat_member(chat_id, user.id)
    is_admin = member.status in ["administrator", "creator"]

    # 1. Komut Kontrolü
    if text.startswith("/"):
        if text.startswith(("/start", "/liste")): return # Bunları CommandHandler işlesin
        if not is_admin:
            try: await message.delete()
            except: pass
        return

    # 2. X Link Kontrolü
    if tweet_regex.match(text):
        data = load_data()
        
        # ADMIN: Sınırsız paylaşım + Bot kimliğiyle paylaşım
        if is_admin:
            try: await message.delete()
            except: pass
            data["daily_links"].append(text)
            save_data(data)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{text}",
                disable_web_page_preview=False
            )
            return

        # ÜYE: 2 Link sınırı ve Onay süreci
        uid = str(user.id)
        if data.get("users", {}).get(uid, {}).get("links", 0) >= 2 or uid in data["waiting"]:
            try: await message.delete()
            except: pass
            return

        data["waiting"][uid] = text
        save_data(data)
        try: await message.delete()
        except: pass
        
        keyboard = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🚨 Bekle!\n\nLinkinin paylaşılması için gruptaki son linklere destek vermelisin.\n\n🔗 Senin Linkin: {text}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
    else:
        # Link değilse ve Admin değilse SİL (ESKİ SİSTEM)
        if not is_admin:
            try: await message.delete()
            except: pass

# --- KOMUTLAR ---
async def
