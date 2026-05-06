"""
modules/rarity.py — /rarity command
Apni harem mein kitne Common/Rare/Legendary hain — full stats

Rarity numbers:
  1 → ⚪ Common
  2 → 🟣 Rare
  3 → 🟡 Legendary
  4 → 🟢 Medium
  5 → 💮 Special Edition
  6 → 🔞 Extreme
"""

from html import escape
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from waifu import application, user_collection


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

BAR_LENGTH = 12


def _bar(value: int, total: int) -> str:
    if total == 0:
        return "░" * BAR_LENGTH
    filled = round(BAR_LENGTH * value / total)
    return "▓" * filled + "░" * (BAR_LENGTH - filled)


def _percent(value: int, total: int) -> str:
    if total == 0:
        return "0.0"
    return f"{100 * value / total:.1f}"


def _normalize_rarity(rarity) -> int:
    """Rarity number ya purana string dono ko int mein convert karo."""
    if isinstance(rarity, int):
        return rarity
    # Purane string format ke liye
    rev = {v: k for k, v in RARITY_MAP.items()}
    return rev.get(str(rarity), 1)


async def rarity_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user

    # Support reply → show other user's stats
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        u_doc  = await user_collection.find_one({"id": target.id})
        name   = escape(target.first_name)
    else:
        u_doc = await user_collection.find_one({"id": user.id})
        name  = escape(user.first_name)

    if not u_doc:
        await update.message.reply_text("❌ Pehle kuch characters collect karo!")
        return

    chars = u_doc.get("characters", [])
    if not chars:
        await update.message.reply_text("❌ Teri harem abhi khaali hai!")
        return

    # Unique characters only
    unique_chars = list({c["id"]: c for c in chars}.values())
    total_unique = len(unique_chars)
    total_all    = len(chars)

    # Count per rarity
    rarity_count: dict[int, int] = {}
    for c in unique_chars:
        r = _normalize_rarity(c.get("rarity", 1))
        rarity_count[r] = rarity_count.get(r, 0) + 1

    # Total collection value
    total_value = sum(
        VALUE_MAP.get(_normalize_rarity(c.get("rarity", 1)), 100)
        for c in unique_chars
    )

    # Build rarity lines
    lines = []
    for r_num in RARITY_ORDER:
        count = rarity_count.get(r_num, 0)
        label = RARITY_MAP[r_num]
        bar   = _bar(count, total_unique)
        pct   = _percent(count, total_unique)
        value = VALUE_MAP.get(r_num, 100) * count
        lines.append(
            f"{label}\n"
            f"  [{bar}] <b>{count}</b> chars ({pct}%)\n"
            f"  💰 {value:,} coins"
        )

    rarity_text = "\n\n".join(lines)

    # Rarest char (highest rarity number first)
    rarest_line = ""
    for r_num in [6, 5, 3, 2, 4, 1]:
        match = next(
            (c for c in unique_chars if _normalize_rarity(c.get("rarity", 1)) == r_num),
            None
        )
        if match:
            rarest_name = escape(match.get("name", "Unknown"))
            rarest_line = f"\n🏆 <b>Rarest:</b> {rarest_name} ({RARITY_MAP.get(r_num, '?')})"
            break

    text = (
        f"📊 <b>{name}'s Rarity Stats</b>\n"
        f"{'─' * 28}\n"
        f"🗂 <b>{total_unique}</b> unique  ({total_all} total)\n"
        f"💎 Est. Value: <b>{total_value:,}</b> coins"
        f"{rarest_line}\n"
        f"{'─' * 28}\n\n"
        f"{rarity_text}"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


application.add_handler(CommandHandler("rarity", rarity_command, block=False))
  
