import os

from dotenv import load_dotenv
load_dotenv()

import sqlite3
import logging
import asyncio
import time
from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

import indexer
from search import search_files
from config import RESULTS_PER_PAGE, DB_PATH

TOKEN = os.getenv("BOT_TOKEN")
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "fanfics_storage/uploads")

logging.basicConfig(level=logging.INFO)

storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=storage)

user_search_data = {}
user_metadata = {}  # для краудсорсинга: {user_id: {'file_id': id, 'step': 'rating', 'data': {}}}


class AddficState(StatesGroup):
    waiting_for_file = State()


def build_keyboard(results, page, current_page_count):
    keyboard = []
    row = []
    for i in range(1, current_page_count + 1):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"select:{page}:{i}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    if (page + 1) * RESULTS_PER_PAGE < len(results):
        keyboard.append([InlineKeyboardButton(text="➡️ Показать ещё", callback_data=f"next:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def send_page(message: types.Message, key):
    data = user_search_data.get(key)
    if not data:
        await message.answer("Сначала выполни поиск с помощью `/findfic <запрос>` или просто напиши слово в личку.")
        return

    results = data['results']
    if not results:
        await message.answer(
            "❌ Увы, такого фика в нашем архиве нет\n\n"
            "Если у тебя есть этот файл, отправь его мне, и он пополнит архив!\n\n"
            "Имя файла должно быть в виде: \"Название фика Автор\" (без кавычек, лишних символов и дефисов). Например:\n"
            "Пример\n\n"
            "Подходящие форматы: doc, docx, epub, fb2, txt, pdf.",
            parse_mode="Markdown"
        )
        return

    page = data['page']
    total_pages = (len(results) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    start = page * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    page_results = results[start:end]
    current_page_count = len(page_results)

    lines = [f"🔎 Найдено {len(results)} фиков (страница {page+1}/{total_pages}):\n"]
    for i, (_, author, title, fmt, orig_name) in enumerate(page_results, 1):
        display_name = orig_name if orig_name else "Без названия"
        lines.append(f"{i}. {display_name} ({fmt})")

    await message.answer(
        "\n".join(lines),
        reply_markup=build_keyboard(results, page, current_page_count)
    )


@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "📚 Привет, я архивариус библиотеки\n\n"
        "Ты можешь отправить мне имя автора, название фика или слово из названия, "
        "и я принесу тебе нужные тома.\n\n"
        "Если фик не найден — поищи его где-то еще, а потом отправь файл мне, "
        "я добавлю его в наш архив!\n\n"
        "📞 *Контакты:*\n"
        "Если у вас возникли проблемы с архивом или есть вопросы по его работе, пишите — "
        "https://t.me/your_username",
        parse_mode="Markdown"
    )


@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "🔍 *Как искать фанфики:*\n\n"
        "1. Напиши в чат слово из названия или имя автора.\n"
        "2. Бот покажет список найденных фиков с кнопками-номерами.\n"
        "3. Нажми на кнопку с номером, чтобы скачать файл.\n\n"
        "📤 *Как добавить фанфик:*\n\n"
        "1. Отправь боту файл (txt, doc, docx, epub, fb2, pdf).\n"
        "2. Бот автоматически добавит его в архив.\n"
        "3. Имя файла должно быть в формате: \"Название фика Автор\"\n"
        "   Пример: \n\n"
        "❓ *Что делать, если фанфик не нашёлся:*\n\n"
        "Попробуй изменить слово для поиска").\n"
        "Если уверен, что файл есть в архиве, но бот его не нашёл — напиши нам.\n\n"
        "📞 *Контакты техподдержки:*\n\n"
        "Если ты нашёл баг, файл не загружается или что-то работает не так — пиши сюда:\n"
        "https://t.me/your_username"
        "---\n\n"
        "*Бот создан для удобного поиска и хранения фанфиков.*",
        parse_mode="Markdown"
    )


@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM fanfics")
    total = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM fanfics WHERE rating IS NOT NULL AND rating != ''")
    with_rating = cur.fetchone()[0]
    
    cur.execute("SELECT rating, COUNT(*) FROM fanfics WHERE rating IS NOT NULL AND rating != '' GROUP BY rating ORDER BY COUNT(*) DESC")
    rating_stats = cur.fetchall()
    
    cur.execute("SELECT length, COUNT(*) FROM fanfics WHERE length IS NOT NULL AND length != '' GROUP BY length ORDER BY COUNT(*) DESC")
    length_stats = cur.fetchall()
    
    cur.execute("SELECT tags FROM fanfics WHERE tags IS NOT NULL AND tags != ''")
    all_tags = cur.fetchall()
    tag_counter = {}
    for (tags,) in all_tags:
        for tag in tags.split(', '):
            tag = tag.strip()
            if tag:
                tag_counter[tag] = tag_counter.get(tag, 0) + 1
    top_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)[:10]
    
    conn.close()
    
    lines = [
        "📊 *Статистика архива*",
        f"📚 Всего фиков: *{total}*",
        f"⭐️ С указанным рейтингом: *{with_rating}*",
        "",
        "*Рейтинги:*"
    ]
    for rating, count in rating_stats:
        lines.append(f"  {rating}: {count}")
    
    lines.append("")
    lines.append("*Размеры:*")
    size_names = {'драббл': 'Драббл', 'мини': 'Мини', 'миди': 'Миди', 'макси': 'Макси'}
    for length, count in length_stats:
        name = size_names.get(length, length)
        lines.append(f"  {name}: {count}")
    
    lines.append("")
    lines.append("*🏷 Популярные метки:*")
    for tag, count in top_tags:
        lines.append(f"  {tag}: {count}")
    
    await message.answer("\n".join(lines), parse_mode="Markdown")


