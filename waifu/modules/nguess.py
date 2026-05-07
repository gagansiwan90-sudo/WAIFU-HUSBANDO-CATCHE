"""
modules/nguess.py — 2 min baad messages delete
"""
import asyncio
import random
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, MessageHandler, filters

from waifu import application, collection, user_collection
from waifu.modules.auto_delete import schedule_delete, NGUESS_DELAY

_COINS_REWARD  = 50
_XP_REWARD     = 25
_ALLOWED_GROUP = -1003865428134
_active_games: dict[int, dict] = {}


async def _send_character(chat_id: int, bot, game: dict) -> None:
    idx   = game["current_index"]
    char  = game["chars"][idx]
    total = game["total_rounds"]

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
        game  = _active_games[chat_id]
        idx   = game["current_index"]
        total = game["total_rounds"]
        await update.message.reply_text(
            f"⏳ <b>Game already running!</b>\nRound <b>{idx + 1}/{total}</b> in progress.",
            parse_mode=ParseMode.HTML,
        )
        return

    all_chars = await collection.find({}).to_list(length=5000)
    if len(all_chars) < 3:
        await update.message.reply_text("❌ Not enough characters in DB!")
        return

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
    # Start msg 2 min baad delete
    schedule_delete(context.bot, chat_id, start_msg.message_id, NGUESS_DELAY)

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
        await update.message.reply_text("❌ Wrong! Look at the character again 👀")
        return

    # ── Correct — character message 2 min baad delete ─────────────────
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
            "$setOnInsert": {"characters": [], "favorites": [], "wins": 0, "total_guesses": 0},
        },
        upsert=True,
    )

    # Character image 2 min baad delete
    if game.get("message_id"):
        schedule_delete(context.bot, chat_id, game["message_id"], NGUESS_DELAY)

    correct_msg = await update.message.reply_text(
        f"✅ <b>Correct!</b> "
        f"<a href='tg://user?id={uid}'>{escape(user.first_name)}</a> got it!\n\n"
        f"🌸 <b>{escape(char['name'])}</b>\n"
        f"📺 {escape(char['anime'])}\n"
        f"💎 {char.get('rarity', 'Unknown')}\n\n"
        f"💰 +{_COINS_REWARD} coins  ✨ +{_XP_REWARD} XP",
        parse_mode=ParseMode.HTML,
    )
    # Correct reply bhi 2 min baad delete
    schedule_delete(context.bot, chat_id, correct_msg.message_id, NGUESS_DELAY)

    game["current_index"] += 1

    if game["current_index"] >= game["total_rounds"]:
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

        end_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🎮 <b>Game Over!</b>\n\n"
                f"🏆 <b>Final Scores:</b>\n{scoreboard}\n\n"
                f"<i>Play again with /nguess!</i>"
            ),
            parse_mode=ParseMode.HTML,
        )
        # Game over message bhi 2 min baad delete
        schedule_delete(context.bot, chat_id, end_msg.message_id, NGUESS_DELAY)
        return

    await asyncio.sleep(2)
    await _send_character(chat_id, context.bot, game)


async def nguess_stop(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if chat_id != _ALLOWED_GROUP:
        return

    if chat_id not in _active_games:
        await update.message.reply_text("❌ No active NGuess game!")
        return

    game  = _active_games.pop(chat_id)
    idx   = game["current_index"]
    total = game["total_rounds"]

    # Character image delete on stop
    if game.get("message_id"):
        schedule_delete(context.bot, chat_id, game["message_id"], NGUESS_DELAY)

    stop_msg = await update.message.reply_text(
        f"🛑 <b>Game stopped!</b>\nCompleted <b>{idx}/{total}</b> rounds.\n\n"
        f"<i>Start again with /nguess</i>",
        parse_mode=ParseMode.HTML,
    )
    schedule_delete(context.bot, chat_id, stop_msg.message_id, NGUESS_DELAY)


application.add_handler(CommandHandler("nguess",      nguess,      block=False))
application.add_handler(CommandHandler("nguess_stop", nguess_stop, block=False))
application.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
    nguess_message, block=False,
), group=1)
                          
