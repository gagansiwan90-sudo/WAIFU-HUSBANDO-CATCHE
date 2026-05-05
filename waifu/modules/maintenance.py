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
OWNER_ID = 8546535996  # 👈 Apna Telegram ID yahan daalo

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
        return  # Silent — owner nahi hai toh ignore

    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        await message.reply_text(
            "⚙️ Usage:\n<code>/maintenance on</code>\n<code>/maintenance off</code>",
            parse_mode=ParseMode.HTML
        )
        return

    state = args[0].lower() == "on"
    await set_maintenance(state)

    if state:
        await message.reply_text(
            "🔴 <b>Maintenance Mode ON</b>\n\n"
            "Bot ab completely silent hai.\n"
            "Koi bhi command ya message ka reply nahi dega.",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            "🟢 <b>Maintenance Mode OFF</b>\n\n"
            "Bot wapas normal ho gaya!\n"
            "Sab commands ab kaam karenge. ✅",
            parse_mode=ParseMode.HTML
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GLOBAL BLOCK HANDLER
#  Ye sabse pehle run hoga —
#  maintenance on hone pe sab block
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def block_during_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maintenance mode on hai toh kuch mat karo.
    Owner ke messages allow hain (taaki /maintenance off kar sake).
    """
    user = update.effective_user

    # Owner ko block mat karo
    if user and user.id == OWNER_ID:
        return

    # Maintenance check
    if await is_maintenance():
        return  # Complete silence — koi reply nahi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REGISTER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def register(app=None):
    target = app or application

    # Block handler — group=0 matlab sabse pehle run hoga
    target.add_handler(
        MessageHandler(filters.ALL, block_during_maintenance),
        group=0
    )

    # /maintenance command
    target.add_handler(
        CommandHandler("maintenance", maintenance_command),
        group=0
)
      
