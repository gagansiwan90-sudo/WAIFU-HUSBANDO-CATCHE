"""
modules/mine.py

/mine — Pay 500 coins to mine for rewards!
- Random coins reward
- Chance to get a character
- 5 minute cooldown
- RESTRICTED to specific group only
"""
import asyncio
import random
import time
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from waifu import application, collection, user_collection

_ALLOWED_GROUP = -1003865428134
_GROUP_LINK    = "https://t.me/Anime_InfinityChatGroup"
_MINE_COST     = 500
_COOLDOWN      = 300  # 5 minutes

# Mine outcomes
_OUTCOMES = [
    {"type": "coins", "amount": 200,  "chance": 20, "msg": "💨 Dust... barely anything here."},
    {"type": "coins", "amount": 500,  "chance": 25, "msg": "⛏️ Found some ore! Break even!"},
    {"type": "coins", "amount": 800,  "chance": 20, "msg": "💎 Nice find! Some shiny gems!"},
    {"type": "coins", "amount": 1200, "chance": 15, "msg": "🪙 Rich vein! Lots of gold!"},
    {"type": "coins", "amount": 2000, "chance": 10, "msg": "💰 Jackpot! A treasure chest!"},
    {"type": "coins", "amount": 3000, "chance": 5,  "msg": "🌟 Legendary ore! Massive haul!"},
    {"type": "char",  "amount": 0,    "chance": 5,  "msg": "✨ A mysterious figure emerged from the mine!"},
]

_MINE_EMOJIS = ["⛏️", "🪨", "💎", "🏔️", "🌋", "⚒️"]
_MINE_STAGES = [
    "⛏️ Digging deep...",
    "💨 Breaking through the rocks...",
    "🔦 Something is glowing...",
    "😲 Wait... what's this?!",
]


def _fmt_time(secs: int) -> str:
    m, s = divmod(secs, 60)
    return f"{m}m {s}s" if m else f"{s}s"


def _pick_outcome() -> dict:
    roll = random.randint(1, 100)
    cumulative = 0
    for outcome in _OUTCOMES:
        cumulative += outcome["chance"]
        if roll <= cumulative:
            return outcome
    return _OUTCOMES[0]


async def mine(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user    = update.effective_user

    # Group check
    if chat_id != _ALLOWED_GROUP:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✨ Join Our Group", url=_GROUP_LINK)
        ]])
        await update.message.reply_text(
            "❌ <b>This command only works in our main group!</b>\n\n"
            "🌸 Join us to start mining!",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    # Get user doc
    user_doc = await user_collection.find_one({"id": user.id})
    now      = time.time()

    # Cooldown check
    last_mine = (user_doc or {}).get("last_mine", 0)
    if now - last_mine < _COOLDOWN:
        remaining = int(_COOLDOWN - (now - last_mine))
        await update.message.reply_text(
            f"⏳ <b>Mine is recharging!</b>\n\n"
            f"Come back in <b>{_fmt_time(remaining)}</b> ⛏️",
            parse_mode=ParseMode.HTML,
        )
        return

    # Coins check
    coins = (user_doc or {}).get("coins", 0)
    if coins < _MINE_COST:
        await update.message.reply_text(
            f"❌ <b>Not enough coins!</b>\n\n"
            f"Mining costs <b>{_MINE_COST:,} 🪙</b>\n"
            f"Your balance: <b>{coins:,} 🪙</b>\n\n"
            f"<i>Earn more with /daily or /guess!</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Deduct cost immediately
    await user_collection.update_one(
        {"id": user.id},
        {
            "$inc": {"coins": -_MINE_COST},
            "$set": {
                "last_mine":  now,
                "username":   user.username,
                "first_name": user.first_name,
            },
        },
        upsert=True,
    )

    # Animated mining stages
    stage_msg = await update.message.reply_text(
        f"⛏️ <b>{escape(user.first_name)} is mining...</b>\n\n"
        f"{_MINE_STAGES[0]}",
        parse_mode=ParseMode.HTML,
    )

    for stage in _MINE_STAGES[1:]:
        await asyncio.sleep(1)
        try:
            await stage_msg.edit_text(
                f"⛏️ <b>{escape(user.first_name)} is mining...</b>\n\n"
                f"{stage}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    await asyncio.sleep(1)

    # Pick outcome
    outcome = _pick_outcome()

    if outcome["type"] == "coins":
        reward  = outcome["amount"]
        profit  = reward - _MINE_COST
        profit_txt = f"+{profit:,}" if profit >= 0 else f"{profit:,}"

        await user_collection.update_one(
            {"id": user.id},
            {"$inc": {"coins": reward}},
        )

        new_balance = coins - _MINE_COST + reward

        result_text = (
            f"⛏️ <b>Mine Result!</b>\n\n"
            f"{outcome['msg']}\n\n"
            f"💸 Paid: <b>{_MINE_COST:,} 🪙</b>\n"
            f"💰 Found: <b>{reward:,} 🪙</b>\n"
            f"📊 Profit: <b>{profit_txt} 🪙</b>\n\n"
            f"👛 Balance: <b>{new_balance:,} 🪙</b>\n\n"
            f"⏰ Mine recharges in <b>5 minutes</b>!"
        )

        try:
            await stage_msg.edit_text(result_text, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)

    elif outcome["type"] == "char":
        # Get random character from DB
        all_chars = await collection.find({}).to_list(length=5000)

        if not all_chars:
            # No characters — give coins instead
            fallback = 1500
            await user_collection.update_one(
                {"id": user.id},
                {"$inc": {"coins": fallback}},
            )
            result_text = (
                f"⛏️ <b>Mine Result!</b>\n\n"
                f"✨ Something special but...\n"
                f"💰 Got <b>{fallback:,} 🪙</b> instead!\n\n"
                f"⏰ Mine recharges in <b>5 minutes</b>!"
            )
            try:
                await stage_msg.edit_text(result_text, parse_mode=ParseMode.HTML)
            except Exception:
                await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)
            return

        char = random.choice(all_chars)

        # Add character to user
        await user_collection.update_one(
            {"id": user.id},
            {"$push": {"characters": char}},
        )

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📖 My Harem",
                switch_inline_query_current_chat=f"collection.{user.id}",
            )
        ]])

        caption = (
            f"⛏️ <b>Mine Result!</b>\n\n"
            f"{outcome['msg']}\n\n"
            f"🌸 <b>{escape(char['name'])}</b>\n"
            f"📺 {escape(char['anime'])}\n"
            f"💎 {char.get('rarity', 'Unknown')}\n\n"
            f"✨ Added to your harem!\n"
            f"💸 Paid: <b>{_MINE_COST:,} 🪙</b>\n\n"
            f"⏰ Mine recharges in <b>5 minutes</b>!"
        )

        try:
            await stage_msg.delete()
        except Exception:
            pass

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

        await update.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=kb)


application.add_handler(CommandHandler("mine", mine, block=False))
