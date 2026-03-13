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
    "🚀 X ETKİLEŞİM GRUBU - RESMİ KURALLAR 🚀\n\n"
    "Grubumuzun kalitesini korumak ve herkesin eşit etkileşim almasını sağlamak için aşağıdaki kurallar zorunludur:\n\n"
    "▪️ Takip Zorunluluğu: Gruptaki herkes birbirini takip etmek zorundadır. Takibi bırakanlar tespit edildiğinde gruptan uzaklaştırılır.\n\n"
    "▪️ Günlük Limit: Hakkaniyet adına günde en fazla 2 gönderi paylaşma hakkınız vardır.\n\n"
    "▪️ Günlük Limit: Hakkaniyet adına günde en fazla 2 gönderi paylaşma hakkınız vardır.\n\n"
    "▪️ Anlamlı Etkileşim: Gönderilere Beğeni + Kaydet ve en az 4-5 kelimelik anlamlı yorum yapılması şarttır. (Emoji veya tek kelimelik yorumlar sayılmaz!)\n\n"
    "▪️ Liste Sistemi: Gruba /liste yazarak, sabah 08:00 ile gece 02:00 saatleri arasında paylaşılan tüm güncel gönderileri özel mesaj olarak alabilirsiniz.\n\n"
    "📢 ÖNEMLİ: Listeyi alabilmek için önce Telegram'da @xlinkkontrol_bot hesabını aratıp BAŞLAT (Start) demeniz gerekmektedir.\n\n"
    "🤝 Birlikte büyüyoruz! Sabrınız ve desteğiniz için teşekkürler.\n"
    "━━━━━━━━━━━━━━━\n"
    "⏰ Bu bilgilendirme 5 dakika içinde gruptan kaldırılacaktır."
)

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

# --- VERİ İŞLEMLERİ ---
def load_data():
    if not os.path.exists(DATA_FILE): 
        return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}
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

