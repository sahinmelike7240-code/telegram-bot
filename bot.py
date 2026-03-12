import json, os, re, asyncio
from datetime import datetime, time
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

# Ayarlar
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_stats.json"
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

# Grup ID'sini botun hatırlaması için global değişken
current_group_id = None

def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"users": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

# --- 4 SAATTE BİR KURAL HATIRLATMA ---
async def send_rules_periodically(context: ContextTypes.DEFAULT_TYPE):
    if current_group_id:
        rules_text = (
            "📢 **DÜZENLİ KURAL HATIRLATMASI**\n\n"
            "▪️ Takip zorunludur.\n"
            "▪️ Günde 2 link hakkı (08:00 - 02:00).\n"
            "▪️ Destek vermeden onay butonuna basmak yasaktır!\n"
            "▪️ 48 saat pasif kalanlar çıkarılır."
        )
        await context.bot.send_message(chat_id=current_group_id, text=rules_text)

# --- İSTATİSTİK KOMUTU (/stats) ---
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    if member.status not in ["administrator", "creator"]: return

    data = load_data()
    if not data["users"]:
        await update.message.reply_text("📊 Henüz veri yok.")
        return

    report = "📊 **Grup Etkileşim Raporu**\n\n👤 Kullanıcı | 🔗 Link | ✅ Onay\n"
    for uid, info in data["users"].items():
        report += f"@{info['username']}: {info['links']} | {info['clicks']}\n"
    await update.message.reply_text(report)

# --- ANA MESAJ İŞLEME ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_group_id
    current_group_id = update.effective_chat.id
    
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

    data = load_data()
    uid = str(user.id)
    if uid not in data["users"]:
        data["users"][uid] = {"username": user.username or user.first_name, "links": 0, "clicks": 0}

    # Mesai ve Limit Kontrolü
    now = datetime.now(TR_TIMEZONE)
    if 2 <= now.hour < 8:
        try: await message.delete()
        except: pass
        return

    if data["users"][uid]["links"] >= 2:
        try: await message.delete()
        except: pass
        return

    # Linki sil ve onay mesajı çıkar
    link_to_post = text
    try: await message.delete()
    except: pass

    # Callback data içine sadece UID koyuyoruz ki daha kısa olsun
    keyboard = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Geçici link verisini sakla
    context.user_data[f"link_{uid}"] = link_to_post

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🚨 **@{user.username} Bekle!**\n\nLinkinin paylaşılması için gruptaki son linklere destek vermelisin.\n\n🔗 **Senin Linkin:** {link_to_post}",
        reply_markup=reply_markup
    )

# --- BUTON TIKLAMA İŞLEMİ ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # query.data formatı: "v_123456"
    target_uid = query.data.replace("v_", "")
    user_id = str(query.from_user.id)

    # Sadece link sahibi onaylayabilir
    if user_id != target_uid:
        await query.answer("⚠️ Bu link senin değil, sadece sahibi onaylayabilir!", show_alert=True)
        return

    link = context.user_data.get(f"link_{target_uid}")
    if not link:
        await query.answer("❌ Hata: Link verisi bulunamadı veya süre doldu.")
        return

    # Veriyi kaydet
    data = load_data()
    if target_uid not in data["users"]:
        data["users"][target_uid] = {"username": query.from_user.username or "User", "links": 0, "clicks": 0}
    
    data["users"][target_uid]["links"] += 1
    data["users"][target_uid]["clicks"] += 1
    save_data(data)

    # Linki paylaş
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"✅ **DESTEK ONAYLANDI**\n👤: @{query.from_user.username}\n🔗: {link}"
    )
    
    try: await query.message.delete()
    except: pass
    await query.answer("Başarıyla onaylandı!")

def main():
    if not BOT_TOKEN: return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # 4 saatte bir hatırlatıcıyı başlat
    app.job_queue.run_repeating(send_rules_periodically, interval=14400, first=10)
    
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("Bot Onay Sistemi ve Hatırlatıcı Hazır!")
    app.run_polling()

if __name__ == "__main__":
    main()
