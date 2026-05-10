import json
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from waifu import application
from waifu import collection, sudo_users


async def import_json(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in sudo_users:
        return await update.message.reply_text("❌ Not authorized.")

    if not update.message.reply_to_message:
        return await update.message.reply_text(
            "Reply to JSON file."
        )

    document = update.message.reply_to_message.document

    if not document.file_name.endswith(".json"):
        return await update.message.reply_text(
            "❌ Send valid JSON file."
        )

    file = await context.bot.get_file(document.file_id)

    path = "characters_import.json"

    await file.download_to_drive(path)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    added = 0

    for char in data:

        await collection.insert_one({
            "img_url": char.get("image"),
            "name": char.get("name"),
            "anime": char.get("anime"),
            "rarity": char.get("rarity")
        })

        added += 1

    await update.message.reply_text(
        f"✅ Imported {added} characters."
    )


application.add_handler(CommandHandler("importjson", import_json))
