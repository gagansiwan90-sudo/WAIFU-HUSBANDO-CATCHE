import json
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from waifu import application
from waifu import collection, sudo_users


async def export_chars(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in sudo_users:
        return await update.message.reply_text("Not authorized.")

    data = []

    async for char in collection.find():

        data.append({
            "id": str(char.get("_id")),
            "name": char.get("name"),
            "anime": char.get("anime"),
            "rarity": char.get("rarity"),
            "image": char.get("img_url")
        })

    file_name = "characters_export.json"

    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    await update.message.reply_document(
        document=file_name,
        caption="✅ Characters exported successfully."
    )


application.add_handler(CommandHandler("exportchars", export_chars))
