"""
modules/quiz.py

/quiz [easy|medium|hard] — Anime character quiz with:
  - Difficulty levels (Easy/Medium/Hard)
  - Visual timer bar
  - Streak system with bonus coins
  - Multiple question types (Who is this? / Which anime? / What rarity?)
  - Leaderboard tracking
RESTRICTED to specific group only.
"""
import asyncio
import random
import time
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler

from waifu import application, collection, user_collection, db

_ALLOWED_GROUP = -1003865428134

quiz_scores_collection = db["quiz_scores"]

# ── Difficulty settings ───────────────────────────────────────────────────────
DIFFICULTY = {
    "easy":   {"timeout": 40, "coins": 80,  "xp": 15, "options": 4, "emoji": "🟢"},
    "medium": {"timeout": 30, "coins": 150, "xp": 25, "options": 4, "emoji": "🟡"},
    "hard":   {"timeout": 20, "coins": 250, "xp": 40, "options": 4, "emoji": "🔴"},
}

# Question types
Q_TYPES = ["who_is", "which_anime", "what_rarity"]

# Timer bar
def _timer_bar(remaining: int, total: int) -> str:
    filled = round((remaining / total) * 10)
    empty  = 10 - filled
    if filled >= 7:
        color = "🟩"
    elif filled >= 4:
        color = "🟨"
    else:
        color = "🟥"
    return color * filled + "⬛" * empty

# Active quizzes: chat_id → quiz data
_active_quiz: dict[int, dict] = {}

# User streaks: user_id → streak count
_streaks: dict[int, int] = {}


def _streak_bonus(streak: int) -> int:
    if streak >= 10: return 200
    if streak >= 7:  return 150
    if streak >= 5:  return 100
    if streak >= 3:  return 50
    return 0


def _streak_emoji(streak: int) -> str:
    if streak >= 10: return "🔥🔥🔥"
    if streak >= 7:  return "🔥🔥"
    if streak >= 5:  return "🔥"
    if streak >= 3:  return "⚡"
    return ""


async def _build_question(all_chars: list, difficulty: str) -> dict:
    """Build a random question of random type."""
    correct = random.choice(all_chars)
    q_type  = random.choice(Q_TYPES)
    cfg     = DIFFICULTY[difficulty]

    if q_type == "who_is":
        # Show image, guess name
        wrong   = random.sample([c for c in all_chars if c["id"] != correct["id"]], cfg["options"] - 1)
        options = [correct] + wrong
        random.shuffle(options)
        return {
            "type":      "who_is",
            "correct":   correct,
            "options":   options,
            "question":  "🎯 <b>Who is this character?</b>",
            "answer_id": correct["id"],
            "choices":   [{"id": o["id"], "label": o["name"]} for o in options],
        }

    elif q_type == "which_anime":
        # Show image, guess anime
        animes  = list({c["anime"] for c in all_chars if c["anime"] != correct["anime"]})
        if len(animes) < cfg["options"] - 1:
            q_type = "who_is"
            wrong   = random.sample([c for c in all_chars if c["id"] != correct["id"]], cfg["options"] - 1)
            options = [correct] + wrong
            random.shuffle(options)
            return {
                "type":      "who_is",
                "correct":   correct,
                "options":   options,
                "question":  "🎯 <b>Who is this character?</b>",
                "answer_id": correct["id"],
                "choices":   [{"id": o["id"], "label": o["name"]} for o in options],
            }
        wrong_animes = random.sample(animes, cfg["options"] - 1)
        choices = [correct["anime"]] + wrong_animes
        random.shuffle(choices)
        return {
            "type":      "which_anime",
            "correct":   correct,
            "question":  f"📺 <b>Which anime is this character from?</b>",
            "answer_id": correct["anime"],
            "choices":   [{"id": a, "label": a} for a in choices],
        }

    else:  # what_rarity
        all_rarities = [
            "⚪ Common", "🟢 Medium", "🟣 Rare",
            "🟡 Legendary", "💮 Special Edition", "🔞 Extreme"
        ]
        correct_rarity = correct.get("rarity", "⚪ Common")
        wrong_rarities = [r for r in all_rarities if r != correct_rarity]
        choices = [correct_rarity] + random.sample(wrong_rarities, min(cfg["options"] - 1, len(wrong_rarities)))
        random.shuffle(choices)
        return {
            "type":      "what_rarity",
            "correct":   correct,
            "question":  f"💎 <b>What is the rarity of this character?</b>",
            "answer_id": correct_rarity,
            "choices":   [{"id": r, "label": r} for r in choices],
        }


