import os
import requests
from flask import Flask

from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Flask для Render healthcheck
app = Flask(__name__)

@app.route("/")
def health():
    return "OK", 200

# --- Telegram Bot ---
HF_API_TOKEN = os.getenv("HF_API_TOKEN")
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MODEL_URL = "https://api-inference.huggingface.co/models/leonelhs/FaceFusion"

headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}

# Состояния диалога
WAITING_MOTHER, WAITING_FATHER = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Пришли фото мамы 👩")
    return WAITING_MOTHER

async def get_mother(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = await update.message.photo[-1].get_file()
    context.user_data["mother"] = await photo.download_as_bytearray()
    await update.message.reply_text("Фото мамы получено ✅ Теперь пришли фото папы 👨")
    return WAITING_FATHER

async def get_father(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = await update.message.photo[-1].get_file()
    father = await photo.download_as_bytearray()
    mother = context.user_data.get("mother")

    await update.message.reply_text("Генерирую изображение ребёнка...")

    resp = requests.post(
        MODEL_URL,
        headers=headers,
        files={"image1": mother, "image2": father}
    )

    if resp.status_code == 200:
        await update.message.reply_photo(photo=resp.content, caption="Вот результат 👶")
    else:
        await update.message.reply_text(f"Ошибка: {resp.text}")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена ❌")
    return ConversationHandler.END

def run_bot():
    application = ApplicationBuilder().token(TG_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_MOTHER: [MessageHandler(filters.PHOTO, get_mother)],
            WAITING_FATHER: [MessageHandler(filters.PHOTO, get_father)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    # Запускаем Flask и бота параллельно
    import threading
    threading.Thread(target=run_bot).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
