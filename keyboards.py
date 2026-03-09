from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def start_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Регистрация", callback_data="start_registration")
    builder.button(text="Правила", callback_data="show_rules")
    builder.adjust(1)
    return builder.as_markup()


def registration_mode_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Классический режим", callback_data="reg_mode_classic")
    builder.button(text="Командный режим", callback_data="reg_mode_team")
    builder.adjust(1)
    return builder.as_markup()


def registration_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Всё верно", callback_data="registration_confirm")
    builder.button(text="Заполнить заново", callback_data="registration_restart")
    builder.adjust(1)
    return builder.as_markup()


def admin_application_keyboard(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Одобрить", callback_data=f"approve_application:{user_id}")
    builder.button(text="Отклонить", callback_data=f"reject_application:{user_id}")
    builder.adjust(1)
    return builder.as_markup()