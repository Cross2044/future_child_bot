import os
import asyncio
import logging
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

logging.basicConfig(level=logging.INFO)

# --- Переменные окружения ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("Не заданы TELEGRAM_TOKEN или GEMINI_API_KEY в переменных окружения")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# --- URL для Gemini 2.5 Flash ---
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

users = {}

# --- Клавиатуры ---
def kb_children_count():
    kb = InlineKeyboardMarkup(row_width=3)
    for i in range(1, 4):
        kb.insert(InlineKeyboardButton(text=str(i), callback_data=f"count:{i}"))
    return kb

def kb_girls_count(max_children: int):
    kb = InlineKeyboardMarkup(row_width=3)
    for i in range(0, max_children + 1):
        kb.insert(InlineKeyboardButton(text=str(i), callback_data=f"girls:{i}"))
    return kb

def kb_restart():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(text="Оставить текущие фото", callback_data="restart:keep"),
        InlineKeyboardButton(text="Загрузить новые фото", callback_data="restart:new"),
    )
    return kb

# --- Обработчики ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    await message.answer("Привет! Я генерирую фото будущих детей по фото родителей.\nСкинь фото девушки (мамы).")
    users[uid] = {"step": "await_mother"}

@dp.message_handler(content_types=['photo', 'document'])
async def handle_photo(message: types.Message):
    uid = message.from_user.id
    if uid not in users:
        await message.answer("Начни с /start")
        return

    step = users[uid].get("step")

    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id
    else:
        await message.answer("Пожалуйста, отправь фото в формате JPG/PNG.")
        return

    file = await bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

    if step == "await_mother":
        users[uid]["mother"] = file_url
        users[uid]["step"] = "await_father"
        await message.answer("Теперь скинь фото парня (отца).")
    elif step == "await_father":
        users[uid]["father"] = file_url
        users[uid]["step"] = "choose_children"
        await message.answer("Сколько детей сгенерировать?", reply_markup=kb_children_count())

@dp.callback_query_handler(lambda c: c.data.startswith("count:"))
async def choose_children(callback: types.CallbackQuery):
    uid = callback.from_user.id
    count = int(callback.data.split(":")[1])
    users[uid]["children_count"] = count
    users[uid]["step"] = "choose_girls"
    await callback.message.answer(f"Выбрано детей: {count}. Сколько девочек?", reply_markup=kb_girls_count(count))

@dp.callback_query_handler(lambda c: c.data.startswith("girls:"))
async def choose_girls(callback: types.CallbackQuery):
    uid = callback.from_user.id
    girls = int(callback.data.split(":")[1])
    total = users[uid]["children_count"]
    users[uid]["girls_count"] = girls
    users[uid]["boys_count"] = total - girls

    users[uid]["ages"] = []
    users[uid]["current_child"] = 1
    users[uid]["step"] = "await_age"
    await callback.message.answer(f"Сколько лет ребёнку №1? (1–25)")

@dp.message_handler(lambda m: m.from_user.id in users and users[m.from_user.id].get("step") == "await_age")
async def handle_age(message: types.Message):
    uid = message.from_user.id
    try:
        age = int(message.text.strip())
    except ValueError:
        await message.answer("Введи число от 1 до 25.")
        return

    if not (1 <= age <= 25):
        await message.answer("Возраст должен быть от 1 до 25.")
        return

    users[uid]["ages"].append(age)
    total = users[uid]["children_count"]
    current = users[uid]["current_child"]

    if current < total:
        users[uid]["current_child"] += 1
        await message.answer(f"Сколько лет ребёнку №{users[uid]['current_child']}? (1–25)")
    else:
        await generate_and_send(uid, message)

async def generate_and_send(uid: int, msg: types.Message):
    state = users[uid]
    total = state["children_count"]
    girls = state["girls_count"]
    boys = state["boys_count"]
    ages = ", ".join(str(a) for a in state["ages"])

    prompt = (
        f"Сгенерируй фото будущих детей пары. "
        f"Количество: {total}, девочек: {girls}, мальчиков: {boys}. "
        f"Возраст(а): {ages}. Используй фото родителей."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "image/png"
        }
    }

    await msg.answer("Генерация изображения...")

    try:
        resp = requests.post(GEMINI_URL, headers={"Content-Type": "application/json"}, json=payload, timeout=120)

        if resp.status_code != 200:
            logging.error(f"Gemini API error {resp.status_code}: {resp.text}")
            await msg.answer("Ошибка при обращении к API.")
            return

        img_bytes = resp.content
        await msg.answer_photo(types.InputFile(path_or_bytesio=img_bytes, filename="children.png"))
        users[uid]["step"] = "restart"
        await msg.answer("Хочешь сгенерировать заново?", reply_markup=kb_restart())
    except Exception as e:
        logging.exception(e)
        await msg.answer("Ошибка при генерации изображения.")

@dp.callback_query_handler(lambda c: c.data.startswith("restart:"))
async def handle_restart(callback: types.CallbackQuery):
    uid = callback.from_user.id
    action = callback.data.split(":")[1]
    if action == "keep":
        users[uid]["step"] = "choose_children"
        await callback.message.answer("Сколько детей сгенерировать?", reply_markup=kb_children_count())
    else:
        users[uid] = {"step": "await_mother"}
        await callback.message.answer("Скинь фото девушки (мамы).")

@dp.message_handler(content_types=types.ContentType.TEXT)
async def block_text(message: types.Message):
    uid = message.from_user.id
    if uid in users and users[uid].get("step") == "await_age":
        return  # обработается в handle_age
    await message.answer("Пожалуйста, используй кнопки или отправь фото.")

# --- Healthcheck HTTP server для Render ---
async def handle_health(request):
    return web.Response(text="OK")

async def start_web_app():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()

# --- Запуск бота и healthcheck вместе ---
async def main():
    await asyncio.gather(
        start_web_app(),
        dp.start_polling()
    )

if __name__ == "__main__":
    asyncio.run(main())
