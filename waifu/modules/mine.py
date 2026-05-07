"""
modules/mines.py — Minesweeper Game
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• /mines        → Start game (500 coins entry)
• 4x4 grid, 3 mines hidden
• 2 mine hits = Game Over
• Safe tiles reveal karo, jitne zyada safe = zyada coins
• /cashout → Kabhi bhi jeete hue coins le lo

Rewards:
  1-4  safe = 1.2x
  5-8  safe = 1.5x
  9-11 safe = 2x
  12-13 safe = 3x
"""

import random
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler

from waifu import application, user_collection

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENTRY_FEE   = 500
GRID_SIZE   = 4
TOTAL_CELLS = GRID_SIZE * GRID_SIZE  # 16
MINE_COUNT  = 3
MAX_HITS    = 2  # 2 mine hits = game over

# Multiplier based on safe tiles revealed
def _multiplier(safe: int) -> float:
    if safe <= 4:  return 1.2
    if safe <= 8:  return 1.5
    if safe <= 11: return 2.0
    return 3.0

def _reward(safe: int) -> int:
    return int(ENTRY_FEE * _multiplier(safe))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GAME STATE (in-memory per user)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# { user_id: { "mines": set, "revealed": set, "hits": int, "safe": int } }
_games: dict[int, dict] = {}


def _new_game() -> dict:
    mines = set(random.sample(range(TOTAL_CELLS), MINE_COUNT))
    return {
        "mines":    mines,
        "revealed": set(),
        "hits":     0,
        "safe":     0,
        "over":     False,
        "won":      False,
    }


