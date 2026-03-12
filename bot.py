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
current_group_id = None

def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"users": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

async def send_rules_periodically(context: ContextTypes.DEFAULT_TYPE):
    if current_group_id:
        rules_text = "📢 **HATIRLATMA:** Önceki linklere destek vermeden onay butonuna basmayınız. Denetimler manuel yapılmaktadır."
        await context.bot.send_message(chat_id=current_group_id, text=rules_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]: return
    data = load_data()
    report = "📊 **Grup İstatistikleri**\n\nKullanıcı | Link | Onay\n"
    for uid, info in data["users"].items():
        report += f"{info['username']}: {info['links']} | {info['clicks']}\n"
    await update.message.reply_text(report)

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
        data["users"][uid] = {"username": user.first_name, "links": 0, "clicks": 0}

    now = datetime.now(TR_TIMEZONE)
    if 2 <= now.hour < 8 or data["users"][uid]["links"] >= 2:
        try: await message.delete()
        except: pass
        return

    # Linki geçici sakla ve temiz onay mesajı çıkar
    link_to_post = text
    try: await message.delete()
    except: pass

    keyboard = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data[f"link_{uid}"] = link_to_post

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🚨 **Bekle!**\n\nLinkinin paylaşılması için gruptaki son linklere destek vermelisin.\n\n🔗 **Senin Linkin:** {link_to_post}",
        reply_markup=reply_markup,
        disable_web_page_preview=True # Kalabalık yapmasın diye önizlemeyi kapattım
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    target_uid = query.data.replace("v_", "")
    user_id = str(query.from_user.id)

    if user_id != target_uid:
        await query.answer("⚠️ Sadece link sahibi onaylayabilir!", show_alert=True)
        return

    link = context.user_data.get(f"link_{target_uid}")
    if not link:
        await query.answer("❌ Süre doldu, lütfen tekrar link atın.")
        return

    data = load_data()
    data["users"][target_uid]["links"] += 1
    data["users"][target_uid]["clicks"] += 1
    save_data(data)

    # TAM SENİN İSTEDİĞİN SADE MESAJ FORMATI
    final_text = (
        "✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n"
        f"{link}"
    )

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=final_text
    )
    
    try: await query.message.delete()
    except: pass
    await query.answer("Onaylandı!")

def main():
    if not BOT_TOKEN: return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.job_queue.run_repeating(send_rules_periodically, interval=14400, first=10)
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
