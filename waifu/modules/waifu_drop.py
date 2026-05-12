"""
modules/waifu_drop.py

Core game loop:
  - Rarity based drop chance
  - Special characters system (owner set kare)
  - Message counter → threshold drop
  - APScheduler timed drop every N minutes
  - /guess to claim
  - /fav to favourite
  - Auto-delete drop message on claim OR after 10 minutes
  - Wrong guess reply auto-delete after 3 seconds
  - Royal style capture message with time taken
"""
import asyncio
import random
import time
from html import escape

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, MessageHandler, filters

from waifu import (
    application, collection, group_user_totals_collection,
    top_global_groups_collection, user_collection, user_totals_collection,
    LOGGER, OWNER_ID, db,
)
from waifu.config import Config

# ── Per-chat in-memory state ──────────────────────────────────────────────────
_active_char:      dict[int, dict]  = {}
_active_msg:       dict[int, int]   = {}
_active_time:      dict[int, float] = {}
_claimed:          dict[int, int]   = {}
_msg_counts:       dict[int, int]   = {}
_last_user:        dict[int, dict]  = {}
_warned:           dict[int, float] = {}
_sent_ids:         dict[int, list]  = {}
_registered_chats: set[int]         = set()

scheduler = AsyncIOScheduler(timezone="UTC")

_XP_PER_GUESS     = 50
_DROP_EXPIRE_SEC  = 600  # 10 minutes
_WRONG_DELETE_SEC = 3

# Special characters collection
special_collection = db["special_characters"]

# Rarity drop weights
RARITY_WEIGHTS = {
    "⚪ Common":          40,
    "🟢 Medium":          25,
    "🟣 Rare":            20,
    "🟡 Legendary":       10,
    "💮 Special Edition": 4,
    "🔞 Extreme":         1,
}

# Special character extra rare weight
_SPECIAL_WEIGHT = 1  # 0.5% effective chance

# Rarity display map
RARITY_DISPLAY = {
    "⚪ Common":          "⚪ Common",
    "🟢 Medium":          "🟢 Medium",
    "🟣 Rare":            "🟣 Rare",
    "🟡 Legendary":       "🟡 Legendary",
    "💮 Special Edition": "💮 Special Edition",
    "🔞 Extreme":         "🔞 Extreme",
}


