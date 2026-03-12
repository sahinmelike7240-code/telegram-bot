import json, os, re, asyncio
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

# Ayarlar
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_stats.json"
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')

# Süre Ayarları
REMIND_INTERVAL = 7200  # 2 Saatte bir hatırlatır
DELETE_AFTER = 300      # 5 Dakika sonra siler

# Kurallar Metni (İstediğin gibi detaylandırıldı ve anlamlı hale getirildi)
RULES_TEXT = (
    "🚀 **X ETKİLEŞİM GRUBU - RESMİ KURALLAR** 🚀\n\n"
    "Grubumuzun kalitesini korumak ve herkesin eşit etkileşim almasını sağlamak için aşağıdaki kurallar zorunludur:\n\n"
    "▪️ **Takip Zorunluluğu:** Gruptaki herkes birbirini takip etmek zorundadır. Takibi bırakanlar tespit edildiğinde gruptan uzaklaştırılır.\n"
    "▪️ **Günlük Limit:** Hakkaniyet adına günde en fazla **2 gönderi** paylaşma hakkınız vardır.\n"
    "▪️ **Anlamlı Etkileşim:** Gönderilere Beğeni + Kaydet ve en az 4-5 kelimelik **anlamlı yorum** yapılması şarttır. (Emoji veya tek kelimelik yorumlar sayılmaz!)\n"
    "▪️ **Liste Sistemi:** Gruba **/liste** yazarak, sabah **08:00** ile gece **02:00** saatleri arasında paylaşılan tüm güncel gönderileri özel mesaj olarak alabilirsiniz.\n"
    "▪️ **Disiplin:** Kurallara uymayanlar veya etkileşimden kaçanlar denetim ekibi tarafından kalıcı olarak engellenir.\n\n"
    "🤝 *Birlikte büyüyoruz! Sabrınız ve desteğiniz için teşekkürler.*\n"
    "━━━━━━━━━━━━━━━\n"
    "⏰ *Bu bilgilendirme 5 dakika içinde gruptan kaldırılacaktır.*"
)

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

def load_data():
    if not os.path.exists(DATA_FILE): 
        return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- 2 SAATTE BİR HATIRLATICI ---
async def remind_rules(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    try:
        msg = await context.bot.send_message(chat_id=job.chat_id, text=RULES_TEXT)
        await asyncio.sleep(DELETE_AFTER)
        await msg.delete()
    except: pass

# --- AKILLI LİSTE (/liste) ---
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    links = data.get("daily_links", [])
    user = update.effective_user
    uid = str(user.id)

    if not links:
        await update.message.reply_text("📭 Henüz onaylanmış link yok.")
        return

    last_index = data.get("last_seen", {}).get(uid, 0)
    new_links = links[last_index:]

    if not new_links:
        try:
            await context.bot.send_message(chat_id=user.id, text="✅ Harikasın! Tüm listeyi tamamladın.")
            info = await update.message.reply_text(f"✅ @{user.username} Zaten güncelsin!")
            await asyncio.sleep(5)
            await info.delete()
        except: pass
    else:
        response = f"🚀 **YENİ ETKİLEŞİM LİSTESİ** 🚀\n📌 *En son {last_index}. linkte kalmıştın.*\n\n"
        for i, link in enumerate(new_links, last_index + 1):
            response += f"{i}. {link}\n"
        
        try:
            await context.bot.send_message(chat_id=user.id, text=response, disable_web_page_preview=True)
            data["last_seen"][uid] = len(links)
            save_data(data)
            info = await update.message.reply_text(f"✅ @{user.username} Yeni linkler DM gönderildi.")
            await asyncio.sleep(5)
            await info.delete()
        except:
            warn = await update.message.reply_text(f"⚠️ @{user.username} Sana liste atabilmem için önce özelden bana /start yazmalısın!")
            await asyncio.sleep(7)
            await warn.delete()
    
    try: await update.message.delete()
    except: pass

# --- ANA MESAJ İŞLEME ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    if not message or not user: return

    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin = member.status in ["administrator", "creator"]
    text = (message.text or "").strip()

    if text.startswith(("/liste", "/hepsi", "/stats", "/start", "/kurallar")):
        return

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

    # GÜNLÜK 2 GÖNDERİ SINIRI
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
        text=f"🚨 **Bekle!**\n\nLinkinin paylaşılması için gruptaki son linklere destek vermelisin.\n\n🔗 **Senin Linkin:** {text}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )

# --- DİĞER FONKSİYONLAR ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    target_uid = query.data.split("_")[1]
    if str(query.from_user.id) != target_uid:
        await query.answer("⚠️ Sadece link sahibi onaylayabilir!", show_alert=True)
        return
    data = load_data()
    link = data["waiting"].get(target_uid)
    if not link: return
    
    if target_uid not in data["users"]:
        data["users"][target_uid] = {"username": query.from_user.first_name, "links": 0, "clicks": 0}
    
    data["users"][target_uid]["links"] += 1
    data["daily_links"].append(link)
    del data["waiting"][target_uid]
    save_data(data)
    await query.edit_message_text(text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{link}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type != "private":
        # Görev döngüsünü başlat (2 saatte bir)
        context.job_queue.run_repeating(remind_rules, interval=REMIND_INTERVAL, first=10, chat_id=chat_id, name=str(chat_id))
    await update.message.reply_text("👋 Bot aktif! Kural hatırlatıcı 2 saatlik döngüye girdi.")

def main():
    if not BOT_TOKEN: return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("liste", list_command))
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
