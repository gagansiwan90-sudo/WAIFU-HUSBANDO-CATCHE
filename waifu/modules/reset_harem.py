"""
reset_harem.py — Full Harem Reset Module (OWNER ONLY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• /resetallharem  → Sabka harem + characters wipe
• Sirf OWNER_ID wala use kar sakta hai
• Double confirm system — galti se na ho
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

from waifu import application, db

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIG — Apna Telegram user ID daalo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OWNER_ID = 8546535996  # 👈 Apna Telegram ID yahan daalo

# MongoDB collections
users_col   = db["users"]
hclaim_col  = db["hclaim_cooldowns"]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def resetallharem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Sirf owner
    if user.id != OWNER_ID:
        await update.effective_message.reply_text("❌ Yeh command sirf bot owner ke liye hai!")
        return

    # Confirm button
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Haan, Reset Karo!", callback_data="confirm_reset_harem"),
            InlineKeyboardButton("❌ Cancel",           callback_data="cancel_reset_harem"),
        ]
    ])

    await update.effective_message.reply_text(
        "⚠️ <b>WARNING!</b>\n\n"
        "Yeh action <b>sabka harem permanently delete</b> kar dega!\n"
        "• Sab characters gone ✗\n"
        "• Sab daily claims reset ✗\n"
        "• Koi undo nahi hoga ✗\n\n"
        "Pakka karna chahte ho?",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user  = query.from_user

    # Sirf owner callback bhi handle kare
    if user.id != OWNER_ID:
        await query.answer("❌ Tumhare liye nahi hai yeh!", show_alert=True)
        return

    await query.answer()

    if query.data == "cancel_reset_harem":
        await query.edit_message_text("✅ Reset cancel ho gaya. Sab safe hai!")
        return

    if query.data == "confirm_reset_harem":
        await query.edit_message_text("⏳ Reset ho raha hai... thoda wait karo.")

        # ── Actual DB wipe ──────────────────────────────────────────────
        # 1. Har user ka characters array aur count reset
        await users_col.update_many(
            {},
            {
                "$set": {
                    "characters":        [],
                    "total_characters":  0,
                }
            }
        )

        # 2. Daily claim cooldowns bhi clear
        await hclaim_col.delete_many({})

        # ── Done message ────────────────────────────────────────────────
        await query.edit_message_text(
            "✅ <b>Full Reset Complete!</b>\n\n"
            "🗑️ Sabka harem wipe ho gaya\n"
            "🔄 Daily claims bhi reset\n"
            "🌸 Ab sab fresh start se shuru kar sakte hain!",
            parse_mode=ParseMode.HTML,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DIRECT REGISTRATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

application.add_handler(CommandHandler("resetallharem", resetallharem_command))
application.add_handler(CallbackQueryHandler(reset_callback, pattern="^(confirm|cancel)_reset_harem$"))