async def quiz(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    if chat_id != _ALLOWED_GROUP:
        return

    if chat_id in _active_quiz:
        await update.message.reply_text("⏳ A quiz is already running! Answer it first.")
        return

    # Parse difficulty
    difficulty = "medium"
    if context.args:
        arg = context.args[0].lower()
        if arg in DIFFICULTY:
            difficulty = arg
        else:
            await update.message.reply_text(
                "Usage: /quiz [easy|medium|hard]\n\n"
                "🟢 Easy — 40s | 80 coins\n"
                "🟡 Medium — 30s | 150 coins\n"
                "🔴 Hard — 20s | 250 coins",
            )
            return

    all_chars = await collection.find({}).to_list(length=5000)
    if len(all_chars) < 4:
        await update.message.reply_text("❌ Not enough characters in DB!")
        return

    cfg      = DIFFICULTY[difficulty]
    question = await _build_question(all_chars, difficulty)
    correct  = question["correct"]
    timeout  = cfg["timeout"]

    # Build keyboard
    kb_buttons = []
    for choice in question["choices"]:
        cb_data = f"qz:{chat_id}:{choice['id']}:{question['answer_id']}:{difficulty}"
        kb_buttons.append([InlineKeyboardButton(choice["label"], callback_data=cb_data)])

    kb = InlineKeyboardMarkup(kb_buttons)

    timer_bar = _timer_bar(timeout, timeout)
    caption = (
        f"{cfg['emoji']} <b>{difficulty.upper()} QUIZ</b>\n\n"
        f"{question['question']}\n\n"
        f"⏰ {timer_bar} {timeout}s\n"
        f"💰 <b>{cfg['coins']} coins + {cfg['xp']} XP</b>"
    )

    try:
        msg = await context.bot.send_photo(
            chat_id=chat_id,
            photo=correct["img_url"],
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )

        start_time = time.time()
        _active_quiz[chat_id] = {
            "question":   question,
            "message_id": msg.message_id,
            "answered":   False,
            "difficulty": difficulty,
            "start_time": start_time,
        }

        # Start timer update task
        asyncio.create_task(_quiz_timer(context.bot, chat_id, msg.message_id, caption, kb, timeout, start_time))
        asyncio.create_task(_quiz_expire(context.bot, chat_id, correct, msg.message_id, timeout))

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def _quiz_timer(bot, chat_id: int, message_id: int, base_caption: str,
                      kb: InlineKeyboardMarkup, timeout: int, start_time: float) -> None:
    """Update timer bar every 5 seconds."""
    for _ in range(timeout // 5):
        await asyncio.sleep(5)

        quiz_data = _active_quiz.get(chat_id)
        if not quiz_data or quiz_data["answered"]:
            return

        elapsed   = time.time() - start_time
        remaining = max(0, timeout - int(elapsed))
        timer_bar = _timer_bar(remaining, timeout)

        # Rebuild caption with updated timer
        q        = quiz_data["question"]
        cfg      = DIFFICULTY[quiz_data["difficulty"]]
        emoji    = cfg["emoji"]
        diff     = quiz_data["difficulty"].upper()
        new_caption = (
            f"{emoji} <b>{diff} QUIZ</b>\n\n"
            f"{q['question']}\n\n"
            f"⏰ {timer_bar} {remaining}s\n"
            f"💰 <b>{cfg['coins']} coins + {cfg['xp']} XP</b>"
        )

        try:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=new_caption,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        except Exception:
            return


async def _quiz_expire(bot, chat_id: int, correct: dict, message_id: int, timeout: int) -> None:
    await asyncio.sleep(timeout)

    quiz_data = _active_quiz.get(chat_id)
    if not quiz_data or quiz_data["answered"]:
        return

    _active_quiz.pop(chat_id, None)

    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=(
                f"⏰ <b>Time's up! No one answered!</b>\n\n"
                f"✅ Correct: <b>{escape(correct['name'])}</b>\n"
                f"📺 {escape(correct['anime'])}\n"
                f"💎 {correct.get('rarity', 'Unknown')}"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([]),
        )
    except Exception:
        pass


async def quiz_answer(update: Update, context: CallbackContext) -> None:
    q = update.callback_query
    await q.answer()

    parts      = q.data.split(":")
    chat_id    = int(parts[1])
    chosen_id  = parts[2]
    correct_id = parts[3]
    difficulty = parts[4]

    if chat_id != _ALLOWED_GROUP:
        return

    quiz_data = _active_quiz.get(chat_id)
    if not quiz_data or quiz_data["answered"]:
        await q.answer("⏰ Quiz already ended!", show_alert=True)
        return

    user       = q.from_user
    correct    = quiz_data["question"]["correct"]
    cfg        = DIFFICULTY[difficulty]
    is_correct = chosen_id == correct_id

    quiz_data["answered"] = True
    _active_quiz.pop(chat_id, None)

    if is_correct:
        # Streak
        _streaks[user.id] = _streaks.get(user.id, 0) + 1
        streak      = _streaks[user.id]
        bonus       = _streak_bonus(streak)
        total_coins = cfg["coins"] + bonus
        streak_txt  = f"\n🔥 Streak: <b>{streak}</b> {_streak_emoji(streak)}  +{bonus} bonus!" if bonus else f"\n🔥 Streak: <b>{streak}</b>"

        await user_collection.update_one(
            {"id": user.id},
            {
                "$inc": {"coins": total_coins, "xp": cfg["xp"]},
                "$set": {"username": user.username, "first_name": user.first_name},
                "$setOnInsert": {"characters": [], "favorites": [], "wins": 0},
            },
            upsert=True,
        )

        # Update quiz leaderboard
        await quiz_scores_collection.update_one(
            {"user_id": user.id},
            {
                "$inc":  {"correct": 1, "coins_earned": total_coins},
                "$set":  {"name": user.first_name},
                "$max":  {"best_streak": streak},
            },
            upsert=True,
        )

        caption = (
            f"✅ <b>Correct!</b> {_streak_emoji(streak)}\n\n"
            f"🎉 <a href='tg://user?id={user.id}'>{escape(user.first_name)}</a> got it!\n\n"
            f"🌸 <b>{escape(correct['name'])}</b>\n"
            f"📺 {escape(correct['anime'])}\n"
            f"💎 {correct.get('rarity', 'Unknown')}\n\n"
            f"💰 +{cfg['coins']} coins  ✨ +{cfg['xp']} XP"
            f"{streak_txt}"
        )
    else:
        # Reset streak
        _streaks[user.id] = 0

        # Update quiz leaderboard (wrong)
        await quiz_scores_collection.update_one(
            {"user_id": user.id},
            {
                "$inc": {"wrong": 1},
                "$set": {"name": user.first_name},
            },
            upsert=True,
        )

        caption = (
            f"❌ <b>Wrong!</b>\n\n"
            f"<a href='tg://user?id={user.id}'>{escape(user.first_name)}</a> "
            f"answered incorrectly!\n\n"
            f"✅ Correct: <b>{escape(correct['name'])}</b>\n"
            f"📺 {escape(correct['anime'])}\n"
            f"💎 {correct.get('rarity', 'Unknown')}\n\n"
            f"💔 Streak reset!"
        )

    try:
        await q.edit_message_caption(
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([]),
        )
    except Exception:
        pass


async def quiz_leaderboard(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if chat_id != _ALLOWED_GROUP:
        return

    top = await quiz_scores_collection.find({}).sort("correct", -1).limit(10).to_list(10)
    if not top:
        await update.message.reply_text("📊 No quiz scores yet!")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines  = ["🏆 <b>Quiz Leaderboard</b>\n"]
    for i, doc in enumerate(top):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(
            f"{medal} <b>{escape(doc.get('name', 'Unknown'))}</b> — "
            f"✅ {doc.get('correct', 0)} correct | "
            f"💰 {doc.get('coins_earned', 0):,} coins | "
            f"🔥 Best streak: {doc.get('best_streak', 0)}"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


application.add_handler(CommandHandler("quiz",  quiz,              block=False))
application.add_handler(CommandHandler("qlb",   quiz_leaderboard,  block=False))
application.add_handler(CallbackQueryHandler(
    quiz_answer,
    pattern=r"^qz:\-?\d+:.+:.+:.+$",
    block=False,
))
