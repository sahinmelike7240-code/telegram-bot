import json, os, re, asyncio, datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

# --- AYARLAR ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_stats.json"
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')

REMIND_INTERVAL = 7200  # 2 saat
WAITING_DELETE = 60     # Onaylanmayan linkler 60 saniye sonra silinir

RULES_TEXT = (
    "🚀 X Etkileşim Grubu Kuralları\n\n"
    "🔹 Takip: Üyeler birbirini takip etmelidir.\n"
    "🔹 Limit: Günde en fazla 2 gönderi paylaşılabilir.\n"
    "🔹 Etkileşim: Beğeni + Kaydet ve anlamlı yorum şarttır.\n"
    "🔹 Liste: /liste yazarak linkleri DM alabilirsiniz.\n"
)

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

# --- VERİ İŞLEMLERİ ---
def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}, "last_rule_msg": None}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            d.setdefault("last_rule_msg", None)
            return d
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}, "last_rule_msg": None}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- SIFIRLAMA GÖREVİ ---
async def daily_reset(context: ContextTypes.DEFAULT_TYPE):
    data = {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}, "last_rule_msg": None}
    save_data(data)

# --- KURALLARI TAZELEME GÖREVİ ---
async def send_rules_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_data()
    
    # Eski kural mesajı varsa sil
    if data.get("last_rule_msg"):
        try: await context.bot.delete_message(chat_id=chat_id, message_id=data["last_rule_msg"])
        except: pass
    
    # Yeni kuralı at ve ID'sini kaydet
    msg = await context.bot.send_message(chat_id=chat_id, text=RULES_TEXT)
    data["last_rule_msg"] = msg.message_id
    save_data(data)

# --- SERVİS MESAJLARI VE DM ---
async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.new_chat_members:
        for new_user in update.message.new_chat_members:
            if not new_user.is_bot:
                try:
                    welcome_dm = f"👋 Merhaba {new_user.first_name}!\nLinkleri alabilmek için önce beni buradan BAŞLAT demen gerekiyor."
                    await context.bot.send_message(chat_id=new_user.id, text=welcome_dm)
                except: pass
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
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Yorum Beğeni Ve Kaydet yapıldı**\n\n{text}")
            return

        user_info = data.setdefault("users", {}).get(uid, {"links": 0})
        if user_info["links"] >= 2 or uid in data.get("waiting", {}):
            try: await message.delete()
            except: pass
            return

        data.setdefault("waiting", {})[uid] = text
        save_data(data)
        try: await message.delete()
        except: pass
        
        keyboard = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
        waiting_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🚨 Bekle! Linkinin paylaşılması için destek vermelisin.\n🔗 Linkin: {text}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
        
        # Sadece bu bekleme mesajını 60 saniye sonra silmek için job tanımla
        context.job_queue.run_once(
            lambda ctx: asyncio.create_task(ctx.bot.delete_message(chat_id=update.effective_chat.id, message_id=waiting_msg.message_id)) if True else None, 
            when=WAITING_DELETE, 
            name=f"delete_waiting_{waiting_msg.message_id}"
        )
    else:
        if not is_admin:
            try: await message.delete()
            except: pass

# --- CALLBACK (BUTON ONAYI) ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    target_uid = query.data.split("_")[1]
    if str(query.from_user.id) != target_uid: return
    
    data = load_data()
    link = data.get("waiting", {}).get(target_uid)
    if not link: return
    
    # 1. Önce bekleme mesajını (butonu) hemen sil
    try: await query.message.delete()
    except: pass
    
    # 2. Silme görevini iptal et (Vaktinden önce onayladığı için)
    current_jobs = context.job_queue.get_jobs_by_name(f"delete_waiting_{query.message.message_id}")
    for j in current_jobs: j.schedule_removal()

    # 3. Kayıtları yap
    user_info = data.setdefault("users", {}).get(target_uid, {"username": query.from_user.username or query.from_user.first_name, "links": 0, "list_count": 0})
    user_info["links"] += 1
    data["users"][target_uid] = user_info
    data.setdefault("daily_links", []).append(link)
    del data["waiting"][target_uid]
    save_data(data)
    
    # 4. Asıl kalıcı link mesajını at (Bu silinmeyecek)
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{link}"
    )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        if member.status not in ["administrator", "creator"]: return
        
        chat_id = update.effective_chat.id
        jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for j in jobs: j.schedule_removal()
        
        # İlk kuralı hemen at ve döngüyü başlat
        context.job_queue.run_repeating(send_rules_job, interval=REMIND_INTERVAL, first=1, chat_id=chat_id, name=str(chat_id))
        
        info = await update.message.reply_text("✅ Sistem aktif edildi. Kurallar taze tutulacak.")
        await asyncio.sleep(5); await info.delete()

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.job_queue.run_daily(daily_reset, time=datetime.time(hour=2, minute=0, tzinfo=TR_TIMEZONE))
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("liste", list_command)) # list_command fonksiyonu önceki kodda var, aynen kalacak
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service_messages))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()
