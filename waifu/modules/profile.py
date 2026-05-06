"""
modules/profile.py — /profile command showing full user stats.
Updated with correct rarity numbers (1-6).
"""
import math
import random
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from waifu import application, user_collection, PHOTO_URL


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RARITY CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RARITY_MAP = {
    1: "⚪ Common",
    2: "🟣 Rare",
    3: "🟡 Legendary",
    4: "🟢 Medium",
    5: "💮 Special Edition",
    6: "🔞 Extreme",
}

RARITY_ORDER = [1, 4, 2, 3, 5, 6]  # Common → Medium → Rare → Legendary → Special → Extreme

VALUE_MAP = {
    1: 100,
    2: 600,
    3: 1500,
    4: 300,
    5: 5000,
    6: 8000,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _xp_for_level(level: int) -> int:
    return int(200 * (level ** 1.5))


def _calc_level(xp: int) -> tuple[int, int, int]:
    """Returns (level, xp_into_level, xp_needed)."""
    level = 1
    while _xp_for_level(level + 1) <= xp:
        level += 1
    floor = _xp_for_level(level)
    nxt   = _xp_for_level(level + 1)
    return level, xp - floor, nxt - floor


def _bar(value: int, maximum: int, length: int = 10) -> str:
    filled = int(length * value / max(maximum, 1))
    return "▓" * filled + "░" * (length - filled)


def _get_rarity_label(rarity) -> str:
    """Rarity number ya string dono handle karta hai."""
    if isinstance(rarity, int):
        return RARITY_MAP.get(rarity, "⚪ Common")
    # Purane string format ke liye fallback
    return str(rarity) if rarity else "⚪ Common"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PROFILE COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def profile(update: Update, context: CallbackContext) -> None:
    # Support /profile or reply to another user
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        u_doc  = await user_collection.find_one({"id": target.id})
    elif context.args:
        username = context.args[0].lstrip("@")
        u_doc = await user_collection.find_one({"username": username})
    else:
        target = update.effective_user
        u_doc  = await user_collection.find_one({"id": target.id})

    if not u_doc:
        await update.message.reply_text("❌ That user hasn't played yet.")
        return

    uid        = u_doc["id"]
    first_name = escape(u_doc.get("first_name", "User"))
    username   = u_doc.get("username")
    coins      = u_doc.get("coins", 0)
    chars      = u_doc.get("characters", [])
    wins       = u_doc.get("wins", 0)
    guesses    = u_doc.get("total_guesses", 0)
    xp         = u_doc.get("xp", 0)
    fav_id     = (u_doc.get("favorites") or [None])[0]

    unique_chars = list({c["id"]: c for c in chars}.values())
    unique_count = len(unique_chars)
    total_count  = len(chars)

    # ── Rarity breakdown ────────────────────────────────────────────────
    rarity_count: dict[int, int] = {}
    for c in unique_chars:
        r = c.get("rarity", 1)
        if isinstance(r, str):
            # String se number map karo (purane data ke liye)
            rev = {v: k for k, v in RARITY_MAP.items()}
            r = rev.get(r, 1)
        rarity_count[r] = rarity_count.get(r, 0) + 1

    # ── XP / Level ──────────────────────────────────────────────────────
    level, xp_in, xp_need = _calc_level(xp)
    bar = _bar(xp_in, xp_need, 12)

    # ── Collection value ────────────────────────────────────────────────
    total_value = sum(
        VALUE_MAP.get(c.get("rarity", 1) if isinstance(c.get("rarity"), int) else 1, 100)
        for c in unique_chars
    )

    # ── Rarity lines ────────────────────────────────────────────────────
    rarity_lines = []
    for r_num in RARITY_ORDER:
        count = rarity_count.get(r_num, 0)
        if count == 0:
            continue
        label = RARITY_MAP[r_num]
        rarity_lines.append(f"  {label}: <b>{count}</b>")

    rarity_text = "\n".join(rarity_lines) if rarity_lines else "  None yet"

    # ── Rarest char ─────────────────────────────────────────────────────
    rarest_line = ""
    for r_num in [6, 5, 3, 2, 4, 1]:  # Highest to lowest
        match = next(
            (c for c in unique_chars
             if (c.get("rarity") == r_num or
                 RARITY_MAP.get(r_num) == c.get("rarity"))),
            None
        )
        if match:
            rarest_name = escape(match.get("name", "Unknown"))
            rarest_line = f"\n🏆 <b>Rarest:</b> {rarest_name} ({RARITY_MAP.get(r_num, '?')})"
            break

    tag  = f"@{username}" if username else f"#{uid}"
    text = (
        f"👤 <b>{first_name}</b>  <code>{tag}</code>\n"
        f"{'─' * 28}\n"
        f"⭐ Level <b>{level}</b>  [{bar}]\n"
        f"   <i>{xp_in:,} / {xp_need:,} XP</i>\n\n"
        f"💰 Coins:      <b>{coins:,}</b>\n"
        f"🗂 Collection: <b>{unique_count}</b> unique  ({total_count} total)\n"
        f"💎 Est. Value: <b>{total_value:,}</b> coins\n"
        f"🎯 Guesses:   <b>{guesses}</b>\n"
        f"⚔️ Duel wins: <b>{wins}</b>"
        f"{rarest_line}\n\n"
        f"<b>✨ Rarity Breakdown:</b>\n"
        f"{rarity_text}"
    )

    # ── Photo ───────────────────────────────────────────────────────────
    photo: str | None = None
    if fav_id:
        fav_char = next((c for c in chars if c["id"] == fav_id), None)
        photo    = (fav_char or {}).get("img_url")
    if not photo and PHOTO_URL:
        photo = random.choice(PHOTO_URL)

    if photo:
        await update.message.reply_photo(
            photo, caption=text, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


application.add_handler(CommandHandler("profile", profile, block=False))
    
