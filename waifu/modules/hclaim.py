"""
modules/hclaim.py — Daily Free Character Claim
5 min baad claim message delete
"""
import random
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from waifu import application, db
from waifu.modules.auto_delete import schedule_delete, HCLAIM_DELAY

ALLOWED_GROUP_ID   = -1003865428134
ALLOWED_GROUP_LINK = "https://t.me/Anime_InfinityChatGroup"

users_col   = db["users"]
hclaim_col  = db["hclaim_cooldowns"]
chars_col   = db["anime_characters"]

RARITY_EMOJI = {
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
    pipeline = [{"$sample": {"size": 1}}]
    result = await chars_col.aggregate(pipeline).to_list(length=1)
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

async def _add_char_to_harem(user_id: int, char: dict):
    char_entry = {
        "id":      char.get("id"),
        "name":    char.get("name"),
        "anime":   char.get("anime"),
        "rarity":  char.get("rarity"),
        "img_url": char.get("img_url"),
    }
    await users_col.update_one(
        {"user_id": user_id},
        {"$push": {"characters": char_entry}, "$inc": {"total_characters": 1}},
        upsert=True
    )

async def hclaim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat    = update.effective_chat
    user    = update.effective_user
    message = update.effective_message

    if chat.id != ALLOWED_GROUP_ID:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🌸 Join Group", url=ALLOWED_GROUP_LINK)
        ]])
        await message.reply_text(
            "❌ <b>/hclaim</b> sirf ek special group mein available hai!\n\n"
            "👇 Niche join karo aur roz free character lo:",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        return

    last_claim = await _get_cooldown(user.id)
    if last_claim:
        next_claim = last_claim + timedelta(hours=24)
        now        = _now_utc()
        if now < next_claim:
            remaining  = next_claim - now
            hours, rem = divmod(int(remaining.total_seconds()), 3600)
            minutes    = rem // 60
            await message.reply_text(
                f"⏳ <b>{user.first_name}</b>, tumne aaj already claim kar liya!\n\n"
                f"🕐 Agli baar: <b>{hours}h {minutes}m</b> baad aao~",
                parse_mode=ParseMode.HTML,
            )
            return

    char = await _get_random_character()
    if not char:
        await message.reply_text("⚠️ Abhi koi character available nahi hai. Baad mein try karo!")
        return

    await _add_char_to_harem(user.id, char)
    await _set_cooldown(user.id)

    rarity_num  = char.get("rarity", 1)
    rarity_text = RARITY_EMOJI.get(rarity_num, "⚪ Common") if isinstance(rarity_num, int) else str(rarity_num)
    char_name   = char.get("name", "Unknown")
    anime_name  = char.get("anime", "Unknown")
    img_url     = char.get("img_url", "")

    caption = (
        f"🎴 <b>Daily Claim!</b>\n\n"
        f"🌸 <b>{char_name}</b>\n"
        f"📺 Anime: <i>{anime_name}</i>\n"
        f"✨ Rarity: {rarity_text}\n\n"
        f"👤 Claimed by: <a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
        f"⏰ Wapas aao 24 ghante baad!\n\n"
        f"<i>🗑 Yeh message 5 min mein delete ho jaayega</i>"
    )

    try:
        if img_url:
            sent = await message.reply_photo(
                photo=img_url, caption=caption, parse_mode=ParseMode.HTML,
            )
        else:
            sent = await message.reply_text(caption, parse_mode=ParseMode.HTML)
        # 5 min baad delete
        schedule_delete(context.bot, chat.id, sent.message_id, HCLAIM_DELAY)
    except Exception:
        sent = await message.reply_text(caption, parse_mode=ParseMode.HTML)
        schedule_delete(context.bot, chat.id, sent.message_id, HCLAIM_DELAY)


application.add_handler(CommandHandler("hclaim", hclaim_command))
                
