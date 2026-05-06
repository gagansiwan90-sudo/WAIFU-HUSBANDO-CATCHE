"""
modules/maintenance.py

/maintenance on  — Enable maintenance mode (only owner can use bot)
/maintenance off — Disable maintenance mode
/maintenance     — Check status

When maintenance is ON:
- All commands and messages are silently ignored for non-owners
- Owner can still use everything normally
"""
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackContext, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters
)

from waifu import application, OWNER_ID

# Global maintenance state
_maintenance: bool = False


def is_maintenance() -> bool:
    return _maintenance


async def maintenance(update: Update, context: CallbackContext) -> None:
    global _maintenance

    if update.effective_user.id != OWNER_ID:
        return

    args = context.args

    if not args:
        status = "🔴 ON" if _maintenance else "🟢 OFF"
        await update.message.reply_text(
            f"🔧 <b>Maintenance Mode:</b> {status}\n\n"
            f"Usage:\n"
            f"<code>/maintenance on</code> — Enable\n"
            f"<code>/maintenance off</code> — Disable",
            parse_mode=ParseMode.HTML,
        )
        return

    action = args[0].lower()

    if action == "on":
        _maintenance = True
        await update.message.reply_text(
            "🔴 <b>Maintenance Mode ON</b>\n\n"
            "Bot is now in maintenance.\n"
            "All users will be silently ignored.",
            parse_mode=ParseMode.HTML,
        )

    elif action == "off":
        _maintenance = False
        await update.message.reply_text(
            "🟢 <b>Maintenance Mode OFF</b>\n\n"
            "Bot is back online!\n"
            "All users can use the bot again. 🌸",
            parse_mode=ParseMode.HTML,
        )

    else:
        await update.message.reply_text("Usage: /maintenance on/off")


async def maintenance_guard_msg(update: Update, context: CallbackContext) -> None:
    """Silently ignore all messages when maintenance is ON."""
    if not _maintenance:
        return
    if update.effective_user and update.effective_user.id == OWNER_ID:
        return
    # Silent ignore — no reply


async def maintenance_guard_cb(update: Update, context: CallbackContext) -> None:
    """Silently ignore all callbacks when maintenance is ON."""
    if not _maintenance:
        return
    if update.callback_query.from_user.id == OWNER_ID:
        return
    await update.callback_query.answer()


# Register maintenance command
application.add_handler(CommandHandler("maintenance", maintenance, block=False))

# Guard handlers — group=-1 means they run BEFORE all other handlers
application.add_handler(
    MessageHandler(filters.ALL, maintenance_guard_msg, block=True),
    group=-1,
)
application.add_handler(
    CallbackQueryHandler(maintenance_guard_cb, block=True),
    group=-1,
)
