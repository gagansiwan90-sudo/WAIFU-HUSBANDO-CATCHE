"""
modules/hclaim.py

/hclaim — Claim a random character once every 24 hours.
RESTRICTED to specific group only.
"""
import random
import time
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from waifu import application, collection, user_collection

_ALLOWED_GROUP = -1003865428134
_COOLDOWN      = 86_400  # 24 hours


def _fmt_time(secs: int) -> str:
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")


async def hclaim(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user    = update.effective_user

    # Only allowed in specific group
    if chat_id != _ALLOWED_GROUP:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✨ Join Our Group",
                url=f"https://t.me/+{str(_ALLOWED_GROUP)[4:]}"
            )
        ]])
        await update.message.reply_text(
            "❌ <b>This command only works in our main group!</b>\n\n"
            "🌸 Join us to claim your daily character!",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    # Check cooldown
    user_doc = await user_collection.find_one({"id": user.id})
    now      = time.time()
    last     = (user_doc or {}).get("last_hclaim", 0)

    if now - last < _COOLDOWN:
        remaining = int(_COOLDOWN - (now - last))
        await update.message.reply_text(
            f"⏳ <b>Already claimed today!</b>\n\n"
            f"Come back in <b>{_fmt_time(remaining)}</b> 🌸",
            parse_mode=ParseMode.HTML,
        )
        return

    # Get random character
    all_chars = await collection.find({}).to_list(length=5000)
    if not all_chars:
        await update.message.reply_text("❌ No characters in DB yet!")
        return

    char = random.choice(all_chars)

    # Give character to user
    await user_collection.update_one(
        {"id": user.id},
        {
            "$push": {"characters": char},
            "$set":  {
                "username":    user.username,
                "first_name":  user.first_name,
                "last_hclaim": now,
            },
            "$setOnInsert": {
                "coins": 0, "xp": 0, "wins": 0,
                "favorites": [], "total_guesses": 0,
            },
        },
        upsert=True,
    )

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📖 My Harem",
            switch_inline_query_current_chat=f"collection.{user.id}",
        )
    ]])

    caption = (
        f"🎁 <b>Daily Claim!</b>\n\n"
        f"<a href='tg://user?id={user.id}'>{escape(user.first_name)}</a> "
        f"received a character!\n\n"
        f"🌸 <b>{escape(char['name'])}</b>\n"
        f"📺 {escape(char['anime'])}\n"
        f"💎 {char.get('rarity', 'Unknown')}\n\n"
        f"✨ Added to your harem!\n"
        f"⏰ Come back in <b>24 hours</b> for next claim!"
    )

    photo = char.get("img_url")
    if photo:
        try:
            await update.message.reply_photo(
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
            return
        except Exception:
            pass

    await update.message.reply_text(
        caption,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


application.add_handler(CommandHandler("hclaim", hclaim, block=False))
