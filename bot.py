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

# --- KURALLAR METNİ ---
RULES_TEXT = (
    "🚀 X Etkileşim Grubu Kuralları\n\n"
    "Grubun düzenli kalması ve herkesin adil şekilde etkileşim almasını sağlamak için birkaç basit kuralımız var:\n\n"
    "🔹 Takip:\n"
    "Gruptaki üyelerin birbirini takip etmek zorundadır. Takibi bırakan hesaplar tespit edilirse gruptan çıkarılabilir.\n\n"
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
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            if "last_seen" not in d: d["last_seen"] = {}
            if "daily_links" not in d: d["daily_links"] = []
            return d
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- SERVİS MESAJLARINI SİL (KATILDI/AYRILDI) ---
async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# --- ÖZEL ADMIN KONTROLÜ ---
async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type == "private": return True
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return member.status in ["administrator", "creator"]

# --- KOMUTLAR ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if update.effective_chat.type != "private":
        if not await is_user_admin(update, context):
            try: await update.message.delete()
            except: pass
            return 
        try: await update.message.delete()
        except: pass
        chat_id = update.effective_chat.id
        current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for j in current_jobs: j.schedule_removal()
        context.job_queue.run_repeating(remind_rules, interval=REMIND_INTERVAL, first=10, chat_id=chat_id, name=str(chat_id))
        info = await update.message.reply_text("✅ Sistem aktif! Kurallar 2 saatte bir gelecek.")
        await asyncio.sleep(5); await info.delete()
    else:
        await update.message.reply_text("👋 Merhaba! Grupta /liste yazarak güncel linkleri buradan alabilirsin.")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    try: await update.message.delete()
    except: pass
    data = load_data()
    links = data.get("daily_links", [])
    user = update.effective_user
    uid = str(user.id)
    if not links:
        m = await context.bot.send_message(chat_id=update.effective_chat.id, text="📭 Henüz onaylanmış link yok.")
        await asyncio.sleep(5); await m.delete(); return
    last_idx = data.get("last_seen", {}).get(uid, 0)
    new_links = links[last_idx:]
    if not new_links:
        try:
            info = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ @{user.username} Zaten güncelsin!")
            await asyncio.sleep(5); await info.delete()
        except: pass
    else:
        res = f"🚀 YENİ ETKİLEŞİM LİSTESİ 🚀\n\n"
        for i, l in enumerate(new_links, last_idx + 1): res += f"{i}. {l}\n"
        try:
            await context.bot.send_message(chat_id=user.id, text=res, disable_web_page_preview=True)
            data["last_seen"][uid] = len(links)
            save_data(data)
            info = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ @{user.username} Liste DM gönderildi.")
            await asyncio.sleep(5); await info.delete()
        except:
            warn = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ @{user.username} Önce botu başlatmalısın (@xlinkkontrol_bot)")
            await asyncio.sleep(7); await warn.delete()

# --- ANA MESAJ FİLTRESİ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    user = update.effective_user
    text = message.text.strip()
    is_admin = await is_user_admin(update, context)

    # 1. Komut Kontrolü
    if text.startswith("/"):
        if not is_admin and not text.startswith("/liste"):
            try: await message.delete()
            except: pass
            return
        if any(text.startswith(c) for c in ["/start", "/liste", "/kurallar"]): return

    # 2. X Link Kontrolü
    if tweet_regex.match(text):
        if is_admin:
            # ADMIN ÖZEL: Sınırsız paylaşım hakkı + Bot yanıtı
            try: await message.delete()
            except: pass
            data = load_data()
            data["daily_links"].append(text)
            save_data(data)
            # Admin link atınca botun verdiği kurumsal yanıt
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{text}",
                disable_web_page_preview=False
            )
            return

        # ÜYE LINK ATINCA: Onay süreci ve 2 link sınırı
        data = load_data()
        uid = str(user.id)
