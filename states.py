from aiogram.fsm.state import State, StatesGroup

#состояние регистрации
class Registration(StatesGroup):
    mode = State()
    name = State()
    course = State()
    face_photo = State()
    team_number = State()
    team_photo = State()
    confirm = State()

#если админ захочет отклонить заявку на регистрацию
class RejectApplication(StatesGroup):
    user_id = State()
    reason = State()

#доступ для админа
class Access(StatesGroup):
    password = State()

#личные сообщения от админа
class PrivateMessage(StatesGroup):
    tg_id = State()
    message = State()

#убийства
class Killing(StatesGroup):
    qr_text = State()
    photo = State()
    confirm = State()


class Admin(StatesGroup):
    message = State()