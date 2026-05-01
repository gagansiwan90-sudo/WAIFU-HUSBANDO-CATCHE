"""
modules/nguess.py

/nguess — Start a name guessing game.
- Random rounds (bot decides 3-8)
- Auto stop when bot wants
- Message delete on wrong/correct
- Coins + XP rewards
RESTRICTED to specific group only.
"""
import asyncio
import random
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, MessageHandler, filters

from waifu import application, collection, user_collection

_COINS_REWARD  = 50
_XP_REWARD     = 25
_ALLOWED_GROUP = -1003865428134
_DELETE_DELAY  = 3   # seconds to delete wrong messages

# Active games: chat_id → game data
_active_games: dict[int, dict] = {}


async def _safe_delete(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _delete_after(bot, chat_id: int, message_id: int, delay: int) -> None:
    await asyncio.sleep(delay)
    await _safe_delete(bot, chat_id, message_id)


async def _send_character(chat_id: int, bot, game: dict) -> None:
    idx   = game["current_index"]
    char  = game["chars"][idx]
    total = game["total_rounds"]

    # Delete previous character message
    prev_msg = game.get("message_id")
    if prev_msg:
        await _safe_delete(bot, chat_id, prev_msg)

    try:
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=char["img_url"],
            caption=(
                f"🎯 <b>Round {idx + 1}/{total}</b>\n\n"
                f"❓ <b>Who is this character?</b>\n\n"
                f"💰 <b>{_COINS_REWARD} coins + {_XP_REWARD} XP</b>\n\n"
                f"<i>Type the character name to guess!</i>"
            ),
            parse_mode=ParseMode.HTML,
        )
        game["message_id"] = msg.message_id
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"❌ Error: {e}")


