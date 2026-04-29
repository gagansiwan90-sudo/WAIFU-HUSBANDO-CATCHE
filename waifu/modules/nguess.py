"""
modules/nguess.py

/nguess — Start a name guessing game.
5 characters appear one by one.
Guess the name via normal text message to earn coins + XP.
Character does NOT get added to harem.
RESTRICTED to specific group only.
"""
import random
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, MessageHandler, filters

from waifu import application, collection, user_collection

_COINS_REWARD  = 50
_XP_REWARD     = 25
_TOTAL_ROUNDS  = 5
_ALLOWED_GROUP = -1003865428134  # Only this group can use nguess

# Active games: chat_id → {chars, current_index, scores}
_active_games: dict[int, dict] = {}


async def _send_character(chat_id: int, bot, game: dict) -> None:
    idx  = game["current_index"]
    char = game["chars"][idx]

    try:
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=char["img_url"],
            caption=(
                f"🎯 <b>Round {idx + 1}/{_TOTAL_ROUNDS}</b>\n\n"
                f"❓ <b>Who is this character?</b>\n\n"
                f"💰 Reward: <b>{_COINS_REWARD} coins + {_XP_REWARD} XP</b>\n"
                f"<i>Type the character name to guess!</i>"
            ),
            parse_mode=ParseMode.HTML,
        )
        game["message_id"] = msg.message_id
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"❌ Error: {e}")


async def nguess(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    # Only allowed in specific group — silent ignore everywhere else
    if chat_id != _ALLOWED_GROUP:
        return

    if chat_id in _active_games:
        game = _active_games[chat_id]
        idx  = game["current_index"]
        await update.message.reply_text(
            f"⏳ A game is already running!\n"
            f"Round <b>{idx + 1}/{_TOTAL_ROUNDS}</b> in progress.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Get random characters
    all_chars = await collection.find({}).to_list(length=5000)
    if len(all_chars) < _TOTAL_ROUNDS:
        await update.message.reply_text(
            f"❌ Not enough characters in DB! Need at least {_TOTAL_ROUNDS}."
        )
        return

    chars = random.sample(all_chars, _TOTAL_ROUNDS)

    game = {
        "chars":         chars,
        "current_index": 0,
        "message_id":    None,
        "scores":        {},
    }
    _active_games[chat_id] = game

    await update.message.reply_text(
        f"🎮 <b>NGuess Game Started!</b>\n\n"
        f"📋 <b>Rules:</b>\n"
        f"┣ {_TOTAL_ROUNDS} characters will appear\n"
        f"┣ Type the character name to guess\n"
        f"┣ Correct → next character appears\n"
        f"┗ Complete all {_TOTAL_ROUNDS} to finish!\n\n"
        f"💰 <b>{_COINS_REWARD} coins + {_XP_REWARD} XP</b> per correct guess\n\n"
        f"<i>Get ready...</i> 🎯",
        parse_mode=ParseMode.HTML,
    )

    await _send_character(chat_id, context.bot, game)


async def nguess_message(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    # Only respond in allowed group
    if chat_id != _ALLOWED_GROUP:
        return

    game = _active_games.get(chat_id)
    if not game:
        return

    user       = update.effective_user
    user_guess = update.message.text.strip().lower()
    idx        = game["current_index"]
    char       = game["chars"][idx]

    # Name matching
    name_parts = char["name"].lower().split()
    correct = (
        sorted(name_parts) == sorted(user_guess.split())
        or any(part == user_guess for part in name_parts)
    )

    if not correct:
        return  # Silent — let them keep trying

    # ── Correct guess ──────────────────────────────────────────────────────
    uid = user.id
    if uid not in game["scores"]:
        game["scores"][uid] = {"name": user.first_name, "coins": 0, "correct": 0}
    game["scores"][uid]["coins"]   += _COINS_REWARD
    game["scores"][uid]["correct"] += 1

    # Give coins + XP
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

    await update.message.reply_text(
        f"✅ <b>Correct!</b> "
        f"<a href='tg://user?id={uid}'>{escape(user.first_name)}</a> got it!\n\n"
        f"🌸 <b>{escape(char['name'])}</b>\n"
        f"📺 {escape(char['anime'])}\n"
        f"💎 {char.get('rarity', 'Unknown')}\n\n"
        f"💰 +{_COINS_REWARD} coins  ✨ +{_XP_REWARD} XP",
        parse_mode=ParseMode.HTML,
    )

    # Move to next round
    game["current_index"] += 1

    if game["current_index"] >= _TOTAL_ROUNDS:
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

        await update.message.reply_text(
            f"🎮 <b>Game Over!</b>\n\n"
            f"🏆 <b>Final Scores:</b>\n{scoreboard}\n\n"
            f"<i>Play again with /nguess!</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Send next character
    await _send_character(chat_id, context.bot, game)


async def nguess_stop(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    # Only in allowed group
    if chat_id != _ALLOWED_GROUP:
        return

    if chat_id not in _active_games:
        await update.message.reply_text("❌ No active NGuess game!")
        return

    game = _active_games.pop(chat_id)
    idx  = game["current_index"]

    await update.message.reply_text(
        f"🛑 <b>Game stopped!</b>\n"
        f"Completed <b>{idx}/{_TOTAL_ROUNDS}</b> rounds.\n\n"
        f"<i>Start again with /nguess</i>",
        parse_mode=ParseMode.HTML,
    )


application.add_handler(CommandHandler("nguess",      nguess,      block=False))
application.add_handler(CommandHandler("nguess_stop", nguess_stop, block=False))
application.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
    nguess_message,
    block=False,
))
      
