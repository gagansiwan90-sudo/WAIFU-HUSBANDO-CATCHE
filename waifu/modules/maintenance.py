"""
maintenance.py — Silent Maintenance Mode (OWNER ONLY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• /maintenance on  → Bot completely silent, no replies
• /maintenance off → Bot normal ho jaata hai
• Sirf OWNER_ID use kar sakta hai
• State MongoDB mein save hota hai — restart pe bhi yaad rehta hai
"""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode

from waifu import application, db

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OWNER_ID = 8546535996

# MongoDB
settings_col = db["bot_settings"]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def is_maintenance() -> bool:
    doc = await settings_col.find_one({"_id": "maintenance"})
    return bool(doc and doc.get("enabled", False))


async def set_maintenance(state: bool):
    await settings_col.update_one(
        {"_id": "maintenance"},
        {"$set": {"enabled": state}},
        upsert=True
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAINTENANCE COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message

    if user.id != OWNER_ID:
        return

    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        await message.reply_text(
            "Usage:\n/maintenance on\n/maintenance off",
            parse_mode=ParseMode.HTML
        )
        return

    state = args[0].lower() == "on"
    await set_maintenance(state)

    if state:
        await message.reply_text(
            "🔴 <b>Maintenance Mode ON</b>\n\nBot ab completely silent hai.\nKoi bhi command ya message ka reply nahi dega.",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            "🟢 <b>Maintenance Mode OFF</b>\n\nBot wapas normal ho gaya!\nSab commands ab kaam karenge. ✅",
            parse_mode=ParseMode.HTML
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GLOBAL BLOCK HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def block_during_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Owner ko block mat karo
    if user and user.id == OWNER_ID:
        return

    # Maintenance on hai toh sab block
    if await is_maintenance():
        raise ApplicationHandlerStop

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DIRECT REGISTRATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from telegram.ext import ApplicationHandlerStop

application.add_handler(
    MessageHandler(filters.ALL, block_during_maintenance),
    group=-1
)

application.add_handler(
    CommandHandler("maintenance", maintenance_command)
)
