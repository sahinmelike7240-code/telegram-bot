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

# Aktif bekleyen onaylar (Kilit mekanizması)
waiting_approvals = {} 

def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"users": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

# --- İSTATİSTİK ---
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]: return
    data = load_data()
    report = "📊 **Grup İstatistikleri**\n\nKullanıcı | Link | Onay\n"
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

    # Link değilse sil (Admin hariç)
    if not tweet_regex.match(text):
        if not is_admin: 
            try: await message.delete()
            except: pass
        return

    if is_admin: return # Adminlere kısıtlama yok

    uid = str(user.id)
    
    # KİLİT KONTROLÜ: Kullanıcının zaten bekleyen bir onayı var mı?
    if uid in waiting_approvals:
        try: await message.delete()
        except: pass
        warn = await message.reply_text(f"⚠️ @{user.username} Önce önceki linkini onaylamalısın!")
        await asyncio.sleep(3)
        await warn.delete()
        return

    # Günlük Hak Kontrolü
    data = load_data()
    if uid not in data["users"]:
        data["users"][uid] = {"username": user.first_name, "links": 0, "clicks": 0}
    
    if data["users"][uid]["links"] >= 2:
        try: await message.delete()
        except: pass
        return

    # Orijinal mesajı sil ve onay sürecini başlat
    try: await message.delete()
    except: pass

    # Onayı kilitle ve linki sakla
    waiting_approvals[uid] = text

    keyboard = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    sent_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🚨 **Bekle!**\n\nLinkinin paylaşılması için gruptaki son linklere destek vermelisin.\n\n🔗 **Senin Linkin:** {text}",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    # Mesaj ID'sini sakla (onaylanınca silmek için)
    context.user_data[f"msg_{uid}"] = sent_msg.message_id

# --- BUTON TIKLAMA ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # "v_123456" formatından UID'yi al
    target_uid = query.data.split("_")[1]
    user_id = str(query.from_user.id)

    if user_id != target_uid:
        await query.answer("⚠️ Sadece link sahibi onaylayabilir!", show_alert=True)
        return

    link = waiting_approvals.get(target_uid)
    if not link:
        await query.answer("❌ İşlem zaman aşımı veya link bulunamadı.")
        return

    # Veriyi güncelle
    data = load_data()
    data["users"][target_uid]["links"] += 1
    data["users"][target_uid]["clicks"] += 1
    save_data(data)

    # Kilidi aç
    del waiting_approvals[target_uid]

    # Mesajı gönder
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{link}"
    )
    
    # Onay kutusunu sil
    try: await query.message.delete()
    except: pass
    await query.answer("Onaylandı ve Paylaşıldı!")

def main():
    if not BOT_TOKEN: return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
