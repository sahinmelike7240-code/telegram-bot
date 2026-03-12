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
    if not os.path.exists(DATA_FILE): return {"users": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"users": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

# --- İSTATİSTİK KOMUTU (/stats) ---
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    if member.status not in ["administrator", "creator"]: return

    data = load_data()
    if not data["users"]:
        await update.message.reply_text("📊 Henüz veri toplanmadı.")
        return

    report = "📊 **Grup Etkileşim Raporu**\n"
    report += "----------------------------\n"
    report += "👤 Kullanıcı | 🔗 Link | ✅ Onay\n"
    
    for uid, info in data["users"].items():
        report += f"@{info['username']}: {info['links']} | {info['clicks']}\n"
    
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

    if is_admin: return # Admin muaf

    # Veriyi hazırla
    data = load_data()
    uid = str(user.id)
    if uid not in data["users"]:
        data["users"][uid] = {"username": user.username or user.first_name, "links": 0, "clicks": 0}

    # Günlük Limit Kontrolü
    if data["users"][uid]["links"] >= 2:
        try: await message.delete()
        except: pass
        warn = await message.reply_text(f"⚠️ @{user.username} Günlük 2 limitin doldu!")
        await asyncio.sleep(5)
        await warn.delete()
        return

    # PSİKOLOJİK KONTROL BAŞLIYOR
    link_to_post = text
    try: await message.delete() # Orijinal mesajı sil
    except: pass

    keyboard = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"verify_{uid}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Kullanıcıya özel onay mesajı
    verify_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🚨 **@{user.username} Bekle!**\n\nLinkinin paylaşılması için gruptaki son linklere destek vermelisin.\n\n"
             f"🔗 **Senin Linkin:** {link_to_post}\n\n"
             "Destekleri tamamladıysan aşağıdaki butona bas. Yanlış beyan gruptan atılma sebebidir!",
        reply_markup=reply_markup
    )
    
    # Geçici veriyi sakla (onay için)
    context.user_data[f"pending_link_{uid}"] = link_to_post

# --- BUTON TIKLAMA (ONAY) ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(query.from_user.id)
    
    if not query.data.startswith(f"verify_{uid}"):
        await query.answer("Bu senin işlemin değil!", show_alert=True)
        return

    link = context.user_data.get(f"pending_link_{uid}")
    if not link:
        await query.answer("İşlem zaman aşımına uğradı.")
        return

    # İstatistiği güncelle
    data = load_data()
    data["users"][uid]["links"] += 1
    data["users"][uid]["clicks"] += 1
    save_data(data)

    # Linki resmi olarak grupta paylaş
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"✅ **DESTEK ONAYLANDI**\n👤: @{query.from_user.username}\n🔗: {link}"
    )
    
    await query.message.delete()
    await query.answer("Linkin grupta paylaşıldı!")

def main():
    if not BOT_TOKEN: return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("İstatistikli ve Kontrollü Bot Aktif!")
    app.run_polling()

if __name__ == "__main__":
    main()
