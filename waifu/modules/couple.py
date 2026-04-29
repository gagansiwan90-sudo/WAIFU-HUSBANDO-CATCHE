"""
modules/couple.py

/couple — Shows a random couple of the day from married users.
"""
import random
from html import escape
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from waifu import application, user_collection


async def couple(update: Update, context: CallbackContext) -> None:
    # Get all married users
    married_users = await user_collection.find(
        {"spouse_id": {"$exists": True, "$ne": None}}
    ).to_list(length=1000)

    if not married_users or len(married_users) < 2:
        await update.message.reply_text(
            "💔 No couples found yet!\n"
            "Use /marry to find your soulmate! 💍"
        )
        return

    # Build unique couples (avoid duplicate pairs)
    seen = set()
    couples = []
    for user in married_users:
        uid = user["id"]
        sid = user.get("spouse_id")
        if not sid:
            continue
        pair = tuple(sorted([uid, sid]))
        if pair in seen:
            continue
        seen.add(pair)

        # Get spouse doc
        spouse_doc = await user_collection.find_one({"id": sid})
        if not spouse_doc:
            continue

        couples.append((user, spouse_doc))

    if not couples:
        await update.message.reply_text(
            "💔 No couples found yet!\n"
            "Use /marry to find your soulmate! 💍"
        )
        return

    # Pick a random couple using today's date as seed for consistency
    today = datetime.now().strftime("%Y-%m-%d")
    random.seed(today)
    user1, user2 = random.choice(couples)
    random.seed()

    name1 = escape(user1.get("first_name", "Unknown"))
    name2 = escape(user2.get("first_name", "Unknown"))
    uid1  = user1["id"]
    uid2  = user2["id"]

    # Count combined characters
    chars1 = len(user1.get("characters", []))
    chars2 = len(user2.get("characters", []))
    combined = chars1 + chars2

    text = (
        f"✨ 💕 <b>Today's Special Couple</b> 💕 ✨\n\n"
        f"🌸 <a href='tg://user?id={uid1}'>{name1}</a>  ×  "
        f"<a href='tg://user?id={uid2}'>{name2}</a> 🌸\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💘 Love Level: MAX\n"
        f"🎴 Combined Waifus: {combined}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"💍 Forever Shipped! 🌸"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


application.add_handler(CommandHandler("couple", couple, block=False))
