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
WAITING_DELETE = 60     # Onay butonu 60 saniye kalsın (YENİ)

# --- KURALLAR METNİ (İSTEDİĞİN GİBİ GÜNCELLENDİ) ---
RULES_TEXT = (
    "🚀 X Etkileşim Grubu Kuralları\n\n"
    "Grubun düzenli kalması ve herkesin adil şekilde etkileşim alabilmesi için birkaç basit kuralımız var:\n"
    "🔹 Takip:\n"
    "Gruptaki üyelerin birbirini takip etmesi gerekiyor. Takibi bırakan hesaplar tespit edilirse gruptan çıkarılabilir.\n"
    "🔹 Günlük paylaşım:\n"
    "Herkesin eşit faydalanabilmesi için günde en fazla 2 gönderi paylaşabilirsiniz.\n"
    "🔹 Etkileşim şekli:\n"
    "Paylaşılan gönderilere Beğeni + Kaydet yapıp en az 4–5 kelimelik anlamlı bir yorum bırakılması gerekiyor.\n"
    "(Sadece emoji veya tek kelimelik yorumlar sayılmıyor.)\n"
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
            d = json.load(f); d.setdefault("last_seen", {}); d.setdefault("daily_links", []); return d
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- SERVİS MESAJLARINI SİL (KATILDI/AYRILDI) ---
async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.delete()
    except: pass

async def remind_rules(context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = await context.bot.send_message(chat_id=context.job.chat_id, text=RULES_TEXT)
        await asyncio.sleep(DELETE_AFTER); await msg.delete()
    except: pass

async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private": return True
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
        context.job_queue.run_repeating(remind_rules, interval=REMIND_INTERVAL, first=REMIND_INTERVAL, chat_id=chat_id, name=str(chat_id))
        info = await update.message.reply_text("✅ Sistem admin tarafından aktif edildi.")
        await asyncio.sleep(5); await info.delete()
    else:
        await update.message.reply_text("👋 Merhaba! Grupta /liste yazarak güncel linkleri buradan alabilirsin.")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    data = load_data(); links = data.get("daily_links", []); user = update.effective_user; uid = str(user.id)
    try: await update.message.delete()
    except: pass
    if not links:
        m = await context.bot.send_message(chat_id=update.effective_chat.id, text="📭 Henüz onaylanmış link yok.")
        await asyncio.sleep(5); await m.delete(); return
    last_idx = data.get("last_seen", {}).get(uid, 0); new_links = links[last_idx:]
    if not new_links:
        try:
            info = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ @{user.username} Zaten güncelsin!")
            await asyncio.sleep(5); await info.delete()
        except: pass
    else:
        res = f"🚀 YENİ ETKİLEŞİM LİSTESİ 🚀\n📌 En son {last_idx}. linkte kalmıştın.\n\n"
        for i, l in enumerate(new_links, last_idx + 1): res += f"{i}. {l}\n"
        try:
            await context.bot.send_message(chat_id=user.id, text=res, disable_web_page_preview=True)
            data["last_seen"][uid] = len(links); save_data(data)
            info = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ @{user.username} Liste DM gönderildi.")
            await asyncio.sleep(5); await info.delete()
        except:
            warn = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ @{user.username} Önce botu başlatmalısın (@xlinkkontrol_bot)")
            await asyncio.sleep(7); await warn.delete()

# --- ANA MESAJ FİLTRESİ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    user = update.effective_user; text = message.text.strip()
    is_admin = await is_user_admin(update, context)

    # 1. Komut Kontrolü
    if text.startswith(("/", "@")):
        if not is_admin and not text.startswith("/liste"):
            try: await message.delete()
            except: pass
            return
        if any(text.startswith(c) for c in ["/start", "/liste"]): return

    # 2. X Link Kontrolü
    if tweet_regex.match(text):
        data = load_data()
        # ADMIN ÖZEL: Sınırsız paylaşım + Bot maskeleme (YENİ)
        if is_admin:
            try: await message.delete() # Admin mesajını sil
            except: pass
            data["daily_links"].append(text); save_data(data)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{text}"
            )
            return

        # ÜYE KONTROLÜ
        uid = str(user.id)
        if uid in data["waiting"] or data["users"].get(uid, {}).get("links", 0) >= 2:
            try: await message.delete()
            except: pass
            return
        
        data["waiting"][uid] = text; save_data(data)
        try: await message.delete()
        except: pass
        
        keyboard = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
        waiting_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🚨 Bekle!\n\nLinkinin paylaşılması için gruptaki son linklere destek vermelisin.\n\n🔗 Senin Linkin: {text}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
        # Onay butonu 60 saniye sonra silinsin (YENİ)
        context.job_queue.run_once(lambda ctx: waiting_msg.delete(), when=WAITING_DELETE)
    else:
        if not is_admin:
            try: await message.delete()
            except: pass

# --- CALLBACK ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; target_uid = query.data.split("_")[1]
    if str(query.from_user.id) != target_uid:
        await query.answer("⚠️ Sadece link sahibi onaylayabilir!", show_alert=True); return
    data = load_data(); link = data["waiting"].get(target_uid)
    if not link: return
    if target_uid not in data["users"]: data["users"][target_uid] = {"links": 0}
    data["users"][target_uid]["links"] += 1; data["daily_links"].append(link)
    del data["waiting"][target_uid]; save_data(data)
    await query.edit_message_text(text=f"✅ Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım\n\n{link}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("liste", list_command))
    # Servis mesajlarını yakala
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service_messages))
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
