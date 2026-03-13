import json, os, re, asyncio
from datetime import datetime
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
    "Grubun düzenli kalması ve herkesin adil şekilde etkileşim almasını sağlamak için birkaç basit kuralımız var:\n"
    "🔹 Takip:\n"
    "Gruptaki üyelerin birbirini takip etmesi gerekiyor. Takibi bırakan hesaplar tespit edilirse gruptan çıkarılabilir.\n"
    "🔹 Günlük paylaşım:\n"
    "Herkesin eşit faydalanabilmesi için günde en fazla 2 gönderi paylaşabilirsiniz.\n"
    "🔹 Etkileşim şekli:\n"
    "Paylaşılan gönderilere Beğeni + Kaydet yapıp en az 4–5 kelimelik anlamlı bir yorum bırakılması gerekiyor.\n"
    "🔹 Liste sistemi:\n"
    "Gruba /liste yazdığınızda, sabah 08:00 ile gece 02:00 arasında paylaşılan tüm gönderiler size özel mesaj olarak gönderilir.\n\n"
    "⚠️ Not:\n"
    "Listeyi kullanabilmek için önce Telegram’da @xlinkkontrol_bot hesabını bulup Başlat (Start) demeniz gerekiyor.\n"
)

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

# --- VERİ İŞLEMLERİ ---
def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}, "last_reset": ""}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            d.setdefault("users", {}); d.setdefault("last_seen", {}); d.setdefault("daily_links", []); d.setdefault("waiting", {})
            return d
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}, "last_reset": ""}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private": return True
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return member.status in ["administrator", "creator"]

# --- YENİ: ADMİN ÖZEL İSTATİSTİK KOMUTU ---
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update, context): return # Sadece sen görebilirsin
    
    try: await update.message.delete()
    except: pass
    
    data = load_data()
    users = data.get("users", {})
    
    if not users:
        await context.bot.send_message(chat_id=update.effective_user.id, text="📊 Henüz bugün işlem yapan kimse yok.")
        return

    rapor = "📊 **GÜNLÜK TAKİP RAPORU** 📊\n\n"
    rapor += "Kullanıcı | Link | Liste Talebi\n"
    rapor += "--------------------------\n"
    
    for uid, info in users.items():
        username = info.get("username", "Bilinmiyor")
        links = info.get("links", 0)
        lists = info.get("list_count", 0)
        rapor += f"👤 @{username}: {links} Link - {lists} Liste\n"

    await context.bot.send_message(chat_id=update.effective_user.id, text=rapor)

# --- DİĞER KOMUTLAR ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        if not await is_user_admin(update, context):
            try: await update.message.delete()
            except: pass
            return
        # Admin Başlatınca
        chat_id = update.effective_chat.id
        jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for j in jobs: j.schedule_removal()
        context.job_queue.run_repeating(lambda ctx: ctx.bot.send_message(chat_id=chat_id, text=RULES_TEXT), interval=REMIND_INTERVAL, first=10)
    else:
        await update.message.reply_text("👋 Bot aktif!")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.delete()
    except: pass
    user = update.effective_user
    uid = str(user.id)
    data = load_data()
    
    # Liste sayısını kaydet (Takip için)
    if uid not in data["users"]: data["users"][uid] = {"username": user.username or user.first_name, "links": 0, "list_count": 0}
    data["users"][uid]["list_count"] = data["users"][uid].get("list_count", 0) + 1
    save_data(data)
    
    links = data.get("daily_links", [])
    if not links: return
    
    res = "🚀 GÜNCEL LİSTE 🚀\n\n" + "\n".join([f"{i+1}. {l}" for i, l in enumerate(links)])
    try:
        await context.bot.send_message(chat_id=user.id, text=res, disable_web_page_preview=True)
    except:
        m = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ @{user.username} Botu başlatmalısın!")
        await asyncio.sleep(5); await m.delete()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    user = update.effective_user
    text = message.text.strip()
    is_admin = await is_user_admin(update, context)

    if tweet_regex.match(text):
        data = load_data()
        if is_admin:
            try: await message.delete()
            except: pass
            data["daily_links"].append(text); save_data(data)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{text}")
            return

        uid = str(user.id)
        if data["users"].get(uid, {}).get("links", 0) >= 2:
            try: await message.delete()
            except: pass
            return
        
        data["waiting"][uid] = text; save_data(data)
        try: await message.delete()
        except: pass
        
        keyboard = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
        waiting_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🚨 Bekle!\n\nLinkinin paylaşılması için destek vermelisin.\n\n🔗 Senin Linkin: {text}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
        context.job_queue.run_once(lambda ctx: waiting_msg.delete(), when=WAITING_DELETE)
    else:
        if not is_admin:
            try: await message.delete()
            except: pass

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; target_uid = query.data.split("_")[1]
    if str(query.from_user.id) != target_uid: return
    
    data = load_data(); link = data["waiting"].get(target_uid)
    if not link: return
    
    user_info = data["users"].get(target_uid, {"username": query.from_user.username or query.from_user.first_name, "links": 0, "list_count": 0})
    user_info["links"] += 1
    data["users"][target_uid] = user_info
    data["daily_links"].append(link)
    del data["waiting"][target_uid]; save_data(data)
    await query.edit_message_text(text=f"✅ Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım\n\n{link}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("liste", list_command))
    app.add_handler(CommandHandler("hepsi", admin_stats)) # YENİ KOMUT
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, lambda u, c: u.message.delete()))
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
