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

def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None, "msg_map": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f); d.setdefault("msg_map", {}); d.setdefault("daily_links", []); return d
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None, "msg_map": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- ÜYE AYRILDIĞINDA TEMİZLİK YAP ---
async def on_user_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.left_chat_member:
        user = update.message.left_chat_member
        uid = str(user.id)
        data = load_data()
        
        # 1. Kullanıcının attığı linkleri gruptan sil
        if uid in data.get("msg_map", {}):
            for msg_id in data["msg_map"][uid]:
                try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
                except: pass
            del data["msg_map"][uid]

        # 2. Liste (daily_links) içinden o kullanıcının twitlerini çıkar
        # Kullanıcının username'ini içeren linkleri filtrele
        new_links = []
        user_pattern = f"/{user.username}/status/" if user.username else "aslında_yok_000"
        for link in data["daily_links"]:
            if user_pattern not in link:
                new_links.append(link)
        data["daily_links"] = new_links
        
        # 3. Kullanıcı bilgilerini sıfırla
        if uid in data["users"]: del data["users"][uid]
        
        save_data(data)
        
        # Ayrıldı servis mesajını sil
        try: await update.message.delete()
        except: pass

# --- ANA MESAJ DİSİPLİNİ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    user = update.effective_user; text = message.text.strip()
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin = member.status in ["administrator", "creator"]

    if tweet_regex.match(text):
        data = load_data(); uid = str(user.id)
        if is_admin:
            try: await message.delete()
            except: pass
            data["daily_links"].append(text); save_data(data)
            sent = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Link Paylaşıldı**\n\n{text}")
            # Admin mesajlarını da takibe al (Çıkarsa silinmesi için - Opsiyonel)
            data.setdefault("msg_map", {}).setdefault(uid, []).append(sent.message_id); save_data(data)
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
        context.job_queue.run_once(lambda ctx: wait_msg.delete(), when=WAITING_DELETE, name=f"del_{wait_msg.message_id}")
    elif not is_admin:
        try: await message.delete()
        except: pass

# --- BUTON ONAYI ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; uid = query.data.split("_")[1]
    if str(query.from_user.id) != uid: return
    data = load_data(); link = data.get("waiting", {}).get(uid)
    if not link: return
    try: await query.message.delete()
    except: pass
    
    user_info = data.setdefault("users", {}).get(uid, {"username": query.from_user.username, "links": 0})
    user_info["links"] += 1; data["users"][uid] = user_info
    data["daily_links"].append(link)
    
    # Kalıcı link mesajını at ve ID'sini kaydet (Çıkarsa silmek için)
    sent_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Yorum Beğeni Ve Kaydet yapıldı**\n\n{link}")
    data.setdefault("msg_map", {}).setdefault(uid, []).append(sent_msg.message_id)
    
    del data["waiting"][uid]; save_data(data)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u, c: None)) # start_command ve list_command buraya eklenmeli
    # Ayrılma kontrolü
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_user_left))
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, lambda u, c: u.message.delete()))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()
