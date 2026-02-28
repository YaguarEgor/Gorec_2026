from aiogram.fsm.state import StatesGroup, State

class Admin(StatesGroup):
    message = State()

class Access(StatesGroup):
    password = State()

class Private(StatesGroup):
    tg_id = State()
    message = State()
