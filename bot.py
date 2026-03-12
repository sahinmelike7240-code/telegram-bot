import json
import os
import re
from datetime import datetime, time, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
DATA_FILE = "bot_data.json"

tweet_regex = re.compile(
    r"^(https?://)?(www\.)?(x\.com|twitter\.com)/[A-Za-z0-9_]+/status/\d+(\?.*)?$",
    re.IGNORECASE,
)

SPAM_LIMIT = 5
SPAM_SECONDS = 60
MUTE_MINUTES = 10


def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "shared_links": {},
            "daily_users": {},
            "pending_approvals": {},
            "user_stats": {},
            "spam": {},
        }
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "shared_links": {},
            "daily_users": {},
            "pending_approvals": {},
            "user_stats": {},
            "spam": {},
        }


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def current_reset_key():
    now = datetime.now()
    reset_hour = 9

    if now.time() < time(reset_hour, 0):
        base_date = now.date().toordinal() - 1
    else:
        base_date = now.date().toordinal()

    return str(base_date)


def normalize_link(text):
    text = text.strip()
    match = tweet_regex.match(text)
    if not match:
        return None

    text = text.replace("twitter.com", "x.com")

    if text.startswith("http://"):
        text = text.replace("http://", "https://", 1)
    elif not text.startswith("https://"):
        text = "https://" + text

    return text.split("?")[0]


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(
        update.effective_chat.id,
        update.effective_user.id,
    )
    return member.status in ["administrator", "creator"]


async def safe_delete(message):
    try:
        await message.delete()
    except Exception:
        pass


def clean_old_daily_data(data, reset_key):
    data["daily_users"] = {
        uid: info
        for uid, info in data.get("daily_users", {}).items()
        if info.get("reset_key") == reset_key
    }

    data["pending_approvals"] = {
        uid: info
        for uid, info in data.get("pending_approvals", {}).items()
        if info.get("reset_key") == reset_key
    }


def get_today_previous_links(data, user_id, reset_key):
    items = []
    for link, info in data.get("shared_links", {}).items():
        if (
            isinstance(info, dict)
            and info.get("reset_key") == reset_key
            and info.get("user_id") != user_id
        ):
            items.append(
                {
                    "link": link,
                    "created_at": info.get("created_at", ""),
                }
            )

    items.sort(key=lambda x: x["created_at"])
    return items


def cleanup_legacy_shared_links(data):
    cleaned = {}
    for link, info in data.get("shared_links", {}).items():
        if isinstance(info, dict):
            cleaned[link] = info
    data["shared_links"] = cleaned


def ensure_user_stats(data, user):
    user_id = str(user.id)
    if user_id not in data["user_stats"]:
        data["user_stats"][user_id] = {
            "name": user.full_name,
            "username": user.username or "",
            "total_shares": 0,
            "last_share_at": "",
        }


def register_share_stat(data, user):
    user_id = str(user.id)
    ensure_user_stats(data, user)
    data["user_stats"][user_id]["name"] = user.full_name
    data["user_stats"][user_id]["username"] = user.username or ""
    data["user_stats"][user_id]["total_shares"] += 1
    data["user_stats"][user_id]["last_share_at"] = datetime.now().isoformat()


def check_and_update_spam(data, user_id):
    now = datetime.now()
    spam_data = data.get("spam", {})

    if user_id not in spam_data:
        spam_data[user_id] = {
            "attempts": [],
            "mute_until": "",
        }

    entry = spam_data[user_id]

    mute_until = entry.get("mute_until", "")
    if mute_until:
        try:
            mute_dt = datetime.fromisoformat(mute_until)
            if now < mute_dt:
                data["spam"] = spam_data
                return True, int((mute_dt - now).total_seconds())
        except Exception:
            entry["mute_until"] = ""

    attempts = entry.get("attempts", [])
    valid_attempts = []

    for ts in attempts:
        try:
            t = datetime.fromisoformat(ts)
            if (now - t).total_seconds() <= SPAM_SECONDS:
                valid_attempts.append(ts)
        except Exception:
            pass

    valid_attempts.append(now.isoformat())
    entry["attempts"] = valid_attempts

    if len(valid_attempts) >= SPAM_LIMIT:
        mute_until_dt = now + timedelta(minutes=MUTE_MINUTES)
        entry["mute_until"] = mute_until_dt.isoformat()
        data["spam"] = spam_data
        return True, int((mute_until_dt - now).total_seconds())

    data["spam"] = spam_data
    return False, 0