@dp.message(Command("findfic"))
@dp.message(Command("find"))
async def find_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Укажи, что искать. Например: `/findfic Гарри Поттер`", parse_mode="Markdown")
        return
    query = args[1].strip()
    results = search_files(query)
    if not results:
        await message.answer(
            "❌ Увы, такого фика в нашем архиве нет\n\n"
            "Если у тебя есть этот файл, отправь его мне, и он пополнит архив!\n\n"
            "Имя файла должно быть в виде: \"Название фика Автор\" (без кавычек, лишних символов и дефисов). Например:\n"
          
            "Подходящие форматы: doc, docx, epub, fb2, txt, pdf.",
            parse_mode="Markdown"
        )
        return
    key = (message.chat.id, message.from_user.id)
    user_search_data[key] = {
        'results': results,
        'page': 0,
        'timestamp': time.time()
    }
    await send_page(message, key)


@dp.callback_query(lambda c: c.data.startswith("select:"))
async def handle_select(callback: types.CallbackQuery):
    _, page, num = callback.data.split(":")
    page = int(page)
    num = int(num)

    key = (callback.message.chat.id, callback.from_user.id)
    data = user_search_data.get(key)
    if not data:
        await callback.message.answer("Сначала выполни поиск.")
        return

    idx = page * RESULTS_PER_PAGE + num - 1
    results = data['results']
    if idx >= len(results):
        await callback.message.answer("❌ Неверный номер. Попробуй ещё раз.")
        return

    file_path = results[idx][0]
    orig_name = results[idx][4]
    ext = os.path.splitext(file_path)[1]
    display_name = (orig_name if orig_name else "Без названия") + ext

    if not os.path.exists(file_path):
        await callback.message.answer("❌ Файл не найден в архиве.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к результатам", callback_data=f"back:{page}")]
    ])

    file = FSInputFile(file_path, filename=display_name)
    await callback.message.answer_document(file, reply_markup=kb)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("next:"))
async def handle_next(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[1])
    key = (callback.message.chat.id, callback.from_user.id)
    user_search_data[key]['page'] = page + 1
    await send_page(callback.message, key)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("back:"))
async def handle_back(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[1])
    key = (callback.message.chat.id, callback.from_user.id)
    user_search_data[key]['page'] = page
    await send_page(callback.message, key)
    await callback.answer()


@dp.message(Command("addfic"))
async def addfic_cmd(message: types.Message, state: FSMContext):
    await state.set_state(AddficState.waiting_for_file)
    await message.answer(
        "Отправь файл, который нужно добавить в архив, следующим сообщением.\n"
        "Имя файла должно быть в формате: \"Название фика Автор\" (без кавычек)."
    )


@dp.message(AddficState.waiting_for_file, lambda message: message.document)
async def process_addfic_document(message: types.Message, state: FSMContext):
    await state.clear()
    file = message.document
    if file.file_size > 20 * 1024 * 1024:
        await message.answer("❌ Файл слишком большой (максимум 20 МБ).")
        return

    file_name = file.file_name
    file_path = os.path.join(UPLOADS_DIR, file_name)

    try:
        file_info = await bot.get_file(file.file_id)
        await bot.download_file(file_info.file_path, destination=file_path)
    except Exception as e:
        await message.answer(f"❌ Ошибка при скачивании файла: {str(e)}")
        return

    success = indexer.index_file(file_path, source='user')
    if success:
        await message.answer(
            f"✅ Фик добавлен в архив! Архивариус счастлив\n\n"
            f"📄 {file_name}\n\n"
            f"Теперь фик можно найти по поиску."
        )
    else:
        await message.answer("❌ Ошибка при добавлении файла. Возможно, он уже есть в архиве.")