# --- ZAMANLANMIŞ GÖREV (KURALLAR) ---
async def remind_rules(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    try:
        msg = await context.bot.send_message(chat_id=job.chat_id, text=RULES_TEXT)
        await asyncio.sleep(DELETE_AFTER)
        await msg.delete()
    except: pass

# --- KOMUTLAR ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # GRUPTA MIYIZ?
    if update.effective_chat.type != "private":
        # ADMİN Mİ?
        member = await context.bot.get_chat_member(chat_id, user.id)
        if member.status not in ["administrator", "creator"]:
            try: await update.message.delete()
            except: pass
            return # ÜYEYSE BURADA BİTER, DÖNGÜ BAŞLAMAZ

        # SADECE ADMİNSE BURAYA GEÇER
        try: await update.message.delete()
        except: pass
        
        # Eski döngüleri temizle
        current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for j in current_jobs: j.schedule_removal()
        
        # Döngüyü kur (İlk kural mesajı 2 saat sonra)
        context.job_queue.run_repeating(remind_rules, interval=REMIND_INTERVAL, first=REMIND_INTERVAL, chat_id=chat_id, name=str(chat_id))
        
        info = await update.message.reply_text(f"✅ Sistem @{user.username} tarafından aktif edildi. Kurallar 2 saatte bir gelecek.")
        await asyncio.sleep(5); await info.delete()
    else:
        # ÖZEL MESAJ (DM)
        await update.message.reply_text("👋 Merhaba! Grupta /liste yazarak güncel linkleri buradan alabilirsin.")

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status in ["administrator", "creator"]:
        try: await update.message.delete()
        except: pass
        msg = await update.message.reply_text(RULES_TEXT)
        await asyncio.sleep(DELETE_AFTER); await msg.delete()

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    data = load_data()
    links = data.get("daily_links", [])
    user = update.effective_user
    uid = str(user.id)
    
    try: await update.message.delete()
    except: pass

    if not links:
        m = await context.bot.send_message(chat_id=update.effective_chat.id, text="📭 Henüz onaylanmış link yok.")
        await asyncio.sleep(5); await m.delete()
        return

    last_idx = data.get("last_seen", {}).get(uid, 0)
    new_links = links[last_idx:]

    if not new_links:
        try:
            await context.bot.send_message(chat_id=user.id, text="✅ Harikasın! Tüm listeyi zaten tamamladın.")
            info = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ @{user.username} Zaten güncelsin!")
            await asyncio.sleep(5); await info.delete()
        except: pass
    else:
        res = f"🚀 YENİ ETKİLEŞİM LİSTESİ 🚀\n📌 En son {last_idx}. linkte kalmıştın.\n\n"
        for i, l in enumerate(new_links, last_idx + 1): res += f"{i}. {l}\n"
        try:
            await context.bot.send_message(chat_id=user.id, text=res, disable_web_page_preview=True)
            data["last_seen"][uid] = len(links)
            save_data(data)
            info = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ @{user.username} Yeni linkler DM gönderildi.")
            await asyncio.sleep(5); await info.delete()
        except:
            warn = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ @{user.username} Önce botu başlatmalısın (@xlinkkontrol_bot)")
            await asyncio.sleep(7); await warn.delete()

async def hepsi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    data = load_data()
    links = data.get("daily_links", [])
    user = update.effective_user
    
    try: await update.message.delete()
    except: pass

    if not links: return
    res = "📚 BUGÜNKÜ TÜM LİSTE 📚\n\n"
    for i, l in enumerate(links, 1): res += f"{i}. {l}\n"
    try:
        await context.bot.send_message(chat_id=user.id, text=res, disable_web_page_preview=True)
        info = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ @{user.username} Tüm liste DM gönderildi.")
        await asyncio.sleep(5); await info.delete()
    except: pass

# --- ANA MESAJ FİLTRESİ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    user = update.effective_user
    text = message.text.strip()
    
    # KOMUTLARI AYIKLA
    if text.startswith(("/", "@")):
        # Admin kontrolü
        member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
        is_admin = member.status in ["administrator", "creator"]
        
        # Eğer admin değilse ve /liste /hepsi harici komutsa sil ve bitir
        if not is_admin and not text.startswith(("/liste", "/hepsi")):
            try: await message.delete()
            except: pass
            return
        # Komut adminse veya yasal komutsa dokunma (CommandHandler halletsin)
        if text.startswith(("/liste", "/hepsi", "/start", "/kurallar", "/stats")):
            return

    # X LINK KONTROLÜ
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin = member.status in ["administrator", "creator"]

    if not tweet_regex.match(text):
        if not is_admin:
            try: await message.delete()
            except: pass
        return 

    if is_admin: return 
    
    data = load_data()
    uid = str(user.id)
    now = datetime.now(TR_TIMEZONE)
    today_str = now.strftime("%Y-%m-%d")
    
    if data.get("last_reset") != today_str and now.hour >= 2:
        data = {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}, "last_reset": today_str}
        save_data(data)
        
    if uid in data["waiting"] or data["users"].get(uid, {}).get("links", 0) >= 2:
        try: await message.delete()
        except: pass
        return
        
    data["waiting"][uid] = text
    save_data(data)
    try: await message.delete()
    except: pass
    
    keyboard = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🚨 Bekle!\n\nLinkinin paylaşılması için gruptaki son linklere destek vermelisin.\n\n🔗 Senin Linkin: {text}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )

# --- CALLBACK ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    target_uid = query.data.split("_")[1]
    if str(query.from_user.id) != target_uid:
        await query.answer("⚠️ Sadece link sahibi onaylayabilir!", show_alert=True); return
    data = load_data()
    link = data["waiting"].get(target_uid)
    if not link: return
    if target_uid not in data["users"]:
        data["users"][target_uid] = {"username": query.from_user.first_name, "links": 0}
    data["users"][target_uid]["links"] += 1
    data["daily_links"].append(link)
    del data["waiting"][target_uid]
    save_data(data)
    await query.edit_message_text(text=f"✅ Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım\n\n{link}")

def main():
    if not BOT_TOKEN: return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("liste", list_command))
    app.add_handler(CommandHandler("hepsi", hepsi_command))
    app.add_handler(CommandHandler("kurallar", rules_command))
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
