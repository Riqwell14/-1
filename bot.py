import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from dotenv import load_dotenv

from db import Database, Profile
from states import RegistrationState, EditState

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "dating_bot.sqlite3")
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

if not TOKEN:
    raise ValueError("BOT_TOKEN is required")

bot = Bot(TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
db = Database(DB_PATH)


def profile_text(profile) -> str:
    return (
        f"<b>{profile['name']}, {profile['age']}</b>\n"
        f"🏙 {profile['city']}\n"
        f"⚧ Пол: {profile['gender']}\n"
        f"🔎 Ищет: {profile['looking_for']}\n\n"
        f"{profile['bio']}"
    )


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👀 Смотреть анкеты", callback_data="browse")],
            [InlineKeyboardButton(text="🧾 Моя анкета", callback_data="profile")],
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit")],
            [InlineKeyboardButton(text="💬 Мэтчи и чат", callback_data="chat")],
        ]
    )


def like_kb(target_user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👎", callback_data=f"dislike:{target_user_id}"),
                InlineKeyboardButton(text="❤️", callback_data=f"like:{target_user_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="menu")],
        ]
    )


def edit_kb() -> InlineKeyboardMarkup:
    fields = [
        ("Имя", "name"),
        ("Возраст", "age"),
        ("Город", "city"),
        ("Пол", "gender"),
        ("Кого ищу", "looking_for"),
        ("Описание", "bio"),
    ]
    rows = [[InlineKeyboardButton(text=title, callback_data=f"edit_field:{key}")] for title, key in fields]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gender_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="male", callback_data=f"{prefix}:male"),
                InlineKeyboardButton(text="female", callback_data=f"{prefix}:female"),
                InlineKeyboardButton(text="other", callback_data=f"{prefix}:other"),
            ],
            [InlineKeyboardButton(text="any", callback_data=f"{prefix}:any")],
        ]
    )