async def nguess(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    if chat_id != _ALLOWED_GROUP:
        return

    if chat_id in _active_games:
        game = _active_games[chat_id]
        idx  = game["current_index"]
        total = game["total_rounds"]
        await update.message.reply_text(
            f"⏳ <b>Game already running!</b>\n"
            f"Round <b>{idx + 1}/{total}</b> in progress.",
            parse_mode=ParseMode.HTML,
        )
        return

    all_chars = await collection.find({}).to_list(length=5000)
    if len(all_chars) < 3:
        await update.message.reply_text("❌ Not enough characters in DB!")
        return

    # Bot decides random rounds between 3-8
    total_rounds = random.randint(3, 8)
    chars        = random.sample(all_chars, total_rounds)

    game = {
        "chars":         chars,
        "current_index": 0,
        "total_rounds":  total_rounds,
        "message_id":    None,
        "scores":        {},
    }
    _active_games[chat_id] = game

    start_msg = await update.message.reply_text(
        f"🎮 <b>NGuess Game Started!</b>\n\n"
        f"📋 <b>Rules:</b>\n"
        f"┣ Type character name to guess\n"
        f"┣ Correct → next character\n"
        f"┗ Bot decides when to stop!\n\n"
        f"💰 <b>{_COINS_REWARD} coins + {_XP_REWARD} XP</b> per correct\n\n"
        f"<i>Get ready...</i> 🎯",
        parse_mode=ParseMode.HTML,
    )

    # Delete start message after 5 seconds
    asyncio.create_task(_delete_after(context.bot, chat_id, start_msg.message_id, 5))
    # Delete /nguess command message
    asyncio.create_task(_delete_after(context.bot, chat_id, update.message.message_id, 2))

    await _send_character(chat_id, context.bot, game)


async def nguess_message(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    if chat_id != _ALLOWED_GROUP:
        return

    game = _active_games.get(chat_id)
    if not game:
        return

    user       = update.effective_user
    user_guess = update.message.text.strip().lower()
    idx        = game["current_index"]
    char       = game["chars"][idx]

    name_parts = char["name"].lower().split()
    correct = (
        sorted(name_parts) == sorted(user_guess.split())
        or any(part == user_guess for part in name_parts)
    )

    if not correct:
        # Delete wrong guess + user message
        wrong_msg = await update.message.reply_text(
            f"❌ Wrong! Look at the character again 👀"
        )
        asyncio.create_task(_delete_after(context.bot, chat_id, wrong_msg.message_id, _DELETE_DELAY))
        asyncio.create_task(_delete_after(context.bot, chat_id, update.message.message_id, _DELETE_DELAY))
        return

    # ── Correct guess ──────────────────────────────────────────────────────
    uid = user.id
    if uid not in game["scores"]:
        game["scores"][uid] = {"name": user.first_name, "coins": 0, "correct": 0}
    game["scores"][uid]["coins"]   += _COINS_REWARD
    game["scores"][uid]["correct"] += 1

    await user_collection.update_one(
        {"id": uid},
        {
            "$inc": {"coins": _COINS_REWARD, "xp": _XP_REWARD},
            "$set": {"username": user.username, "first_name": user.first_name},
            "$setOnInsert": {
                "characters": [], "favorites": [],
                "wins": 0, "total_guesses": 0,
            },
        },
        upsert=True,
    )

    # Delete user's correct guess message
    asyncio.create_task(_delete_after(context.bot, chat_id, update.message.message_id, 1))

    correct_msg = await update.message.reply_text(
        f"✅ <b>Correct!</b> "
        f"<a href='tg://user?id={uid}'>{escape(user.first_name)}</a> got it!\n\n"
        f"🌸 <b>{escape(char['name'])}</b>\n"
        f"📺 {escape(char['anime'])}\n"
        f"💎 {char.get('rarity', 'Unknown')}\n\n"
        f"💰 +{_COINS_REWARD} coins  ✨ +{_XP_REWARD} XP",
        parse_mode=ParseMode.HTML,
    )

    # Delete correct reply after 5 seconds
    asyncio.create_task(_delete_after(context.bot, chat_id, correct_msg.message_id, 5))

    game["current_index"] += 1

    if game["current_index"] >= game["total_rounds"]:
        # Game over
        _active_games.pop(chat_id, None)

        scores = game["scores"]
        if scores:
            sorted_scores = sorted(scores.items(), key=lambda x: x[1]["correct"], reverse=True)
            medals = ["🥇", "🥈", "🥉"]
            lines  = []
            for i, (uid2, data) in enumerate(sorted_scores):
                medal = medals[i] if i < 3 else f"{i+1}."
                lines.append(
                    f"{medal} <a href='tg://user?id={uid2}'>{escape(data['name'])}</a> "
                    f"— {data['correct']} correct  |  💰 {data['coins']:,} coins"
                )
            scoreboard = "\n".join(lines)
        else:
            scoreboard = "No one scored!"

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🎮 <b>Game Over!</b>\n\n"
                f"🏆 <b>Final Scores:</b>\n{scoreboard}\n\n"
                f"<i>Play again with /nguess!</i>"
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    # Small delay before next character
    await asyncio.sleep(2)
    await _send_character(chat_id, context.bot, game)


async def nguess_stop(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    if chat_id != _ALLOWED_GROUP:
        return

    if chat_id not in _active_games:
        msg = await update.message.reply_text("❌ No active NGuess game!")
        asyncio.create_task(_delete_after(context.bot, chat_id, msg.message_id, 3))
        asyncio.create_task(_delete_after(context.bot, chat_id, update.message.message_id, 3))
        return

    game = _active_games.pop(chat_id)
    idx  = game["current_index"]
    total = game["total_rounds"]

    # Delete current character message
    if game.get("message_id"):
        await _safe_delete(context.bot, chat_id, game["message_id"])

    asyncio.create_task(_delete_after(context.bot, chat_id, update.message.message_id, 2))

    await update.message.reply_text(
        f"🛑 <b>Game stopped!</b>\n"
        f"Completed <b>{idx}/{total}</b> rounds.\n\n"
        f"<i>Start again with /nguess</i>",
        parse_mode=ParseMode.HTML,
    )


application.add_handler(CommandHandler("nguess",      nguess,      block=False))
application.add_handler(CommandHandler("nguess_stop", nguess_stop, block=False))
application.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
    nguess_message,
    block=False,
), group=1)
    
