import sqlite3
from aiogram import Router, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from config import DB_PATH, RESULTS_PER_PAGE

router = Router()

class AdvSearch(StatesGroup):
    rating = State()
    length = State()
    tags = State()

user_tags = {}

async def send_results(message: types.Message, results, page=0):
    if not results:
        await message.answer("❌ По вашему запросу ничего не найдено.")
        return
    total = len(results)
    total_pages = (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    start = page * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    page_results = results[start:end]

    lines = [f"🔎 Найдено {total} фиков (страница {page+1}/{total_pages}):\n"]
    for i, (_, author, title, fmt, orig_name) in enumerate(page_results, 1):
        display_name = orig_name if orig_name else "Без названия"
        lines.append(f"{i}. {display_name} ({fmt})")

    keyboard = []
    row = []
    for i in range(1, len(page_results) + 1):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"adv_sel:{page}:{i}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    if end < total:
        keyboard.append([InlineKeyboardButton(text="➡️ Показать ещё", callback_data=f"adv_next:{page}")])

    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.message(Command("advanced_search"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(AdvSearch.rating)
    kb = [
        [InlineKeyboardButton(text="G", callback_data="adv_r_G"),
         InlineKeyboardButton(text="PG-13", callback_data="adv_r_PG-13"),
         InlineKeyboardButton(text="R", callback_data="adv_r_R"),
         InlineKeyboardButton(text="NC-17", callback_data="adv_r_NC-17")],
        [InlineKeyboardButton(text="➡️ Пропустить", callback_data="adv_r_skip")]
    ]
    await message.answer("Выберите рейтинг:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(lambda c: c.data.startswith("adv_r_"))
async def process_rating(callback: types.CallbackQuery, state: FSMContext):
    val = callback.data.split("_")[1]
    await state.update_data(rating=None if val == "skip" else val)
    await state.set_state(AdvSearch.length)
    kb = [
        [InlineKeyboardButton(text="Драббл", callback_data="adv_l_драббл"),
         InlineKeyboardButton(text="Мини", callback_data="adv_l_мини"),
         InlineKeyboardButton(text="Миди", callback_data="adv_l_миди"),
         InlineKeyboardButton(text="Макси", callback_data="adv_l_макси")],
        [InlineKeyboardButton(text="➡️ Пропустить", callback_data="adv_l_skip")]
    ]
    try:
        await callback.message.edit_text("Выберите размер:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        pass
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("adv_l_"))
async def process_length(callback: types.CallbackQuery, state: FSMContext):
    val = callback.data.split("_")[1]
    await state.update_data(length=None if val == "skip" else val)
    await state.set_state(AdvSearch.tags)
    popular = ["ООС", "АУ", "Романтика", "Юмор", "Ангст", "Флафф", "hurt/comfort", "Счастливый финал"]
    kb = []
    row = []
    for t in popular:
        row.append(InlineKeyboardButton(text=t, callback_data=f"adv_t_{t}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton(text="➡️ Пропустить", callback_data="adv_t_skip")])
    kb.append([InlineKeyboardButton(text="✏️ Своя метка", callback_data="adv_t_custom")])
    try:
        await callback.message.edit_text("Выберите метки (можно несколько, затем Готово):", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        pass
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("adv_t_") and not c.data.startswith("adv_t_custom"))
async def process_tags(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    tag = callback.data.split("_")[1]
    if tag == "skip":
        await final_search(callback, state, [])
        return
    if uid not in user_tags:
        user_tags[uid] = []
    if tag in user_tags[uid]:
        user_tags[uid].remove(tag)
    else:
        user_tags[uid].append(tag)
    popular = ["ООС", "АУ", "Романтика", "Юмор", "Ангст", "Флафф", "hurt/comfort", "Счастливый финал"]
    kb = []
    row = []
    for t in popular:
        text = f"✅ {t}" if t in user_tags[uid] else t
        row.append(InlineKeyboardButton(text=text, callback_data=f"adv_t_{t}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton(text="✅ Готово", callback_data="adv_t_done")])
    kb.append([InlineKeyboardButton(text="➡️ Пропустить всё", callback_data="adv_t_skip")])
    kb.append([InlineKeyboardButton(text="✏️ Своя метка", callback_data="adv_t_custom")])
    try:
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        pass
    await callback.answer()

@router.callback_query(lambda c: c.data == "adv_t_done")
async def tags_done(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    tags = user_tags.get(uid, [])
    await final_search(callback, state, tags)

@router.callback_query(lambda c: c.data == "adv_t_custom")
async def custom_tag(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите метки через запятую:")
    await state.set_state(AdvSearch.tags)
    await callback.answer()

@router.message(AdvSearch.tags)
async def custom_tags_input(message: types.Message, state: FSMContext):
    tags = [t.strip() for t in message.text.split(",") if t.strip()]
    await final_search(message, state, tags)

async def final_search(source, state: FSMContext, tags):
    data = await state.get_data()
    rating = data.get("rating")
    length = data.get("length")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    sql = "SELECT file_path, author, title, format, original_filename FROM fanfics WHERE 1=1"
    params = []
    if rating:
        sql += " AND rating = ?"
        params.append(rating)
    if length:
        sql += " AND length = ?"
        params.append(length)
    for tag in tags:
        sql += " AND tags LIKE ?"
        params.append(f"%{tag}%")
    sql += " LIMIT 30"
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    if hasattr(source, 'message'):
        msg = source.message
        await source.answer()
    else:
        msg = source
    if not rows:
        await msg.answer("❌ Ничего не найдено.")
        await state.clear()
        return
    # временно сохраним результаты в объекте сообщения
    if not hasattr(msg, 'adv_results'):
        msg.adv_results = {}
    msg.adv_results[msg.from_user.id] = rows
    await send_results(msg, rows)
    await state.clear()

@router.callback_query(lambda c: c.data.startswith("adv_sel:"))
async def select_file(callback: types.CallbackQuery):
    _, page, num = callback.data.split(":")
    page = int(page)
    num = int(num)
    uid = callback.from_user.id
    results = getattr(callback.message, 'adv_results', {}).get(uid, [])
    if not results:
        await callback.message.answer("Результаты устарели, запустите поиск заново.")
        await callback.answer()
        return
    idx = page * RESULTS_PER_PAGE + num - 1
    if idx >= len(results):
        await callback.message.answer("❌ Неверный номер.")
        await callback.answer()
        return
    file_path, author, title, fmt, orig_name = results[idx]
    ext = os.path.splitext(file_path)[1]
    display_name = orig_name + ext
    from aiogram.types import FSInputFile
    await callback.message.answer_document(FSInputFile(file_path, filename=display_name))
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("adv_next:"))
async def next_page(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[1]) + 1
    uid = callback.from_user.id
    results = getattr(callback.message, 'adv_results', {}).get(uid, [])
    if not results:
        await callback.message.answer("Результаты устарели.")
        await callback.answer()
        return
    await send_results(callback.message, results, page)
    await callback.answer()