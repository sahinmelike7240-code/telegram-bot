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
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}, "daily_links": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            if "waiting" not in d: d["waiting"] = {}
            if "daily_links" not in d: d["daily_links"] = []
            return d
    except: return {"users": {}, "waiting": {}, "daily_links": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- ÖZEL LİSTE KOMUTU (/liste) ---
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    links = data.get("daily_links", [])
    user = update.effective_user

    if not links:
        await update.message.reply_text("📭 Bugün henüz onaylanmış bir link bulunmuyor.")
        return

    response = "🚀 **BUGÜNKÜ ETKİLEŞİM LİSTESİ** 🚀\n"
    response += "----------------------------------\n"
    response += "Aşağıdaki linklere destek vererek gruba katkıda bulunabilirsin:\n\n"
    
    for i, link in enumerate(links, 1):
        response += f"{i}. {link}\n"
    
    response += "\n✅ *Hepsini tamamlamayı unutma!*"

    try:
        # Mesajı kullanıcıya ÖZELDEN gönder
        await context.bot.send_message(chat_id=user.id, text=response, disable_web_page_preview=True)
        # Gruba sadece bilgi mesajı at (5 saniye sonra silinir)
        info = await update.message.reply_text(f"✅ @{user.username} Liste özel mesaj (DM) olarak gönderildi!")
        await asyncio.sleep(5)
        await info.delete()
        await update.message.delete() # /liste komutunu da silerek grubu temiz tutar
    except:
        # Kullanıcı botu başlatmamışsa
        warn = await update.message.reply_text(
            f"⚠️ @{user.username} Sana özelden liste gönderemiyorum!\n"
            f"Lütfen önce botun özeline gidip /start yapmalısın."
        )
        await asyncio.sleep(10)
        await warn.delete()

# --- İSTATİSTİK KOMUTU (/stats) ---
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]: return
    data = load_data()
    report = "📊 **İstatistikler**\n\nKullanıcı | Link | Onay\n"
    for uid, info in data["users"].items():
        report += f"{info['username']}: {info['links']} | {info['clicks']}\n"
    await update.message.reply_text(report)

# --- ANA MESAJ İŞLEME ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    if not message or not user: return

    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin = member.status in ["administrator", "creator"]
    text = (message.text or "").strip()

    if not tweet_regex.match(text):
        if not is_admin:
            try: await message.delete()
            except: pass
        return

    if is_admin: return 

    data = load_data()
    uid = str(user.id)

    # Sıfırlama Kontrolü
    now = datetime.now(TR_TIMEZONE)
    today_str = now.strftime("%Y-%m-%d")
    if data.get("last_reset") != today_str and now.hour >= 2:
        data = {"users": {}, "waiting": {}, "daily_links": [], "last_reset": today_str}
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
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🚨 **Bekle!**\n\nLinkinin paylaşılması için gruptaki son linklere destek vermelisin.\n\n🔗 **Senin Linkin:** {text}",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

# --- BUTON TIKLAMA ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    target_uid = query.data.split("_")[1]
    user_id = str(query.from_user.id)

    if user_id != target_uid:
        await query.answer("⚠️ Sadece link sahibi onaylayabilir!", show_alert=True)
        return

    data = load_data()
    link = data["waiting"].get(target_uid)

    if not link:
        await query.answer("❌ Link bulunamadı.")
        return

    if target_uid not in data["users"]:
        data["users"][target_uid] = {"username": query.from_user.first_name, "links": 0, "clicks": 0}
    
    data["users"][target_uid]["links"] += 1
    data["users"][target_uid]["clicks"] += 1
    data["daily_links"].append(link)
    del data["waiting"][target_uid]
    save_data(data)

    final_text = f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{link}"
    await query.edit_message_text(text=final_text, disable_web_page_preview=False)
    await query.answer("Onaylandı!")

# --- BOTU BAŞLATMA KOMUTU (DM İÇİN) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("👋 Merhaba! Ben X Etkileşim Botu.\n\nGrupta `/liste` yazdığında günün linklerini sana buradan göndereceğim.")

def main():
    if not BOT_TOKEN: return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("liste", list_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
