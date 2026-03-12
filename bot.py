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
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            if "waiting" not in d: d["waiting"] = {}
            return d
    except: return {"users": {}, "waiting": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

    # Kilit Kontrolü
    if uid in data["waiting"]:
        try: await message.delete()
        except: pass
        return

    # Limit Kontrolü
    if uid not in data["users"]:
        data["users"][uid] = {"username": user.first_name, "links": 0, "clicks": 0}
    if data["users"][uid]["links"] >= 2:
        try: await message.delete()
        except: pass
        return

    # Linki sil ve tek bir onay kutusu aç
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

# --- BUTON TIKLAMA (MESAJI DÜZENLEME) ---
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
        await query.answer("❌ Link bulunamadı.", show_alert=True)
        return

    # Veriyi Güncelle
    data["users"][target_uid]["links"] += 1
    data["users"][target_uid]["clicks"] += 1
    del data["waiting"][target_uid]
    save_data(data)

    # MESAJI İKİNCİ KEZ ATMAK YERİNE MEVCUT MESAJI DÜZENLİYORUZ (TEK MESAJ)
    final_text = (
        "✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n"
        f"{link}"
    )

    # Butonu kaldırıp metni değiştiriyoruz
    await query.edit_message_text(text=final_text, disable_web_page_preview=False)
    await query.answer("Başarıyla onaylandı!")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]: return
    data = load_data()
    report = "📊 **İstatistikler**\n\nKullanıcı | Link | Onay\n"
    for uid, info in data["users"].items():
        report += f"{info['username']}: {info['links']} | {info['clicks']}\n"
    await update.message.reply_text(report)

def main():
    if not BOT_TOKEN: return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