async def short_warn(chat, context, text, seconds=5):
    try:
        warn = await chat.send_message(text)
        if context.job_queue:
            context.job_queue.run_once(
                lambda ctx: ctx.bot.delete_message(chat.id, warn.message_id),
                seconds,
            )
    except Exception:
        pass


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if await is_admin(update, context):
        return

    data = load_data()
    reset_key = current_reset_key()
    user_id = str(user.id)

    cleanup_legacy_shared_links(data)
    clean_old_daily_data(data, reset_key)

    muted, remain = check_and_update_spam(data, user_id)
    save_data(data)

    if muted:
        await safe_delete(message)
        mins = max(1, remain // 60)
        await short_warn(chat, context, f"Çok fazla hatalı işlem yaptın. {mins} dakika bekle", 5)
        return

    if (
        message.photo
        or message.video
        or message.animation
        or message.document
        or message.audio
        or message.voice
        or message.video_note
        or message.sticker
        or message.poll
        or message.contact
        or message.location
    ):
        await safe_delete(message)
        return

    text = (message.text or "").strip()
    if not text:
        await safe_delete(message)
        return

    link = normalize_link(text)
    if not link:
        await safe_delete(message)
        return

    if link in data["shared_links"]:
        await safe_delete(message)
        return

    if user_id in data["daily_users"]:
        await safe_delete(message)
        await short_warn(chat, context, "09:00 sonrası günde sadece 1 link paylaşabilirsin", 5)
        return

    previous_links = get_today_previous_links(data, user_id, reset_key)

    if previous_links and user_id not in data["pending_approvals"]:
        await safe_delete(message)

        data["pending_approvals"][user_id] = {
            "reset_key": reset_key,
            "approved": False,
            "pending_link": link,
            "chat_id": chat.id,
            "created_at": datetime.now().isoformat(),
        }
        save_data(data)

        text_lines = [
            f"Bugün 09:00'dan sonra senden önce {len(previous_links)} paylaşım yapılmış",
            "",
            "Önce bunları gör:",
            "",
        ]

        for i, item in enumerate(previous_links[:15], start=1):
            text_lines.append(f"{i}. {item['link']}")

        if len(previous_links) > 15:
            text_lines.append("")
            text_lines.append(f"... ve {len(previous_links) - 15} paylaşım daha var")

        text_lines.append("")
        text_lines.append("Bunları gördüysen aşağıdaki butona bas sonra kendi linkini tekrar gönder")

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Gördüm Onaylıyorum", callback_data=f"approve_{user_id}")]]
        )

        await chat.send_message("\n".join(text_lines), reply_markup=keyboard)
        return

    if previous_links:
        approval = data["pending_approvals"].get(user_id)
        if not approval or not approval.get("approved"):
            await safe_delete(message)
            await short_warn(chat, context, "Önce bugün paylaşılan linkleri görüp onay vermelisin", 5)
            return

    data["shared_links"][link] = {
        "user_id": user_id,
        "username": user.username or "",
        "name": user.full_name,
        "chat_id": chat.id,
        "message_id": message.message_id,
        "created_at": datetime.now().isoformat(),
        "reset_key": reset_key,
    }

    data["daily_users"][user_id] = {
        "reset_key": reset_key,
        "shared_at": datetime.now().isoformat(),
    }

    register_share_stat(data, user)

    if user_id in data["pending_approvals"]:
        del data["pending_approvals"][user_id]

    save_data(data)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    user = query.from_user
    user_id = str(user.id)

    if query.data == f"approve_{user_id}":
        data = load_data()
        reset_key = current_reset_key()
        cleanup_legacy_shared_links(data)
        clean_old_daily_data(data, reset_key)

        if user_id not in data["pending_approvals"]:
            await query.answer("Bekleyen onay bulunamadı", show_alert=True)
            return

        data["pending_approvals"][user_id]["approved"] = True
        save_data(data)

        await query.answer("Onay alındı")
        await query.edit_message_text(
            "Onay kaydedildi. Şimdi kendi X linkini tekrar gruba gönderebilirsin"
        )
    else:
        await query.answer("Bu buton sana ait değil", show_alert=True)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    data = load_data()
    reset_key = current_reset_key()
    cleanup_legacy_shared_links(data)
    clean_old_daily_data(data, reset_key)

    today_count = 0
    for _, info in data["shared_links"].items():
        if isinstance(info, dict) and info.get("reset_key") == reset_key:
            today_count += 1

    total_count = len(data["shared_links"])

    top_users = sorted(
        data.get("user_stats", {}).values(),
        key=lambda x: x.get("total_shares", 0),
        reverse=True,
    )[:10]

    lines = [
        "Grup İstatistikleri",
        "",
        f"Toplam paylaşılan benzersiz link: {total_count}",
        f"Bugün 09:00 sonrası paylaşılan link: {today_count}",
        "",
        "En çok paylaşım yapanlar:",
    ]

    if not top_users:
        lines.append("Henüz veri yok")
    else:
        for i, u in enumerate(top_users, start=1):
            name = u.get("name", "Bilinmiyor")
            total = u.get("total_shares", 0)
            lines.append(f"{i}. {name} — {total}")

    await update.effective_chat.send_message("\n".join(lines))


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    data = load_data()
    reset_key = current_reset_key()
    cleanup_legacy_shared_links(data)

    today_links = []
    for link, info in data["shared_links"].items():
        if isinstance(info, dict) and info.get("reset_key") == reset_key:
            today_links.append((info.get("created_at", ""), link, info.get("name", "Bilinmiyor")))

    today_links.sort(key=lambda x: x[0])

    if not today_links:
        await update.effective_chat.send_message("Bugün 09:00 sonrası henüz paylaşım yok")
        return

    lines = ["Bugünkü paylaşımlar", ""]
    for i, (_, link, name) in enumerate(today_links[:20], start=1):
        lines.append(f"{i}. {name}")
        lines.append(link)
        lines.append("")

    if len(today_links) > 20:
        lines.append(f"... ve {len(today_links) - 20} paylaşım daha var")

    await update.effective_chat.send_message("\n".join(lines))


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ALL, handle_message))

    print("Bot çalışıyor...")
    app.run_polling()


if __name__ == "__main__":
    main()

bunu ekledim dostum şimdi ne yapmam gerekiyor 1 dk da özetle 2 uzun uzun yazma ! 

::contentReference[oaicite:1]{index=1}
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ALL, handle_message))

    print("Bot çalışıyor...")
    app.run_polling()


if __name__ == "__main__":
    main()
