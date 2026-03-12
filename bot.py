import json, os, re, asyncio
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

# Ayarlar
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_stats.json"
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

def load_data():
    if not os.path.exists(DATA_FILE): 
        return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            if "waiting" not in d: d["waiting"] = {}
            if "daily_links" not in d: d["daily_links"] = []
            if "last_seen" not in d: d["last_seen"] = {}
            return d
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_seen": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- AKILLI LİSTE KOMUTU (/liste) ---
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    links = data.get("daily_links", [])
    user = update.effective_user
    uid = str(user.id)

    if not links:
        await update.message.reply_text("📭 Bugün henüz onaylanmış bir link bulunmuyor.")
        return

    last_index = data.get("last_seen", {}).get(uid, 0)
    new_links = links[last_index:]

    if not new_links:
        try:
            await context.bot.send_message(chat_id=user.id, text="✅ Bugün paylaşılan tüm linkleri tamamladın!")
            info = await update.message.reply_text(f"✅ @{user.username} Zaten güncelsin!")
            await asyncio.sleep(5)
            await info.delete()
        except: pass
    else:
        response = f"🚀 **YENİ ETKİLEŞİM LİSTESİ ({len(new_links)} Yeni)** 🚀\n\n"
        for i, link in enumerate(new_links, last_index + 1):
            response += f"{i}. {link}\n"
        
        try:
            await context.bot.send_message(chat_id=user.id, text=response, disable_web_page_preview=True)
            data["last_seen"][uid] = len(links)
            save_data(data)
            info = await update.message.reply_text(f"✅ @{user.username} Yeni linkler özelden gönderildi!")
            await asyncio.sleep(5)
            await info.delete()
        except:
            warn = await update.message.reply_text(f"⚠️ @{user.username} Önce botu başlatmalısın!")
            await asyncio.sleep(5)
            await warn.delete()
    
    try: await update.message.delete()
    except: pass

# --- TÜM LİSTE KOMUTU (/hepsi) - TEMİZLİK EKLENDİ ---
async def all_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    links = data.get("daily_links", [])
    user = update.effective_user

    if not links:
        await update.message.reply_text("📭 Liste şu an boş.")
        return

    response = "📚 **BUGÜNKÜ TÜM LİSTE** 📚\n\n"
    for i, link in enumerate(links, 1):
        response += f"{i}. {link}\n"
    
    try:
        # Özelden gönder
        await context.bot.send_message(chat_id=user.id, text=response, disable_web_page_preview=True)
        # Grupta bilgi ver
        info = await update.message.reply_text(f"✅ @{user.username} Tüm liste özelden gönderildi!")
        # 5 saniye bekle ve temizle
        await asyncio.sleep(5)
        await info.delete()
    except:
        warn = await update.message.reply_text(f"⚠️ @{user.username} Önce botu başlatmalısın!")
        await asyncio.sleep(5)
        await warn.delete()
    
    # Kullanıcının yazdığı /hepsi komutunu sil
    try: await update.message.delete()
    except: pass

# --- MESAJ İŞLEME (GEREKSİZLERİ SİLME) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    if not message or not user: return

    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin = member.status in ["administrator", "creator"]
    text = (message.text or "").strip()

    if text.startswith(("/liste", "/hepsi", "/stats", "/start")):
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