def matches_kb(matches) -> InlineKeyboardMarkup:
    rows = []
    for m in matches:
        rows.append([
            InlineKeyboardButton(
                text=f"💬 {m['name']} ({m['age']}, {m['city']})",
                callback_data=f"chat_with:{m['user_id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext) -> None:
    profile = db.get_profile(message.from_user.id)
    if profile:
        await state.clear()
        await message.answer("С возвращением! Выберите действие:", reply_markup=main_menu())
        return
    await state.set_state(RegistrationState.name)
    await message.answer("Привет! Давай создадим анкету. Как тебя зовут?")


@dp.message(Command("profile"))
async def profile_cmd(message: Message) -> None:
    profile = db.get_profile(message.from_user.id)
    if not profile:
        await message.answer("Сначала зарегистрируйся через /start")
        return
    await message.answer(profile_text(profile), reply_markup=main_menu())


@dp.message(Command("browse"))
async def browse_cmd(message: Message) -> None:
    await send_next_candidate(message.from_user.id, message)


@dp.message(Command("edit"))
async def edit_cmd(message: Message) -> None:
    if not db.get_profile(message.from_user.id):
        await message.answer("Сначала зарегистрируйся через /start")
        return
    await message.answer("Что изменить?", reply_markup=edit_kb())


@dp.message(Command("chat"))
async def chat_cmd(message: Message) -> None:
    matches = db.get_matches(message.from_user.id)
    if not matches:
        await message.answer("Пока нет мэтчей. Ставь лайки в /browse")
        return
    await message.answer("Выбери, с кем начать чат:", reply_markup=matches_kb(matches))


@dp.message(Command("stopchat"))
async def stop_chat_cmd(message: Message) -> None:
    db.clear_active_chat(message.from_user.id)
    await message.answer("Чат остановлен.", reply_markup=main_menu())


@dp.callback_query(F.data == "menu")
async def menu_cb(call: CallbackQuery) -> None:
    await call.message.edit_text("Главное меню:", reply_markup=main_menu())


@dp.callback_query(F.data == "browse")
async def browse_cb(call: CallbackQuery) -> None:
    await send_next_candidate(call.from_user.id, call.message, use_edit=True)


@dp.callback_query(F.data == "profile")
async def profile_cb(call: CallbackQuery) -> None:
    profile = db.get_profile(call.from_user.id)
    if not profile:
        await call.message.edit_text("Сначала зарегистрируйся через /start")
        return
    await call.message.edit_text(profile_text(profile), reply_markup=main_menu())


@dp.callback_query(F.data == "edit")
async def edit_cb(call: CallbackQuery) -> None:
    await call.message.edit_text("Что изменить?", reply_markup=edit_kb())


@dp.callback_query(F.data == "chat")
async def chat_cb(call: CallbackQuery) -> None:
    matches = db.get_matches(call.from_user.id)
    if not matches:
        await call.message.edit_text("Пока нет мэтчей. Ставь лайки в /browse", reply_markup=main_menu())
        return
    await call.message.edit_text("Выбери, с кем начать чат:", reply_markup=matches_kb(matches))


@dp.callback_query(F.data.startswith("chat_with:"))
async def chat_with_cb(call: CallbackQuery) -> None:
    partner_id = int(call.data.split(":", 1)[1])
    if not db.are_matched(call.from_user.id, partner_id):
        await call.answer("Этот пользователь не в мэтчах", show_alert=True)
        return

    db.set_active_chat(call.from_user.id, partner_id)
    partner = db.get_profile(partner_id)
    partner_name = partner["name"] if partner else "пользователь"
    await call.message.edit_text(
        f"Чат активирован с {partner_name}. Теперь просто отправляй сообщения.\n"
        "Чтобы выйти: /stopchat",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data.startswith("edit_field:"))
async def edit_field_cb(call: CallbackQuery, state: FSMContext) -> None:
    field = call.data.split(":", 1)[1]
    await state.set_state(EditState.value)
    await state.update_data(field=field)
    if field in {"gender", "looking_for"}:
        await call.message.edit_text(
            "Выбери значение:",
            reply_markup=gender_kb("edit_value"),
        )
        return
    await call.message.edit_text("Введи новое значение:")


@dp.callback_query(F.data.startswith("edit_value:"))
async def edit_value_cb(call: CallbackQuery, state: FSMContext) -> None:
    value = call.data.split(":", 1)[1]
    data = await state.get_data()
    field = data.get("field")
    if field == "age" and not value.isdigit():
        await call.answer("Возраст должен быть числом", show_alert=True)
        return
    db.update_profile_field(call.from_user.id, field, value)
    await state.clear()
    await call.message.edit_text("Обновлено!", reply_markup=main_menu())


@dp.message(EditState.value)
async def edit_value_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("field")
    value = message.text.strip()

    if field == "age":
        if not value.isdigit() or not (18 <= int(value) <= 99):
            await message.answer("Возраст должен быть числом от 18 до 99")
            return
    db.update_profile_field(message.from_user.id, field, value)
    await state.clear()
    await message.answer("Анкета обновлена", reply_markup=main_menu())


@dp.callback_query(F.data.startswith("like:"))
async def like_cb(call: CallbackQuery) -> None:
    target_id = int(call.data.split(":", 1)[1])
    is_match = db.set_like(call.from_user.id, target_id, 1)

    if is_match:
        me = db.get_profile(call.from_user.id)
        target = db.get_profile(target_id)
        if target:
            await bot.send_message(
                target_id,
                f"🎉 Взаимный лайк с {me['name']}!\n"
                "Открой /chat, чтобы начать общение.",
            )
        if me:
            await call.message.answer(
                f"🎉 Взаимный лайк с {target['name']}! Открой /chat, чтобы написать.",
            )
    await send_next_candidate(call.from_user.id, call.message, use_edit=True)


@dp.callback_query(F.data.startswith("dislike:"))
async def dislike_cb(call: CallbackQuery) -> None:
    target_id = int(call.data.split(":", 1)[1])
    db.set_like(call.from_user.id, target_id, 0)
    await send_next_candidate(call.from_user.id, call.message, use_edit=True)


@dp.message(RegistrationState.name)
async def reg_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(RegistrationState.age)
    await message.answer("Сколько тебе лет? (18-99)")


@dp.message(RegistrationState.age)
async def reg_age(message: Message, state: FSMContext) -> None:
    age = message.text.strip()
    if not age.isdigit() or not (18 <= int(age) <= 99):
        await message.answer("Введи число от 18 до 99")
        return
    await state.update_data(age=int(age))
    await state.set_state(RegistrationState.city)
    await message.answer("Из какого ты города?")


@dp.message(RegistrationState.city)
async def reg_city(message: Message, state: FSMContext) -> None:
    await state.update_data(city=message.text.strip())
    await state.set_state(RegistrationState.gender)
    await message.answer("Укажи свой пол:", reply_markup=gender_kb("reg_gender"))


@dp.callback_query(F.data.startswith("reg_gender:"), RegistrationState.gender)
async def reg_gender(call: CallbackQuery, state: FSMContext) -> None:
    gender = call.data.split(":", 1)[1]
    await state.update_data(gender=gender)
    await state.set_state(RegistrationState.looking_for)
    await call.message.edit_text("Кого ты ищешь?", reply_markup=gender_kb("reg_looking"))


@dp.callback_query(F.data.startswith("reg_looking:"), RegistrationState.looking_for)
async def reg_looking(call: CallbackQuery, state: FSMContext) -> None:
    looking_for = call.data.split(":", 1)[1]
    await state.update_data(looking_for=looking_for)
    await state.set_state(RegistrationState.bio)
    await call.message.edit_text("Коротко расскажи о себе:")


@dp.message(RegistrationState.bio)
async def reg_bio(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    profile = Profile(
        user_id=message.from_user.id,
        username=message.from_user.username,
        name=data["name"],
        age=data["age"],
        city=data["city"],
        gender=data["gender"],
        looking_for=data["looking_for"],
        bio=message.text.strip(),
    )
    db.upsert_profile(profile)
    await state.clear()
    await message.answer("Анкета готова!", reply_markup=main_menu())


@dp.message()
async def relay_message(message: Message) -> None:
    if message.text and message.text.startswith("/"):
        return
    partner_id = db.get_active_chat_partner(message.from_user.id)
    if not partner_id:
        return
    if not db.are_matched(message.from_user.id, partner_id):
        db.clear_active_chat(message.from_user.id)
        await message.answer("Этот чат больше недоступен.", reply_markup=main_menu())
        return

    sender = db.get_profile(message.from_user.id)
    sender_name = sender["name"] if sender else "Аноним"

    if message.text:
        await bot.send_message(partner_id, f"💬 {sender_name}:\n{message.text}")
    elif message.photo:
        await bot.send_photo(partner_id, message.photo[-1].file_id, caption=f"💬 {sender_name}")
    elif message.voice:
        await bot.send_voice(partner_id, message.voice.file_id, caption=f"💬 {sender_name}")


async def send_next_candidate(user_id: int, message: Message, use_edit: bool = False) -> None:
    if not db.get_profile(user_id):
        text = "Сначала зарегистрируйся через /start"
        if use_edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    candidate = db.get_candidate(user_id)
    if not candidate:
        text = "Анкеты закончились. Возвращайся позже 👀"
        if use_edit:
            await message.edit_text(text, reply_markup=main_menu())
        else:
            await message.answer(text, reply_markup=main_menu())
        return

    text = profile_text(candidate)
    if use_edit:
        await message.edit_text(text, reply_markup=like_kb(candidate["user_id"]))
    else:
        await message.answer(text, reply_markup=like_kb(candidate["user_id"]))


@dp.message(Command("admin_stats"))
async def admin_stats(message: Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return
    users = db.conn.execute("SELECT COUNT(*) cnt FROM profiles").fetchone()["cnt"]
    likes = db.conn.execute("SELECT COUNT(*) cnt FROM likes WHERE value = 1").fetchone()["cnt"]
    matches = db.conn.execute("SELECT COUNT(*) cnt FROM matches").fetchone()["cnt"]
    await message.answer(
        "<b>Статистика</b>\n"
        f"Пользователи: {users}\n"
        f"Лайки: {likes}\n"
        f"Мэтчи: {matches}"
    )


async def main() -> None:
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
