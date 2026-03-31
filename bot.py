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
    "🔹 Limit: Günde en fazla 2 gönderi paylaşılabilir.\n"
    "🔹 Etkileşim: Beğeni + Kaydet ve anlamlı yorum şarttır.\n"
    "🔹 Liste: /liste yazarak linkleri DM alabilirsiniz."
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

# --- GÖREVLER (SIFIRLAMA VE KURAL) ---
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
    if update.effective_chat.type != "private":
        try: await update.message.delete()
        except: pass
        member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        if member.status in ["administrator", "creator"]:
            if user_id not in data["admins"]: data["admins"].append(user_id); save_data(data)
            rapor = "📊 **GÜNLÜK TAKİP RAPORU** 📊\n\n"
            for uid, info in data["users"].items():
                rapor += f"👤 @{info.get('username')}: {info.get('links')} Link - {info.get('list_count')} Liste\n"
            try: await context.bot.send_message(chat_id=user_id, text=rapor)
            except: pass
        return
    if user_id in data.get("admins", []):
        rapor = "📊 **GÜNLÜK TAKİP RAPORU** 📊\n\n"
        for uid, info in data["users"].items():
            rapor += f"👤 @{info.get('username')}: {info.get('links')} Link - {info.get('list_count')} Liste\n"
        await update.message.reply_text(rapor)

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.effective_chat.type != "private":
        try: await update.message.delete()
        except: pass
    data = load_data(); links = data.get("daily_links", [])
    try:
        if not links: await context.bot.send_message(chat_id=user.id, text="⚠️ Henüz paylaşılmış link yok.")
        else:
            res = "🚀 GÜNCEL LİSTE 🚀\n\n" + "\n".join([f"{i+1}. {l}" for i, l in enumerate(links)])
            await context.bot.send_message(chat_id=user.id, text=res, disable_web_page_preview=True)
            u_id = str(user.id)
            u_info = data["users"].setdefault(u_id, {"username": user.username or user.first_name, "links": 0, "list_count": 0})
            u_info["list_count"] += 1; save_data(data)
    except:
        if update.effective_chat.type != "private":
            m = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ @{user.username} Önce botu başlatmalısın!")
            await asyncio.sleep(5); await m.delete()

# --- MESAJ İŞLEME ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    user = update.effective_user; text = message.text.strip()
    if update.effective_chat.type == "private": return

    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin = member.status in ["administrator", "creator"]

    # Eğer adminden gelen normal mesajsa dokunma (Konuşabilsin)
    if is_admin and not tweet_regex.match(text):
        if user.id not in load_data()["admins"]:
            d = load_data(); d["admins"].append(user.id); save_data(d)
        return

    if tweet_regex.match(text):
        data = load_data(); uid = str(user.id)
        try: await message.delete()
        except: pass
        if is_admin:
            data["daily_links"].append(text); save_data(data)
            sent = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Yorum Beğeni Ve Kaydet yapıldı**\n\n{text}")
            data.setdefault("msg_map", {}).setdefault(uid, []).append(sent.message_id); save_data(data)
            return
        
        u_info = data["users"].get(uid, {"links": 0})
        if u_info["links"] >= 2: return
        data["waiting"][uid] = text; save_data(data)
        kb = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
        w_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🚨 Bekle! Destek vermelisin.\n🔗 Linkin: {text}", reply_markup=InlineKeyboardMarkup(kb))
        context.job_queue.run_once(lambda ctx: w_msg.delete() if uid in load_data()["waiting"] else None, when=WAITING_DELETE)
    else:
        # Üye link harici bir şey yazarsa (komutlar dahil) sil
        if not is_admin:
            try: await message.delete()
            except: pass

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; uid = query.data.split("_")[1]
    if str(query.from_user.id) != uid:
        await query.answer("⚠️ Sadece kendi linkini onaylayabilirsin!", show_alert=True)
        return
    data = load_data(); link = data["waiting"].get(uid)
    if not link: return
    try: await query.message.delete()
    except: pass
    u_info = data["users"].setdefault(uid, {"username": query.from_user.username or query.from_user.first_name, "links": 0, "list_count": 0})
    u_info["links"] += 1; data["daily_links"].append(link)
    sent = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{link}")
    data.setdefault("msg_map", {}).setdefault(uid, []).append(sent.message_id)
    del data["waiting"][uid]; save_data(data)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    jq = app.job_queue
    jq.run_daily(daily_reset, time=datetime.time(hour=2, minute=0, tzinfo=TR_TIMEZONE))
    
    # 18:00 Kural Hatırlatıcı (ID kısmını kendi grubunla değiştir)
    jq.run_daily(send_rules_job, time=datetime.time(hour=18, minute=0, tzinfo=TR_TIMEZONE), chat_id=-1002361730040)
    
    app.add_handler(CommandHandler("liste", list_command))
    app.add_handler(CommandHandler("hepsi", hepsi_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, clean_status_updates))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()

