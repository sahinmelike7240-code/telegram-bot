import json, os, re, asyncio, datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

# --- AYARLAR ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "bot_stats.json"
TR_TIMEZONE = pytz.timezone('Europe/Istanbul')
REMIND_INTERVAL = 7200
WAITING_DELETE = 60

# Senin orijinal kuralların
RULES_TEXT = (
    "🚀 X Etkileşim Grubu Kuralları\n\n"
    "🔹 Takip: Üyeler birbirini takip etmelidir.\n"
    "🔹 Limit: Günde en fazla 2 gönderi paylaşılabilir.\n"
    "🔹 Etkileşim: Beğeni + Kaydet ve anlamlı yorum şarttır.\n"
    "🔹 Liste: /liste yazarak linkleri DM alabilirsiniz."
)

tweet_regex = re.compile(r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$", re.IGNORECASE)

# --- VERİ MERKEZİ ---
def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None, "msg_map": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            for k in ["users", "waiting", "daily_links", "msg_map"]: d.setdefault(k, {} if k != "daily_links" else [])
            return d
    except: return {"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None, "msg_map": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- GRUP YÖNETİMİ ---
async def daily_reset(context: ContextTypes.DEFAULT_TYPE):
    save_data({"users": {}, "waiting": {}, "daily_links": [], "last_rule_id": None, "msg_map": {}})

async def on_user_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.left_chat_member
    if not user: return
    uid = str(user.id); data = load_data()
    if uid in data.get("msg_map", {}):
        for mid in data["msg_map"][uid]:
            try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=mid)
            except: pass
        del data["msg_map"][uid]
    patt = f"/{user.username}/status/" if user.username else "temp_xyz"
    data["daily_links"] = [l for l in data["daily_links"] if patt not in l]
    if uid in data["users"]: del data["users"][uid]
    save_data(data)
    try: await update.message.delete()
    except: pass

# --- KOMUTLAR ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("👋 Bot aktif! Grupta /liste yazabilirsin.")
        return
    # Grupta start sadece admin için
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]: return
    try: await update.message.delete()
    except: pass
    m = await update.message.reply_text("✅ Sistem aktif.")
    await asyncio.sleep(2); await m.delete()

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # 1. Grupta yazıldıysa komutu sil
    if update.effective_chat.type != "private":
        try: await update.message.delete()
        except: pass
    
    data = load_data()
    links = data.get("daily_links", [])
    
    # 2. Özelden listeyi gönder (DM)
    try:
        if not links:
            await context.bot.send_message(chat_id=user.id, text="⚠️ Henüz paylaşılmış link yok.")
        else:
            res = "🚀 GÜNCEL LİSTE 🚀\n\n" + "\n".join([f"{i+1}. {l}" for i, l in enumerate(links)])
            await context.bot.send_message(chat_id=user.id, text=res, disable_web_page_preview=True)
            u_info = data["users"].setdefault(str(user.id), {"username": user.username or user.first_name, "links": 0, "list_count": 0})
            u_info["list_count"] += 1
            save_data(data)
    except:
        # Botu başlatmamışsa gruptan uyar ve 5sn sonra sil
        if update.effective_chat.type != "private":
            m = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ @{user.username} Botu DM'den başlatmalısın!")
            await asyncio.sleep(5); await m.delete()

async def hepsi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = -1002361730040  # <--- BURAYA KENDİ GRUP ID'Nİ YAZARSAN DAHA SAĞLIKLI OLUR

    # GRUPTA YAZILDIYSA: KİM OLURSA OLSUN SİL
    if update.effective_chat.type != "private":
        try: await update.message.delete()
        except: pass
        
    # ADMİNLİK KONTROLÜ (Gerek grupta gerek özelde)
    try:
        # Botun olduğu gruptaki yetkisini kontrol et
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ["administrator", "creator"]:
            return # Admin değilse hiçbir şey yapma, cevap verme
    except:
        # Eğer bot grup ID'sini bulamazsa veya hata alırsa güvenlik için cevap vermez
        return

    # SADECE ADMİN BURAYA GELEBİLİR
    data = load_data()
    if not data["users"]:
        await context.bot.send_message(chat_id=user_id, text="📊 Veri yok.")
        return
        
    rapor = "📊 **GÜNLÜK TAKİP RAPORU** 📊\n\n"
    for uid, info in data["users"].items():
        rapor += f"👤 @{info.get('username')}: {info.get('links')} Link - {info.get('list_count')} Liste\n"
    
    await context.bot.send_message(chat_id=user_id, text=rapor)

# --- ANA MESAJ FİLTRESİ ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text: return
    user = update.effective_user
    text = message.text.strip()
    
    if update.effective_chat.type != "private":
        member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
        is_admin = member.status in ["administrator", "creator"]

        if tweet_regex.match(text):
            data = load_data(); uid = str(user.id)
            if is_admin:
                try: await message.delete()
                except: pass
                data["daily_links"].append(text); save_data(data)
                sent = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Yorum Beğeni Ve Kaydet yapıldı**\n\n{text}")
                data.setdefault("msg_map", {}).setdefault(uid, []).append(sent.message_id); save_data(data)
                return
            
            u_info = data["users"].get(uid, {"links": 0})
            if u_info["links"] >= 2:
                try: await message.delete()
                except: pass
                return
                
            data["waiting"][uid] = text; save_data(data)
            try: await message.delete()
            except: pass
            kb = [[InlineKeyboardButton("✅ DESTEK VERDİM (ONAYLA)", callback_data=f"v_{uid}")]]
            w_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🚨 Bekle! Destek vermelisin.\n🔗 Linkin: {text}", reply_markup=InlineKeyboardMarkup(kb))
            context.job_queue.run_once(lambda ctx: w_msg.delete() if uid in load_data()["waiting"] else None, when=WAITING_DELETE)
        else:
            # Grupta link/komut harici her şeyi sil
            try: await message.delete()
            except: pass

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; uid = query.data.split("_")[1]
    if str(query.from_user.id) != uid:
        await query.answer("⚠️ Sadece kendi linkini onaylayabilirsin!", show_alert=True)
        return
    data = load_data(); link = data["waiting"].get(uid)
    if not link: return
    try: await query.message.delete()
    except: pass
    u_info = data["users"].setdefault(uid, {"username": query.from_user.username or query.from_user.first_name, "links": 0, "list_count": 0})
    u_info["links"] += 1; data["daily_links"].append(link)
    sent = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ **Yukarıdaki Linklere Yorum Beğeni Ve Kaydet yaptım**\n\n{link}")
    data.setdefault("msg_map", {}).setdefault(uid, []).append(sent.message_id)
    del data["waiting"][uid]; save_data(data)
    await query.answer("✅ Onaylandı!")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.job_queue.run_daily(daily_reset, time=datetime.time(hour=2, minute=0, tzinfo=TR_TIMEZONE))
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("liste", list_command))
    app.add_handler(CommandHandler("hepsi", hepsi_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_user_left))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
