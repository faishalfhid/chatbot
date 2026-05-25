import os
import re
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# Import fungsi ask() dari script yang sudah ada
from text_to_sql import ask_return  # akan kita modifikasi

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(level=logging.INFO)


def md_to_html(text: str) -> str:
    """Konversi Markdown sederhana ke HTML untuk Telegram (parse_mode='HTML')."""
    # Escape karakter HTML khusus terlebih dahulu (kecuali yang akan kita konversi)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Bold: **text** → <b>text</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # Italic: *text* atau _text_ → <i>text</i>
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"_(.+?)_", r"<i>\1</i>", text)

    # Inline code: `text` → <code>text</code>
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)

    return text


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    await update.message.reply_text("⏳ Sedang mencari data...")

    try:
        answer = ask_return(question)
        await update.message.reply_text(md_to_html(answer), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Terjadi error: {e}")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()