"""
hclaim.py — Daily Free Character Claim Module
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• /hclaim  → Roz ek random character milega (group -1003865428134 mein hi)
• Dusre group mein use karo → join link wala message aata hai
• 24 ghante cooldown per user
• Character seedha user ki harem mein jaata hai
"""

import random
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

# ── Bot ke baaki modules se import (adjust karo agar tumhare paths alag hain) ──
from waifu import application, db

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIG — yahan apna group set karo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALLOWED_GROUP_ID   = -1003865428134          # Sirf is group mein /hclaim chalega
ALLOWED_GROUP_LINK = "https://t.me/Anime_InfinityChatGroup"

# MongoDB collections
users_col   = db["users"]
hclaim_col  = db["hclaim_cooldowns"]   # New collection — cooldown track karne ke liye
chars_col   = db["anime_characters"]   # Master character catalogue

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _get_random_character() -> dict | None:
    """DB se ek random character pick karo."""
    pipeline = [{"$sample": {"size": 1}}]
    result = await chars_col.aggregate(pipeline).to_list(length=1)
    return result[0] if result else None


async def _get_cooldown(user_id: int) -> datetime | None:
    """User ka last claim time lo."""
    doc = await hclaim_col.find_one({"user_id": user_id})
    if doc and "last_claim" in doc:
        return doc["last_claim"].replace(tzinfo=timezone.utc)
    return None


async def _set_cooldown(user_id: int):
    """User ka claim time update karo."""
    await hclaim_col.update_one(
        {"user_id": user_id},
        {"$set": {"last_claim": _now_utc()}},
        upsert=True
    )


async def _add_char_to_harem(user_id: int, char: dict):
    """Character user ki harem mein add karo (existing bot ka format follow karta hai)."""
    char_entry = {
        "id":     char.get("id"),
        "name":   char.get("name"),
        "anime":  char.get("anime"),
        "rarity": char.get("rarity"),
        "img_url": char.get("img_url"),
    }
    await users_col.update_one(
        {"user_id": user_id},
        {
            "$push": {"characters": char_entry},
            "$inc":  {"total_characters": 1}
        },
        upsert=True
    )


RARITY_EMOJI = {
    1: "⚪ Common",
    2: "🟣 Rare",
    3: "🟡 Legendary",
    4: "🟢 Medium",
    5: "💮 Special Edition",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def hclaim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat    = update.effective_chat
    user    = update.effective_user
    message = update.effective_message

    # ── 1. Sirf allowed group mein kaam karo ──────────────────────────────
    if chat.id != ALLOWED_GROUP_ID:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌸 Join Group", url=ALLOWED_GROUP_LINK)]
        ])
        await message.reply_text(
            "❌ <b>/hclaim</b> sirf ek special group mein available hai!\n\n"
            "👇 Niche join karo aur roz free character lo:",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        return

    # ── 2. Cooldown check ─────────────────────────────────────────────────
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

    # ── 3. Random character lo ────────────────────────────────────────────
    char = await _get_random_character()
    if not char:
        await message.reply_text("⚠️ Abhi koi character available nahi hai. Baad mein try karo!")
        return

    # ── 4. Harem mein add karo + cooldown set karo ────────────────────────
    await _add_char_to_harem(user.id, char)
    await _set_cooldown(user.id)

    # ── 5. Success message ────────────────────────────────────────────────
    rarity_text = RARITY_EMOJI.get(char.get("rarity", 1), "⚪ Common")
    char_name   = char.get("name", "Unknown")
    anime_name  = char.get("anime", "Unknown")
    img_url     = char.get("img_url", "")

    caption = (
        f"🎴 <b>Daily Claim!</b>\n\n"
        f"🌸 <b>{char_name}</b>\n"
        f"📺 Anime: <i>{anime_name}</i>\n"
        f"✨ Rarity: {rarity_text}\n\n"
        f"👤 Claimed by: <a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
        f"⏰ Wapas aao 24 ghante baad!"
    )

    try:
        if img_url:
            await message.reply_photo(
                photo=img_url,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text(caption, parse_mode=ParseMode.HTML)
    except Exception:
        # Agar photo fail ho toh plain text fallback
        await message.reply_text(caption, parse_mode=ParseMode.HTML)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REGISTER HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def register(app=None):
    """__main__.py mein call karo: from waifu.modules.hclaim import register; register()"""
    target = app or application
    target.add_handler(CommandHandler("hclaim", hclaim_command))