def _build_keyboard(game: dict, reveal_all: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for row in range(GRID_SIZE):
        line = []
        for col in range(GRID_SIZE):
            idx = row * GRID_SIZE + col
            if idx in game["revealed"] or reveal_all:
                if idx in game["mines"]:
                    label = "💣"
                else:
                    label = "✅"
            else:
                label = "⬛"
            line.append(InlineKeyboardButton(
                label,
                callback_data=f"mines:{idx}"
            ))
        rows.append(line)

    # Bottom buttons
    if not game["over"]:
        rows.append([
            InlineKeyboardButton("💰 Cash Out", callback_data="mines:cashout"),
            InlineKeyboardButton("❌ Quit",     callback_data="mines:quit"),
        ])
    return InlineKeyboardMarkup(rows)


def _game_text(user_name: str, game: dict) -> str:
    hits      = game["hits"]
    safe      = game["safe"]
    reward    = _reward(safe)
    mult      = _multiplier(safe)
    remaining = MAX_HITS - hits

    if game["over"] and not game["won"]:
        return (
            f"💣 <b>BOOM! Game Over!</b>\n\n"
            f"👤 {escape(user_name)}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Entry Fee Lost: <b>{ENTRY_FEE} coins</b>\n"
            f"✅ Safe tiles: <b>{safe}</b>\n"
            f"💣 Mine hits: <b>{hits}</b>\n\n"
            f"Better luck next time! 😢"
        )
    if game["won"]:
        return (
            f"🎉 <b>Amazing! You cleared the board!</b>\n\n"
            f"👤 {escape(user_name)}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ Safe tiles: <b>{safe}</b>\n"
            f"💰 Reward: <b>{reward} coins</b> ({mult}x)\n\n"
            f"🏆 Legend! Sab mines bach gaye!"
        )

    return (
        f"💣 <b>Minesweeper!</b>\n\n"
        f"👤 {escape(user_name)}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 {MINE_COUNT} mines  |  💰 Fee: {ENTRY_FEE}\n"
        f"💣 {MAX_HITS} mine hits = Game Over!\n\n"
        f"<b>💎 Current Reward:</b>\n"
        f"• {safe} safe = <b>{reward} coins</b> ({mult}x)\n\n"
        f"❤️ Lives: {'❤️' * remaining}{'🖤' * hits}\n"
        f"✅ Safe so far: <b>{safe}</b>"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def mines_command(update: Update, context: CallbackContext) -> None:
    user    = update.effective_user
    message = update.effective_message

    # Already in game?
    if user.id in _games and not _games[user.id]["over"]:
        await message.reply_text(
            "⚠️ Tera game already chal raha hai!\n"
            "Pehle finish karo ya <code>/cashout</code> karo.",
            parse_mode=ParseMode.HTML
        )
        return

    # Check coins
    u_doc = await user_collection.find_one({"id": user.id})
    if not u_doc:
        await message.reply_text("❌ Pehle bot use karo — /start karo!")
        return

    coins = u_doc.get("coins", 0)
    if coins < ENTRY_FEE:
        await message.reply_text(
            f"❌ Tere paas <b>{ENTRY_FEE} coins</b> nahi hain!\n"
            f"Abhi tere paas: <b>{coins} coins</b>",
            parse_mode=ParseMode.HTML
        )
        return

    # Deduct entry fee
    await user_collection.update_one(
        {"id": user.id},
        {"$inc": {"coins": -ENTRY_FEE}}
    )

    # Start game
    game = _new_game()
    _games[user.id] = game

    kb   = _build_keyboard(game)
    text = _game_text(user.first_name, game)

    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def cashout_command(update: Update, context: CallbackContext) -> None:
    user    = update.effective_user
    message = update.effective_message

    game = _games.get(user.id)
    if not game or game["over"]:
        await message.reply_text("❌ Koi active game nahi hai! /mines se shuru karo.")
        return

    if game["safe"] == 0:
        await message.reply_text("⚠️ Pehle koi tile reveal karo, phir cashout karo!")
        return

    reward = _reward(game["safe"])
    game["over"] = True
    game["won"]  = True

    await user_collection.update_one(
        {"id": user.id},
        {"$inc": {"coins": reward}}
    )

    kb = _build_keyboard(game, reveal_all=True)
    await message.reply_text(
        f"💰 <b>Cashed Out!</b>\n\n"
        f"✅ Safe tiles: <b>{game['safe']}</b>\n"
        f"🎁 Reward: <b>{reward} coins</b> ({_multiplier(game['safe'])}x)\n\n"
        f"Smart move! 😎",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CALLBACK — tile click
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def mines_callback(update: Update, context: CallbackContext) -> None:
    q    = update.callback_query
    user = q.from_user
    await q.answer()

    data = q.data  # "mines:0" .. "mines:15" | "mines:cashout" | "mines:quit"
    action = data.split(":")[1]

    game = _games.get(user.id)
    if not game:
        await q.answer("❌ Game nahi mila! /mines se start karo.", show_alert=True)
        return

    if game["over"]:
        await q.answer("Game already khatam ho gaya!", show_alert=True)
        return

    # ── Cash out ──────────────────────────────────────────────────────
    if action == "cashout":
        if game["safe"] == 0:
            await q.answer("⚠️ Pehle koi tile reveal karo!", show_alert=True)
            return
        reward       = _reward(game["safe"])
        game["over"] = True
        game["won"]  = True
        await user_collection.update_one(
            {"id": user.id}, {"$inc": {"coins": reward}}
        )
        kb   = _build_keyboard(game, reveal_all=True)
        text = (
            f"💰 <b>Cashed Out!</b>\n\n"
            f"✅ Safe tiles: <b>{game['safe']}</b>\n"
            f"🎁 Reward: <b>{reward} coins</b> ({_multiplier(game['safe'])}x)\n\n"
            f"Smart move! 😎"
        )
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return

    # ── Quit ──────────────────────────────────────────────────────────
    if action == "quit":
        game["over"] = True
        kb   = _build_keyboard(game, reveal_all=True)
        try:
            await q.edit_message_text(
                f"🏳️ Game quit kar diya!\n💸 {ENTRY_FEE} coins gaye...",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        except Exception:
            pass
        return

    # ── Tile click ────────────────────────────────────────────────────
    try:
        idx = int(action)
    except ValueError:
        return

    if idx in game["revealed"]:
        await q.answer("Yeh tile already reveal ho chuki hai!", show_alert=True)
        return

    game["revealed"].add(idx)

    if idx in game["mines"]:
        # Mine hit!
        game["hits"] += 1
        await q.answer("💣 BOOM! Mine mili!", show_alert=True)

        if game["hits"] >= MAX_HITS:
            # Game over
            game["over"] = True
            kb   = _build_keyboard(game, reveal_all=True)
            text = _game_text(user.first_name, game)
            try:
                await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return
    else:
        game["safe"] += 1
        await q.answer(f"✅ Safe! +1 tile")

        # All safe tiles revealed?
        total_safe = TOTAL_CELLS - MINE_COUNT
        if game["safe"] >= total_safe:
            game["over"] = True
            game["won"]  = True
            reward = _reward(game["safe"])
            await user_collection.update_one(
                {"id": user.id}, {"$inc": {"coins": reward}}
            )
            kb   = _build_keyboard(game, reveal_all=True)
            text = _game_text(user.first_name, game)
            try:
                await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

    # Update board
    kb   = _build_keyboard(game)
    text = _game_text(user.first_name, game)
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REGISTER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

application.add_handler(CommandHandler("mines", mines_command, block=False))
application.add_handler(CommandHandler("cashout", cashout_command, block=False))
application.add_handler(CallbackQueryHandler(mines_callback, pattern=r"^mines:", block=False))
    
