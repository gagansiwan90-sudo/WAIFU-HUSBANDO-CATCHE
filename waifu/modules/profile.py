"""
modules/profile.py — /profile command showing full user stats.
Cool aesthetic design with user PFP.
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

RARITY_ORDER = [1, 4, 2, 3, 5, 6]

VALUE_MAP = {
    1: 100,
    2: 600,
    3: 1500,
    4: 300,
    5: 5000,
    6: 8000,
}

RARITY_STARS = {
    1: "★☆☆☆☆☆",
    4: "★★☆☆☆☆",
    2: "★★★☆☆☆",
    3: "★★★★☆☆",
    5: "★★★★★☆",
    6: "★★★★★★",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _xp_for_level(level: int) -> int:
    return int(200 * (level ** 1.5))


def _calc_level(xp: int) -> tuple[int, int, int]:
    level = 1
    while _xp_for_level(level + 1) <= xp:
        level += 1
    floor = _xp_for_level(level)
    nxt   = _xp_for_level(level + 1)
    return level, xp - floor, nxt - floor


def _xp_bar(value: int, maximum: int, length: int = 10) -> str:
    filled = int(length * value / max(maximum, 1))
    empty  = length - filled
    return "🟪" * filled + "⬛" * empty


def _level_title(level: int) -> str:
    if level >= 50: return "👑 𝗟𝗲𝗴𝗲𝗻𝗱"
    if level >= 40: return "💎 𝗘𝗹𝗶𝘁𝗲"
    if level >= 30: return "🔥 𝗘𝘅𝗽𝗲𝗿𝘁"
    if level >= 20: return "⚡ 𝗔𝗱𝘃𝗮𝗻𝗰𝗲𝗱"
    if level >= 10: return "🌟 𝗜𝗻𝘁𝗲𝗿𝗺𝗲𝗱𝗶𝗮𝘁𝗲"
    return "🌱 𝗡𝗼𝘃𝗶𝗰𝗲"


def _get_rarity_num(rarity) -> int:
    if isinstance(rarity, int):
        return rarity
    rev = {v: k for k, v in RARITY_MAP.items()}
    return rev.get(rarity, 1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PROFILE COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def profile(update: Update, context: CallbackContext) -> None:
    # Target user
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        u_doc  = await user_collection.find_one({"id": target.id})
    elif context.args:
        username = context.args[0].lstrip("@")
        u_doc    = await user_collection.find_one({"username": username})
        target   = None
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

    # ── Rarity breakdown ──────────────────────────────────────────────
    rarity_count: dict[int, int] = {}
    for c in unique_chars:
        r = _get_rarity_num(c.get("rarity", 1))
        rarity_count[r] = rarity_count.get(r, 0) + 1

    # ── XP / Level ────────────────────────────────────────────────────
    level, xp_in, xp_need = _calc_level(xp)
    bar    = _xp_bar(xp_in, xp_need, 10)
    title  = _level_title(level)

    # ── Collection value ──────────────────────────────────────────────
    total_value = sum(
        VALUE_MAP.get(_get_rarity_num(c.get("rarity", 1)), 100)
        for c in unique_chars
    )

    # ── Rarity lines ──────────────────────────────────────────────────
    rarity_lines = []
    for r_num in RARITY_ORDER:
        count = rarity_count.get(r_num, 0)
        if count == 0:
            continue
        label = RARITY_MAP[r_num]
        rarity_lines.append(f"  {label} × <b>{count}</b>")
    rarity_text = "\n".join(rarity_lines) if rarity_lines else "  None yet 🌸"

    # ── Rarest char ───────────────────────────────────────────────────
    rarest_line = ""
    for r_num in [6, 5, 3, 2, 4, 1]:
        match = next(
            (c for c in unique_chars if _get_rarity_num(c.get("rarity", 1)) == r_num),
            None,
        )
        if match:
            rarest_name  = escape(match.get("name", "Unknown"))
            rarest_label = RARITY_MAP.get(r_num, "?")
            rarest_stars = RARITY_STARS.get(r_num, "")
            rarest_line  = f"\n🏆 <b>Rarest:</b> {rarest_name}\n     {rarest_label}  {rarest_stars}"
            break

    tag = f"@{username}" if username else f"#{uid}"

    text = (
        f"╔══════════════════════╗\n"
        f"  🌸 <b>𝗪𝗮𝗶𝗳𝘂𝗛𝘂𝗯 𝗣𝗿𝗼𝗳𝗶𝗹𝗲</b>\n"
        f"╚══════════════════════╝\n\n"
        f"👤 <b>{first_name}</b>  <code>{tag}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{title}  •  <b>Level {level}</b>\n"
        f"{bar}  <i>{xp_in:,}/{xp_need:,} XP</i>\n\n"
        f"┌─────────────────────\n"
        f"│ 💰 <b>Coins:</b>       {coins:,}\n"
        f"│ 🗂 <b>Collection:</b>  {unique_count} unique ({total_count} total)\n"
        f"│ 💎 <b>Est. Value:</b>  {total_value:,} coins\n"
        f"│ 🎯 <b>Guesses:</b>    {guesses}\n"
        f"│ ⚔️ <b>Duel Wins:</b>  {wins}\n"
        f"└─────────────────────"
        f"{rarest_line}\n\n"
        f"✨ <b>𝗥𝗮𝗿𝗶𝘁𝘆 𝗕𝗿𝗲𝗮𝗸𝗱𝗼𝘄𝗻:</b>\n"
        f"{rarity_text}"
    )

    # ── Photo — try to get user PFP first ─────────────────────────────
    photo: str | None = None

    # Try user's Telegram profile photo
    try:
        if target:
            photos = await context.bot.get_user_profile_photos(uid, limit=1)
            if photos and photos.photos:
                photo = photos.photos[0][-1].file_id
    except Exception:
        pass

    # Fallback: fav character image
    if not photo:
        if fav_id:
            fav_char = next((c for c in chars if c["id"] == fav_id), None)
            photo    = (fav_char or {}).get("img_url")

    # Fallback: bot photo
    if not photo and PHOTO_URL:
        photo = random.choice(PHOTO_URL)

    if photo:
        await update.message.reply_photo(
            photo, caption=text, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


application.add_handler(CommandHandler("profile", profile, block=False))
    
