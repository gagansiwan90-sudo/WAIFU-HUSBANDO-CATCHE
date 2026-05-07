"""
modules/hclaim.py — Daily Free Character Claim
Deletes claim message after 5 minutes.
"""
import random
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from waifu import application, user_collection, collection, db
from waifu.modules.auto_delete import schedule_delete, HCLAIM_DELAY

ALLOWED_GROUP_ID   = -1003865428134
ALLOWED_GROUP_LINK = "https://t.me/Anime_InfinityChatGroup"

hclaim_col = db["hclaim_cooldowns"]

RARITY_MAP = {
    1: "⚪ Common",
    2: "🟣 Rare",
    3: "🟡 Legendary",
    4: "🟢 Medium",
    5: "💮 Special Edition",
    6: "🔞 Extreme",
}

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _get_random_character() -> dict | None:
    """Pick a random character from the main characters collection."""
    pipeline = [{"$sample": {"size": 1}}]
    result = await collection.aggregate(pipeline).to_list(length=1)
    return result[0] if result else None


async def _get_cooldown(user_id: int) -> datetime | None:
    doc = await hclaim_col.find_one({"user_id": user_id})
    if doc and "last_claim" in doc:
        return doc["last_claim"].replace(tzinfo=timezone.utc)
    return None


async def _set_cooldown(user_id: int):
    await hclaim_col.update_one(
        {"user_id": user_id},
        {"$set": {"last_claim": _now_utc()}},
        upsert=True
    )


async def hclaim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat    = update.effective_chat
    user    = update.effective_user
    message = update.effective_message

    # ── Group check ───────────────────────────────────────────────────────
    if chat.id != ALLOWED_GROUP_ID:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🌸 Join Group", url=ALLOWED_GROUP_LINK)
        ]])
        await message.reply_text(
            "❌ <b>/hclaim</b> is only available in a special group!\n\n"
            "👇 Join below to get a free character every day:",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        return

    # ── Cooldown check ────────────────────────────────────────────────────
    last_claim = await _get_cooldown(user.id)
    if last_claim:
        next_claim = last_claim + timedelta(hours=24)
        now        = _now_utc()
        if now < next_claim:
            remaining  = next_claim - now
            hours, rem = divmod(int(remaining.total_seconds()), 3600)
            minutes    = rem // 60
            await message.reply_text(
                f"⏳ <b>{user.first_name}</b>, you already claimed today!\n\n"
                f"🕐 Come back in: <b>{hours}h {minutes}m</b>",
                parse_mode=ParseMode.HTML,
            )
            return

    # ── Get random character ──────────────────────────────────────────────
    char = await _get_random_character()
    if not char:
        await message.reply_text("⚠️ No characters available right now. Try again later!")
        return

    # ── Add to harem — same format as waifu_drop ─────────────────────────
    rarity     = char.get("rarity", 1)
    rarity_txt = RARITY_MAP.get(rarity, "⚪ Common") if isinstance(rarity, int) else str(rarity)

    await user_collection.update_one(
        {"id": user.id},
        {
            "$push": {"characters": char},
            "$inc":  {"total_guesses": 1},
            "$set":  {"username": user.username, "first_name": user.first_name},
            "$setOnInsert": {
                "coins":     0,
                "wins":      0,
                "xp":        0,
                "favorites": [],
            },
        },
        upsert=True,
    )

    await _set_cooldown(user.id)

    # ── Success message ───────────────────────────────────────────────────
    caption = (
        f"🎴 <b>Daily Claim!</b>\n\n"
        f"🌸 <b>{char.get('name', 'Unknown')}</b>\n"
        f"📺 Anime: <i>{char.get('anime', 'Unknown')}</i>\n"
        f"✨ Rarity: {rarity_txt}\n\n"
        f"👤 Claimed by: <a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
        f"⏰ Come back in 24 hours!\n\n"
        f"<i>🗑 This message will be deleted in 5 minutes.</i>"
    )

    img_url = char.get("img_url", "")
    try:
        if img_url:
            sent = await message.reply_photo(
                photo=img_url, caption=caption, parse_mode=ParseMode.HTML,
            )
        else:
            sent = await message.reply_text(caption, parse_mode=ParseMode.HTML)
    except Exception:
        sent = await message.reply_text(caption, parse_mode=ParseMode.HTML)

    schedule_delete(context.bot, chat.id, sent.message_id, HCLAIM_DELAY)


application.add_handler(CommandHandler("hclaim", hclaim_command))
                                 
