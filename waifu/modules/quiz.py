"""
modules/quiz.py

/quiz — Anime character quiz, guess the character from the image.
Correct answer → coins reward!
RESTRICTED to specific group only.
"""
import asyncio
import random
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler

from waifu import application, collection, user_collection

_QUIZ_TIMEOUT  = 30
_QUIZ_REWARD   = 100
_QUIZ_XP       = 20
_ALLOWED_GROUP = -1003865428134  # Only this group can use quiz

# Active quizzes: chat_id → {char, message_id, answered}
_active_quiz: dict[int, dict] = {}


async def quiz(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    # Only allowed in specific group — silent ignore everywhere else
    if chat_id != _ALLOWED_GROUP:
        return

    if chat_id in _active_quiz:
        await update.message.reply_text(
            "⏳ A quiz is already running! Answer it first."
        )
        return

    all_chars = await collection.find({}).to_list(length=5000)
    if len(all_chars) < 4:
        await update.message.reply_text(
            "❌ Not enough characters in DB for a quiz! Need at least 4."
        )
        return

    correct = random.choice(all_chars)
    wrong   = random.sample([c for c in all_chars if c["id"] != correct["id"]], 3)
    options = [correct] + wrong
    random.shuffle(options)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            options[i]["name"],
            callback_data=f"quiz:{chat_id}:{options[i]['id']}:{correct['id']}"
        )] for i in range(4)
    ])

    try:
        msg = await context.bot.send_photo(
            chat_id=chat_id,
            photo=correct["img_url"],
            caption=(
                f"🎯 <b>Who is this character?</b>\n\n"
                f"💰 Reward: <b>{_QUIZ_REWARD} coins + {_QUIZ_XP} XP</b>\n"
                f"⏰ You have <b>{_QUIZ_TIMEOUT} seconds!</b>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )

        _active_quiz[chat_id] = {
            "char":       correct,
            "message_id": msg.message_id,
            "answered":   False,
        }

        asyncio.create_task(_quiz_expire(context.bot, chat_id, correct, msg.message_id))

    except Exception as e:
        await update.message.reply_text(f"❌ Error starting quiz: {e}")


async def _quiz_expire(bot, chat_id: int, correct: dict, message_id: int) -> None:
    await asyncio.sleep(_QUIZ_TIMEOUT)

    quiz_data = _active_quiz.get(chat_id)
    if not quiz_data or quiz_data["answered"]:
        return

    _active_quiz.pop(chat_id, None)

    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=(
                f"⏰ <b>Time's up!</b>\n\n"
                f"The character was: <b>{escape(correct['name'])}</b>\n"
                f"📺 Anime: {escape(correct['anime'])}\n"
                f"💎 Rarity: {correct.get('rarity', 'Unknown')}"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([]),
        )
    except Exception:
        pass


async def quiz_answer(update: Update, context: CallbackContext) -> None:
    q = update.callback_query
    await q.answer()

    data       = q.data.split(":")
    chat_id    = int(data[1])
    chosen_id  = data[2]
    correct_id = data[3]

    # Only allowed group
    if chat_id != _ALLOWED_GROUP:
        return

    quiz_data = _active_quiz.get(chat_id)
    if not quiz_data or quiz_data["answered"]:
        await q.answer("⏰ Quiz already ended!", show_alert=True)
        return

    user    = q.from_user
    correct = quiz_data["char"]
    is_correct = chosen_id == correct_id

    quiz_data["answered"] = True
    _active_quiz.pop(chat_id, None)

    if is_correct:
        await user_collection.update_one(
            {"id": user.id},
            {
                "$inc": {"coins": _QUIZ_REWARD, "xp": _QUIZ_XP},
                "$set": {"username": user.username, "first_name": user.first_name},
                "$setOnInsert": {"characters": [], "favorites": [], "wins": 0},
            },
            upsert=True,
        )
        caption = (
            f"✅ <b>Correct!</b>\n\n"
            f"🎉 <a href='tg://user?id={user.id}'>{escape(user.first_name)}</a> "
            f"got it right!\n\n"
            f"🌸 <b>{escape(correct['name'])}</b>\n"
            f"📺 {escape(correct['anime'])}\n"
            f"💎 {correct.get('rarity', 'Unknown')}\n\n"
            f"💰 +{_QUIZ_REWARD} coins  |  ✨ +{_QUIZ_XP} XP"
        )
    else:
        chosen_char = await collection.find_one({"id": chosen_id})
        chosen_name = chosen_char["name"] if chosen_char else "Unknown"
        caption = (
            f"❌ <b>Wrong!</b>\n\n"
            f"<a href='tg://user?id={user.id}'>{escape(user.first_name)}</a> "
            f"guessed <b>{escape(chosen_name)}</b>\n\n"
            f"✅ Correct answer: <b>{escape(correct['name'])}</b>\n"
            f"📺 {escape(correct['anime'])}\n"
            f"💎 {correct.get('rarity', 'Unknown')}"
        )

    try:
        await q.edit_message_caption(
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([]),
        )
    except Exception:
        pass


application.add_handler(CommandHandler("quiz", quiz, block=False))
application.add_handler(CallbackQueryHandler(
    quiz_answer,
    pattern=r"^quiz:\-?\d+:[^:]+:[^:]+$",
    block=False,
))
  
