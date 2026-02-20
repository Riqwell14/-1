from aiogram.fsm.state import State, StatesGroup


class RegistrationState(StatesGroup):
    name = State()
    age = State()
    city = State()
    gender = State()
    looking_for = State()
    bio = State()


class EditState(StatesGroup):
    field = State()
    value = State()
