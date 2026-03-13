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
    "Grubun düzenli kalması ve herkesin adil şekilde etkileşim alabilmesi için birkaç basit kuralımız var:\n"
    "🔹 Takip: Gruptaki üyelerin birbirini takip etmesi gerekiyor.\n"
    "🔹 Günlük paylaşım: Günde en fazla 2 gönderi paylaşabilirsiniz.\n"
    "🔹 Etkileşim şekli: Beğeni + Kaydet ve en az 4–5 kelimelik anlamlı yorum şarttır.\n"
    "🔹 Liste sistemi: /liste yazdığınızda güncel linkler size DM olarak gönderilir.\n\n"
    "⚠️ Not: Listeyi kullanabilmek için önce botu başlatmalısınız."
)

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

# --- VERİ İŞLEMLERİ ---
def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            # Eksik anahtarları tamamla
            for k in ["users", "waiting", "daily_links", "last_seen"]: d.setdefault(k, {}) if k != "daily_links" else d.setdefault(k, [])
            return d
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- GECE 02:00 SIFIRLAMA GÖREVİ ---
async def daily_reset(context: ContextTypes.DEFAULT_TYPE):
    data = {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}
    save_data(data)

# --- SERVİS MESAJLARI VE DM (KUSURSUZ TEMİZLİK) ---
async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message: return

    # Yeni üye geldiyse DM at
    if message.new_chat_members:
        for new_user in message.new_chat_members:
            if not new_user.is_bot:
                try:
                    welcome_dm = f"👋 Merhaba {new_user.first_name}, hoş geldin!\n\nLinkleri alabilmek için önce beni buradan BAŞLAT (START) demen gerekiyor.\nGünlük limit: 2 Link.\nİyi etkileşimler!"
                    await context.bot.send_message(chat_id=new_user.id, text=welcome_dm)
                except: pass
    
    # "Katıldı", "Ayrıldı", "İsteğiniz onaylandı" gibi TÜM servis mesajlarını sil
    try: await message.delete()
    except: pass

# --- ADMİN ÖZEL İSTATİSTİK ---
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]: return
    try: await update.message.delete()
    except: pass
    
    data = load_data(); users = data.get("users", {})
    if not users:
        await context.bot.send_message(chat_id=update.effective_user.id, text="📊 Henüz işlem yok.")
        return
    
    rapor = "📊 **GÜNLÜK TAKİP RAPORU** 📊\n\n"
    for uid, info in users.items():
        rapor += f"👤 @{info.get('username', 'Bilinmiyor')}: {info.get('links', 0)} Link - {info.get('list_count', 0)} Liste\n"
    await context.bot.send_message(chat_id=update.effective_user.id, text=rapor)

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
        
        # ADMIN: Sınırsız + Maskeleme
        if is_admin:
            try: await message.delete()
            except: pass
            data["daily_links"].append(text); save_data(data)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{text}")
            return

        # ÜYE: Limit Kontrolü
        user_info = data["users"].get(uid, {"links": 0})
        if user_info["links"] >= 2 or uid in data["waiting"]:
            try: await message.delete()
            except: pass
            return

        # Onay Süreci
        data["waiting"][uid] = text; save_data(data)
        try: await message.delete()
        except: pass
        
        keyboard = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
        waiting_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🚨 Bekle! Destek vermelisin.\n🔗 Linkin: {text}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
        context.job_queue.run_once(lambda ctx: waiting_msg.delete(), when=WAITING_DELETE)
    else:
        # Link değilse ve Admin değilse ŞAK diye sil
        if not is_admin:
            try: await message.delete()
            except: pass

# --- CALLBACK (BUTON ONAYI) ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; target_uid = query.data.split("_")[1]
    if str(query.from_user.id) != target_uid: return
    
    data = load_data(); link = data["waiting"].get(target_uid)
    if not link: return
    
    if target_uid not in data["users"]: data["users"][target_uid] = {"username": query.from_user.username or query.from_user.first_name, "links": 0, "list_count": 0}
    data["users"][target_uid]["links"] += 1
    data["daily_links"].append(link)
    del data["waiting"][target_uid]; save_data(data)
    await query.edit_message_text(text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{link}")

# --- KOMUTLAR ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        if member.status not in ["administrator", "creator"]:
            try: await update.message.delete()
            except: pass
            return
        
        # Döngüyü kur
        chat_id = update.effective_chat.id
        jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for j in jobs: j.schedule_removal()
        context.job_queue.run_repeating(lambda ctx: ctx.bot.send_message(chat_id=chat_id, text=RULES_TEXT), interval=REMIND_INTERVAL, first=10, name=str(chat_id))
        
        info = await update.message.reply_text("✅ Bot aktif edildi.")
        await asyncio.sleep(5); await info.delete()
    else:
        await update.message.reply_text("👋 Bot aktif! Grupta /liste yazarak linkleri alabilirsin.")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.delete()
    except: pass
    user = update.effective_user; uid = str(user.id); data = load_data()
    
    if uid not in data["users"]: data["users"][uid] = {"username": user.username or user.first_name, "links": 0, "list_count": 0}
    data["users"][uid]["list_count"] = data["users"][uid].get("list_count", 0) + 1
    save_data(data)
    
    links = data.get("daily_links", [])
    if not links: return
    
    res = "🚀 GÜNCEL LİSTE 🚀\n\n" + "\n".join([f"{i+1}. {l}" for i, l in enumerate(links)])
    try:
        await context.bot.send_message(chat_id=user.id, text=res, disable_web_page_preview=True)
    except:
        m = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ @{user.username} Önce botu başlatmalısın!")
        await asyncio.sleep(5); await m.delete()

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Gece 02:00 Reset Görevi
    app.job_queue.run_daily(daily_reset, time=datetime.time(hour=2, minute=0, tzinfo=TR_TIMEZONE))
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("liste", list_command))
    app.add_handler(CommandHandler("hepsi", admin_stats))
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service_messages))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    app.run_polling()

if __name__ == "__main__":
    main()
