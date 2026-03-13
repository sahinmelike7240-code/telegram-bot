import json, os, re, asyncio, datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

# --- AYARLAR ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_stats.json"
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')

REMIND_INTERVAL = 7200
WAITING_DELETE = 60

# Senin o meşhur uzun kuralların, tek bir harfine dokunulmadı
RULES_TEXT = (
    "🚀 X Etkileşim Grubu Kuralları\n\n"
    "Grubun düzenli kalması ve herkesin adil şekilde etkileşim alabilmesi için birkaç basit kuralımız var:\n"
    "🔹 Takip:\n"
    "Gruptaki üyelerin birbirini takip etmesi gerekiyor. Takibi bırakan hesaplar tespit edilirse gruptan çıkarılabilir.\n"
    "🔹 Günlük paylaşım:\n"
    "Herkesin eşit faydalanabilmesi için günde en fazla 2 gönderi paylaşabilirsiniz.\n"
    "🔹 Etkileşim şekli:\n"
    "Paylaşılan gönderilere Beğeni + Kaydet ve en az 4–5 kelimelik anlamlı yorum bırakılması gerekiyor.\n"
    "🔹 Liste sistemi:\n"
    "Gruba /liste yazdığınızda paylaşılan tüm gönderiler size özel mesaj olarak gönderilir.\n\n"
    "⚠️ Not: Listeyi kullanabilmek için önce botu başlatmalısınız."
)

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

# --- VERİ MERKEZİ ---
def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None, "msg_map": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            for k in ["users", "waiting", "daily_links", "msg_map"]: d.setdefault(k, {} if k != "daily_links" else [])
            return d
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None, "msg_map": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- GÖREVLER ---
async def daily_reset(context: ContextTypes.DEFAULT_TYPE):
    save_data({"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None, "msg_map": {}})

async def send_rules_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_data()
    if data.get("last_rule_id"):
        try: await context.bot.delete_message(chat_id=chat_id, message_id=data["last_rule_id"])
        except: pass
    msg = await context.bot.send_message(chat_id=chat_id, text=RULES_TEXT)
    data["last_rule_id"] = msg.message_id
    save_data(data)

# --- HAİN VE SİSTEM TEMİZLİĞİ ---
async def on_user_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.left_chat_member
    if not user: return
    uid = str(user.id); data = load_data()
    if uid in data.get("msg_map", {}):
        for mid in data["msg_map"][uid]:
            try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=mid)
            except: pass
        del data["msg_map"][uid]
    patt = f"/{user.username}/status/" if user.username else "empty_user_path"
    data["daily_links"] = [l for l in data["daily_links"] if patt not in l]
    save_data(data)
    try: await update.message.delete()
    except: pass

# --- ANA AKIŞ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    user = update.effective_user; text = message.text.strip()
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin = member.status in ["administrator", "creator"]

    if tweet_regex.match(text):
        data = load_data(); uid = str(user.id)
        if is_admin: # ADMIN MASKELİ PAYLAŞIM
            try: await message.delete()
            except: pass
            data["daily_links"].append(text); save_data(data)
            sent = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Yorum Beğeni Ve Kaydet yapıldı**\n\n{text}")
            data.setdefault("msg_map", {}).setdefault(uid, []).append(sent.message_id); save_data(data)
            return
        
        u_info = data["users"].get(uid, {"links": 0})
        if u_info["links"] >= 2:
            try: await message.delete()
            except: pass
            return
            
        data["waiting"][uid] = text; save_data(data)
        try: await message.delete()
        except: pass
        kb = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
        w_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🚨 Bekle! Destek vermelisin.\n🔗 Linkin: {text}", reply_markup=InlineKeyboardMarkup(kb))
        context.job_queue.run_once(lambda ctx: w_msg.delete(), when=WAITING_DELETE, name=f"del_{w_msg.message_id}")
    elif not is_admin:
        try: await message.delete()
        except: pass

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; uid = query.data.split("_")[1]
    if str(query.from_user.id) != uid: return
    data = load_data(); link = data["waiting"].get(uid)
    if not link: return
    try: await query.message.delete()
    except: pass
    for j in context.job_queue.get_jobs_by_name(f"del_{query.message.message_id}"): j.schedule_removal()
    
    u_info = data["users"].setdefault(uid, {"username": query.from_user.username, "links": 0, "list_count": 0})
    u_info["links"] += 1; data["daily_links"].append(link)
    # ESKİ RUH: O meşhur yeşil onay mesajı
    sent = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{link}")
    data.setdefault("msg_map", {}).setdefault(uid, []).append(sent.message_id)
    del data["waiting"][uid]; save_data(data)

# --- KOMUTLAR ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("👋 Bot aktif! Grupta /liste yazabilirsin.")
        return
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]:
        try: await update.message.delete()
        except: pass
        return
    chat_id = update.effective_chat.id
    for j in context.job_queue.get_jobs_by_name(str(chat_id)): j.schedule_removal()
    context.job_queue.run_repeating(send_rules_job, interval=REMIND_INTERVAL, first=1, chat_id=chat_id, name=str(chat_id))
    m = await update.message.reply_text("✅ Sistem aktif.")
    await asyncio.sleep(3); await m.delete()

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.delete()
    except: pass
    user = update.effective_user; data = load_data(); links = data.get("daily_links", [])
    if not links: return
    res = "🚀 GÜNCEL LİSTE 🚀\n\n" + "\n".join([f"{i+1}. {l}" for i, l in enumerate(links)])
    try:
        await context.bot.send_message(chat_id=user.id, text=res, disable_web_page_preview=True)
        u_info = data["users"].setdefault(str(user.id), {"username": user.username, "links": 0, "list_count": 0})
        u_info["list_count"] += 1; save_data(data)
    except:
        m = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ @{user.username} Önce botu başlatmalısın!")
        await asyncio.sleep(5); await m.delete()

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.job_queue.run_daily(daily_reset, time=datetime.time(hour=2, minute=0, tzinfo=TR_TIMEZONE))
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("liste", list_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_user_left))
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, lambda u, c: u.message.delete()))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