@dp.message(AddficState.waiting_for_file)
async def addfic_not_file(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Пожалуйста, отправьте файл (документ), а не текст.")


@dp.message(lambda message: message.document and message.chat.type == "private")
async def handle_document_private(message: types.Message):
    file = message.document
    if file.file_size > 20 * 1024 * 1024:
        await message.answer("❌ Файл слишком большой (максимум 20 МБ).")
        return

    file_name = file.file_name
    file_path = os.path.join(UPLOADS_DIR, file_name)

    try:
        file_info = await bot.get_file(file.file_id)
        await bot.download_file(file_info.file_path, destination=file_path)
    except Exception as e:
        await message.answer(f"❌ Ошибка при скачивании файла: {str(e)}")
        return

    success = indexer.index_file(file_path, source='user')
    if success:
        await message.answer(
            f"✅ Фик добавлен в архив! Архивариус счастлив\n\n"
            f"📄 {file_name}\n\n"
            f"Теперь фик можно найти по поиску."
        )
        # --- начало краудсорсинга ---
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id FROM fanfics WHERE file_path = ?", (file_path,))
        row = cur.fetchone()
        conn.close()
        if row:
            file_id = row[0]
            user_metadata[message.from_user.id] = {'file_id': file_id, 'step': 'rating'}
            await message.answer(
                "Теперь вы можете уточнить данные для этого файла.\n"
                "Введите рейтинг (G, PG-13, R, NC-17) или 'пропустить':"
            )
        # --- конец краудсорсинга ---
    else:
        await message.answer("❌ Ошибка при добавлении файла. Возможно, он уже есть в архиве.")


# =========================
# Краудсорсинг: обработка ответов пользователя
# =========================
@dp.message(lambda msg: msg.from_user.id in user_metadata and user_metadata[msg.from_user.id]['step'] == 'rating')
async def process_rating(message: types.Message):
    user_id = message.from_user.id
    data = user_metadata[user_id]
    text = message.text.strip()
    if text.lower() == 'пропустить':
        rating = None
    else:
        rating = text.upper()
        if rating not in ('G', 'PG-13', 'R', 'NC-17'):
            await message.answer("Некорректный рейтинг. Введите G, PG-13, R, NC-17 или 'пропустить':")
            return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE fanfics SET rating = ? WHERE id = ?", (rating, data['file_id']))
    conn.commit()
    conn.close()
    data['step'] = 'length'
    await message.answer("Введите размер (драббл, мини, миди, макси) или 'пропустить':")

@dp.message(lambda msg: msg.from_user.id in user_metadata and user_metadata[msg.from_user.id]['step'] == 'length')
async def process_length(message: types.Message):
    user_id = message.from_user.id
    data = user_metadata[user_id]
    text = message.text.strip().lower()
    if text == 'пропустить':
        length = None
    else:
        if text not in ('драббл', 'мини', 'миди', 'макси'):
            await message.answer("Некорректный размер. Введите драббл, мини, миди, макси или 'пропустить':")
            return
        length = text
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE fanfics SET length = ? WHERE id = ?", (length, data['file_id']))
    conn.commit()
    conn.close()
    data['step'] = 'tags'
    await message.answer("Введите метки через запятую (например: ООС, АУ, Романтика) или 'пропустить':")

@dp.message(lambda msg: msg.from_user.id in user_metadata and user_metadata[msg.from_user.id]['step'] == 'tags')
async def process_tags(message: types.Message):
    user_id = message.from_user.id
    data = user_metadata[user_id]
    text = message.text.strip()
    if text.lower() == 'пропустить':
        tags = None
    else:
        tags = ', '.join([t.strip() for t in text.split(',') if t.strip()])
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE fanfics SET tags = ? WHERE id = ?", (tags, data['file_id']))
    conn.commit()
    conn.close()
    del user_metadata[user_id]
    await message.answer("Спасибо! Данные сохранены. Теперь этот файл будет участвовать в расширенном поиске.")


@dp.message()
async def search(message: types.Message, state: FSMContext):
    if message.chat.type != "private":
        return
    if not message.text:
        return
    current_state = await state.get_state()
    if current_state:
        return
    query = message.text.strip()
    if not query or query.startswith('/'):
        return
    results = search_files(query)
    if not results:
        await message.answer(
            "❌ Увы, такого фика в нашем архиве нет\n\n"
            "Если у тебя есть этот файл, отправь его мне, и он пополнит архив!\n\n"
            "Имя файла должно быть в виде: \"Название фика Автор\" (без кавычек, лишних символов и дефисов). Например:\n"
           
            "Подходящие форматы: doc, docx, epub, fb2, txt, pdf.",
            parse_mode="Markdown"
        )
        return
    key = (message.chat.id, message.from_user.id)
    user_search_data[key] = {
        'results': results,
        'page': 0,
        'timestamp': time.time()
    }
    await send_page(message, key)


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())