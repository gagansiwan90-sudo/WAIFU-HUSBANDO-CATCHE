from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from waifu import application
from waifu import collection, sudo_users


async def export_chars(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in sudo_users:
        return await update.message.reply_text("❌ Not authorized.")

    text = ""

    async for char in collection.find():

        char_id = str(char.get("_id"))
        name = char.get("name")
        anime = char.get("anime")
        rarity = char.get("rarity")
        image = char.get("img_url")

        text += (
            f"/upload {image} {name} {anime} {rarity}\n"
        )

    if not text:
        return await update.message.reply_text("No characters found.")

    # telegram message limit safe split
    for i in range(0, len(text), 4000):
        await update.message.reply_text(
            f"<code>{text[i:i+4000]}</code>",
            parse_mode="HTML"
        )


application.add_handler(CommandHandler("exportchars", export_chars))