def _drop_caption(char: dict) -> str:
    rarity = char.get("rarity", "⚪ Common")
    rarity_label = RARITY_DISPLAY.get(rarity, rarity)
    is_special = char.get("is_special", False)
    special_tag = "🌟 <b>SPECIAL DROP!</b>\n" if is_special else ""
    return (
        f"{special_tag}"
        f"✨ A <b>{rarity_label}</b> Character Appears! ✨\n"
        f"🔍 Use /guess to claim this mysterious character!\n"
        f"🪄 Hurry, before someone else snatches them!"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _chat_frequency(chat_id: int) -> int:
    doc = await user_totals_collection.find_one({"chat_id": chat_id})
    return int(doc["message_frequency"]) if doc and "message_frequency" in doc \
        else Config.DEFAULT_MSG_FREQUENCY


def _rolling_window_size(total_chars: int) -> int:
    return max(20, total_chars // 2)


async def _safe_delete(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _delete_after(bot, chat_id: int, message_id: int, delay: int) -> None:
    await asyncio.sleep(delay)
    await _safe_delete(bot, chat_id, message_id)


async def _safe_send(bot, chat_id: int, text: str, **kwargs):
    try:
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception as e:
        LOGGER.warning("Failed to send message in chat %s: %s", chat_id, e)
        return None


async def _pick_character(all_chars: list, sent: list) -> dict:
    """Pick character based on rarity weights + special characters."""

    # Get special characters
    special_docs = await special_collection.find({}).to_list(length=500)
    special_ids  = {s["char_id"] for s in special_docs}

    # Separate chars into groups
    unsent = [c for c in all_chars if c["id"] not in sent]
    if not unsent:
        unsent = all_chars

    # Build weighted pool
    weighted_pool = []
    for char in unsent:
        rarity  = char.get("rarity", "⚪ Common")
        weight  = RARITY_WEIGHTS.get(rarity, 10)

        # Special characters get extra rare weight
        if char["id"] in special_ids:
            weight = _SPECIAL_WEIGHT
            char   = {**char, "is_special": True}

        weighted_pool.append((char, weight))

    if not weighted_pool:
        return random.choice(all_chars)

    chars   = [c for c, _ in weighted_pool]
    weights = [w for _, w in weighted_pool]

    return random.choices(chars, weights=weights, k=1)[0]


async def _expire_drop(bot, chat_id: int, char_id: str) -> None:
    await asyncio.sleep(_DROP_EXPIRE_SEC)

    current = _active_char.get(chat_id)
    if not current or current.get("id") != char_id:
        return

    _active_char.pop(chat_id, None)
    _claimed.pop(chat_id, None)
    _active_time.pop(chat_id, None)

    msg_id = _active_msg.pop(chat_id, None)
    if msg_id:
        await _safe_delete(bot, chat_id, msg_id)

    try:
        expire_msg = await bot.send_message(
            chat_id=chat_id,
            text="⏰ <b>The character got away!</b>\n<i>No one claimed them in time...</i>",
            parse_mode=ParseMode.HTML,
        )
        asyncio.create_task(_delete_after(bot, chat_id, expire_msg.message_id, 5))
    except Exception:
        pass


async def _send_drop(chat_id: int, bot) -> None:
    all_chars = await collection.find({}).to_list(length=5000)
    if not all_chars:
        LOGGER.debug("No characters in DB — skipping drop for chat %s", chat_id)
        return

    window = _rolling_window_size(len(all_chars))
    sent   = _sent_ids.get(chat_id, [])

    # Pick character with rarity weights
    char = await _pick_character(all_chars, sent)

    new_sent = sent + [char["id"]]
    _sent_ids[chat_id] = new_sent[-window:]

    _active_char[chat_id] = char
    _active_time[chat_id] = time.time()
    _claimed.pop(chat_id, None)

    try:
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=char["img_url"],
            caption=_drop_caption(char),
            parse_mode=ParseMode.HTML,
        )
        _active_msg[chat_id] = msg.message_id
        LOGGER.info("Drop sent to chat %s: %s (%s)%s",
                    chat_id, char["name"], char.get("rarity", "?"),
                    " [SPECIAL]" if char.get("is_special") else "")
        asyncio.create_task(_expire_drop(bot, chat_id, char["id"]))

    except Exception as e:
        _active_char.pop(chat_id, None)
        _active_time.pop(chat_id, None)
        LOGGER.warning("Drop failed in chat %s: %s", chat_id, e)


# ── Scheduler ─────────────────────────────────────────────────────────────────

async def _timed_drop_job(bot) -> None:
    for chat_id in list(_registered_chats):
        await _send_drop(chat_id, bot)


def start_scheduler(bot) -> None:
    scheduler.add_job(
        _timed_drop_job,
        trigger=IntervalTrigger(minutes=Config.DROP_INTERVAL_MIN),
        kwargs={"bot": bot},
        id="timed_drop",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    LOGGER.info("Drop scheduler started — interval: every %d min", Config.DROP_INTERVAL_MIN)


# ── Message counter ───────────────────────────────────────────────────────────

async def message_counter(update: Update, context: CallbackContext) -> None:
    if not update.effective_chat or update.effective_chat.type == "private":
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    _registered_chats.add(chat_id)

    last = _last_user.get(chat_id)
    if last and last["user_id"] == user_id:
        last["count"] += 1
        if last["count"] >= 10:
            warned_at = _warned.get(user_id, 0)
            if time.time() - warned_at < 600:
                return
            _warned[user_id] = time.time()
            try:
                await update.message.reply_text(
                    f"⚠️ {escape(update.effective_user.first_name)}, slow down!\n"
                    f"Your messages will be ignored for 10 minutes."
                )
            except Exception:
                pass
            return
    else:
        _last_user[chat_id] = {"user_id": user_id, "count": 1}

    _msg_counts[chat_id] = _msg_counts.get(chat_id, 0) + 1
    freq = await _chat_frequency(chat_id)
    if _msg_counts[chat_id] >= freq:
        _msg_counts[chat_id] = 0
        await _send_drop(chat_id, context.bot)


# ── /guess ────────────────────────────────────────────────────────────────────

async def guess(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    bot     = context.bot

    char = _active_char.get(chat_id)
    if not char:
        return

    if chat_id in _claimed:
        msg = await _safe_send(
            bot, chat_id,
            "❌ Already claimed by someone else! Wait for the next character.",
        )
        if msg:
            asyncio.create_task(_delete_after(bot, chat_id, msg.message_id, _WRONG_DELETE_SEC))
        asyncio.create_task(_delete_after(bot, chat_id, update.message.message_id, _WRONG_DELETE_SEC))
        return

    user_guess = " ".join(context.args).strip().lower() if context.args else ""
    if not user_guess:
        msg = await _safe_send(bot, chat_id, "Usage: /guess <character name>")
        if msg:
            asyncio.create_task(_delete_after(bot, chat_id, msg.message_id, _WRONG_DELETE_SEC))
        asyncio.create_task(_delete_after(bot, chat_id, update.message.message_id, _WRONG_DELETE_SEC))
        return

    if any(bad in user_guess for bad in ("()", "&&", "||", "<script")):
        msg = await _safe_send(bot, chat_id, "❌ Invalid characters in guess.")
        if msg:
            asyncio.create_task(_delete_after(bot, chat_id, msg.message_id, _WRONG_DELETE_SEC))
        asyncio.create_task(_delete_after(bot, chat_id, update.message.message_id, _WRONG_DELETE_SEC))
        return

    name_parts = char["name"].lower().split()
    correct = (
        sorted(name_parts) == sorted(user_guess.split())
        or any(part == user_guess for part in name_parts)
    )

    if not correct:
        asyncio.create_task(_delete_after(bot, chat_id, update.message.message_id, _WRONG_DELETE_SEC))
        msg = await _safe_send(bot, chat_id, "❌ Wrong! Look at the character again 👀")
        if msg:
            asyncio.create_task(_delete_after(bot, chat_id, msg.message_id, _WRONG_DELETE_SEC))
        return

    # ── Correct guess ─────────────────────────────────────────────────────────
    _claimed[chat_id] = user_id
    _active_char.pop(chat_id, None)

    drop_time  = _active_time.pop(chat_id, time.time())
    time_taken = int(time.time() - drop_time)

    msg_id = _active_msg.pop(chat_id, None)
    if msg_id:
        await _safe_delete(bot, chat_id, msg_id)

    asyncio.create_task(_delete_after(bot, chat_id, update.message.message_id, 1))

    u = update.effective_user
    await user_collection.update_one(
        {"id": user_id},
        {
            "$push": {"characters": char},
            "$inc":  {"total_guesses": 1, "xp": _XP_PER_GUESS},
            "$set":  {"username": u.username, "first_name": u.first_name},
            "$setOnInsert": {"coins": 0, "wins": 0, "favorites": []},
        },
        upsert=True,
    )

    await group_user_totals_collection.update_one(
        {"user_id": user_id, "group_id": chat_id},
        {"$set": {"username": u.username, "first_name": u.first_name}, "$inc": {"count": 1}},
        upsert=True,
    )
    await top_global_groups_collection.update_one(
        {"group_id": chat_id},
        {"$set": {"group_name": update.effective_chat.title}, "$inc": {"count": 1}},
        upsert=True,
    )

    rarity     = char.get("rarity", "⚪ Common")
    is_special = char.get("is_special", False)
    special_tag = "🌟 <b>SPECIAL CHARACTER CLAIMED!</b>\n\n" if is_special else ""

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📖 My Harem",
            switch_inline_query_current_chat=f"collection.{user_id}",
        )
    ]])

    await _safe_send(
        bot, chat_id,
        f'{special_tag}'
        f'👑 <b>𝗡𝗘𝗪 𝗖𝗛𝗔𝗥𝗔𝗖𝗧𝗘𝗥 𝗖𝗔𝗣𝗧𝗨𝗥𝗘𝗗</b> 👑\n\n'
        f'🎯 <a href="tg://user?id={user_id}">{escape(u.first_name)}</a> claimed this character!\n\n'
        f'🌸 {escape(char["name"])}\n'
        f'🎬 {escape(char["anime"])}\n'
        f'💠 {rarity}\n'
        f'⏱️ {time_taken} seconds\n\n'
        f'✨ Harem Updated! +{_XP_PER_GUESS} XP 🔥',
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


# ── /fav ──────────────────────────────────────────────────────────────────────

async def fav(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /fav <character_id>")
        return

    char_id  = context.args[0]
    user_doc = await user_collection.find_one({"id": user_id})
    if not user_doc:
        await update.message.reply_text("You haven't guessed any characters yet.")
        return

    char = next((c for c in user_doc.get("characters", []) if c["id"] == char_id), None)
    if not char:
        await update.message.reply_text("That character isn't in your collection.")
        return

    await user_collection.update_one({"id": user_id}, {"$set": {"favorites": [char_id]}})
    await update.message.reply_text(
        f"⭐ <b>{escape(char['name'])}</b> set as your favourite!",
        parse_mode=ParseMode.HTML,
    )


# ── /setspecial ───────────────────────────────────────────────────────────────

async def setspecial(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only!")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/setspecial &lt;char_id&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    char_id = context.args[0].strip()
    char    = await collection.find_one({"id": char_id})
    if not char:
        await update.message.reply_text(
            f"❌ Character <code>{char_id}</code> not found in DB!",
            parse_mode=ParseMode.HTML,
        )
        return

    existing = await special_collection.find_one({"char_id": char_id})
    if existing:
        await update.message.reply_text(
            f"⚠️ <b>{escape(char['name'])}</b> is already in special list!",
            parse_mode=ParseMode.HTML,
        )
        return

    await special_collection.insert_one({
        "char_id": char_id,
        "name":    char["name"],
        "anime":   char["anime"],
        "rarity":  char.get("rarity", "Unknown"),
    })

    await update.message.reply_text(
        f"🌟 <b>{escape(char['name'])}</b> added to special drop list!\n"
        f"💎 Rarity: {char.get('rarity', 'Unknown')}\n"
        f"🎯 Drop chance: Very Rare (0.5%)",
        parse_mode=ParseMode.HTML,
    )


# ── /removespecial ────────────────────────────────────────────────────────────

async def removespecial(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only!")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/removespecial &lt;char_id&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    char_id = context.args[0].strip()
    result  = await special_collection.delete_one({"char_id": char_id})

    if result.deleted_count:
        await update.message.reply_text(
            f"✅ Character <code>{char_id}</code> removed from special list!",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("❌ Character not found in special list!")


# ── /speciallist ──────────────────────────────────────────────────────────────

async def speciallist(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only!")
        return

    specials = await special_collection.find({}).to_list(length=100)
    if not specials:
        await update.message.reply_text("📭 No special characters set yet!")
        return

    lines = ["🌟 <b>Special Characters List</b>\n"]
    for s in specials:
        lines.append(
            f"🎴 <b>{escape(s['name'])}</b> — {s.get('rarity', '?')}\n"
            f"   🆔 <code>{s['char_id']}</code>"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


# ── Register handlers ─────────────────────────────────────────────────────────

application.add_handler(CommandHandler(
    ["guess", "protecc", "collect", "grab", "hunt"], guess, block=False
))
application.add_handler(CommandHandler("fav",           fav,           block=False))
application.add_handler(CommandHandler("setspecial",    setspecial,    block=False))
application.add_handler(CommandHandler("removespecial", removespecial, block=False))
application.add_handler(CommandHandler("speciallist",   speciallist,   block=False))
application.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
    message_counter,
    block=False,
))
