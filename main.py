import asyncio
import logging
import sys
from aiogram.types import FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession
from models import User
from qr_generating import generate_custom_qr
import os
from pathlib import Path

from local_storage import (
    download_telegram_file_bytes,
    build_kill_photo_path,
    save_bytes_to_file,
)

from config_reader import config
import texts

from states import (
    Admin,
    Registration,
    Killing,
    Access,
    PrivateMessage,
    RejectApplication
)
from keyboards import (
    admin_application_keyboard,
    start_keyboard,
    registration_mode_keyboard,
    registration_confirm_keyboard,
)

from db import (
    approve_user_application,
    create_db,
    delete_user_with_rewire,
    get_alive_teams,
    get_all_tg_ids,
    get_all_users_full,
    get_last_alive_classic_player,
    get_player_rating,
    get_team_rating,
    get_user_by_id,
    get_user_by_qr_text,
    get_user_by_tg_id,
    get_team_by_name,
    create_team,
    create_user_application,
    is_admin,
    make_admin,
    process_classic_kill,
    process_team_kill,
    reject_user_application,
    revive_user_with_rewire,
    set_user_score,
    update_user_application,
    assign_classic_targets,
    get_user_victim,
    ensure_user_qr_code,
    assign_team_targets,
    get_team_target,
    get_alive_team_players,
    get_team_by_id,
)

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

TOKEN = config.bot_token.get_secret_value()
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
ADMIN = config.admin.get_secret_value()
BASE_DIR = Path(__file__).resolve().parent
KILL_PHOTOS_DIR = BASE_DIR / "kill_photos"
USER_HELP_TEXT = """
Доступные команды:

/start — начать работу с ботом
/help — показать это сообщение
/my_qr — получить свой QR-код
/target — показать текущую цель (classic)
/team_target — показать цель команды (team)
/kill — подтвердить убийство
/cancel — отменить текущее действие
/player_rating — рейтинг игроков
/team_rating — рейтинг команд
"""

ADMIN_HELP_TEXT = """
Доступные команды администратора:

/start — начать работу с ботом
/help — показать это сообщение
/my_qr — получить свой QR-код
/target — показать текущую цель (classic)
/team_target — показать цель команды (team)
/kill — подтвердить убийство
/cancel — отменить текущее действие
/player_rating — рейтинг игроков
/team_rating — рейтинг команд

Админские команды:
/start_classic_round — запустить классический раунд
/start_team_round — запустить командный раунд
/delete_player <user_id или tg_id> — удалить игрока
/revive_player <user_id или tg_id> — оживить игрока
/all_tg_ids — показать все tg_id
/all_players_full — показать всех игроков с флагами и очками
/set_score <user_id> <score> — установить игроку очки
"""


@dp.callback_query(F.data == "show_rules")
async def show_rules_handler(callback: CallbackQuery, sessionmaker):
    async with sessionmaker() as session:
        user = await get_user_by_tg_id(session, str(callback.from_user.id))

        if user is None:
            await callback.message.answer(
                "В игре есть два режима:\n\n"
                "1. Классический — каждый игрок получает личную цель.\n"
                "2. Командный — каждая команда охотится на другую команду.\n\n"
                "После регистрации и одобрения заявки вы получите подробные правила."
            )
            await callback.answer()
            return

        if user.game_mode == "classic":
            await callback.message.answer(
                "Правила классического режима:\n\n"
                "• У каждого игрока есть одна цель.\n"
                "• После успешного убийства вы получаете новую цель.\n"
                "• За каждое убийство начисляется 1 балл.\n"
                "• Убийство подтверждается QR-кодом и фото."
            )
        elif user.game_mode == "team":
            await callback.message.answer(
                "Правила командного режима:\n\n"
                "• У вашей команды есть команда-жертва.\n"
                "• Вы охотитесь на живых участников команды-противника.\n"
                "• За каждое убийство команда получает 1 балл.\n"
                "• Убийство подтверждается QR-кодом и фото."
            )
        else:
            await callback.message.answer(
                "Подробные правила будут доступны после завершения регистрации."
            )

        await callback.answer()


@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext, sessionmaker) -> None:
    await state.clear()

    async with sessionmaker() as session:
        user = await get_user_by_tg_id(session, str(message.from_user.id))

        if user is None:
            await message.answer(
                texts.greeting,
                reply_markup=start_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return

        if user.is_approved:
            mode_text = "классический" if user.game_mode == "classic" else "командный"
            await message.answer(
                f"Вы уже зарегистрированы.\n"
                f"Ваш режим: {mode_text}.\n\n"
                f"Ожидайте дальнейших указаний от организаторов.",
                reply_markup=start_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return

        if user.reject_reason is None:
            await message.answer(
                "Ваша заявка уже отправлена и находится на рассмотрении.",
                reply_markup=start_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return

        await message.answer(
            f"Ваша предыдущая заявка была отклонена.\n"
            f"Причина: {user.reject_reason}\n\n"
            f"Вы можете подать заявку заново.",
            reply_markup=start_keyboard(),
            parse_mode=ParseMode.HTML
        )


@dp.callback_query(F.data == "start_registration")
async def registration_start(callback: CallbackQuery, state: FSMContext, sessionmaker):
    async with sessionmaker() as session:
        user = await get_user_by_tg_id(session, str(callback.from_user.id))

        if user is not None:
            if user.is_approved:
                await callback.message.answer("Ваша заявка уже одобрена.")
                await callback.answer()
                return

            if user.reject_reason is None:
                await callback.message.answer("Ваша заявка уже находится на рассмотрении.")
                await callback.answer()
                return

        await state.clear()
        await callback.message.answer(
            "Выберите режим участия:",
            reply_markup=registration_mode_keyboard()
        )
        await state.set_state(Registration.mode)
        await callback.answer()


@dp.callback_query(F.data == "reg_mode_classic", Registration.mode)
async def registration_mode_classic(callback: CallbackQuery, state: FSMContext):
    await state.update_data(mode="classic")
    await callback.message.answer("Введите ваше ФИО:")
    await state.set_state(Registration.name)
    await callback.answer()


@dp.callback_query(F.data == "reg_mode_team", Registration.mode)
async def registration_mode_team(callback: CallbackQuery, state: FSMContext):
    await state.update_data(mode="team")
    await callback.message.answer("Введите ваше ФИО:")
    await state.set_state(Registration.name)
    await callback.answer()


@dp.message(Registration.name)
async def process_registration_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("ФИО не может быть пустым. Введите его ещё раз:")
        return

    await state.update_data(name=name)
    await message.answer("Введите номер вашего курса:")
    await state.set_state(Registration.course)


@dp.message(Registration.course)
async def process_registration_course(message: Message, state: FSMContext):
    course_text = message.text.strip()

    if not course_text.isdigit():
        await message.answer("Номер курса должен быть числом. Попробуйте ещё раз:")
        return

    course = int(course_text)

    if course <= 0 or course > 10:
        await message.answer("Введите корректный номер курса.")
        return

    await state.update_data(course=course)
    await message.answer(
        "Отправьте фотографию, на которой хорошо видно ваше лицо.\n"
        "‼️ За прикрепление не своей фотографии предусмотрена дисквалификация."
    )
    await state.set_state(Registration.face_photo)


@dp.message(Registration.face_photo)
async def process_registration_face_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("Пожалуйста, отправьте именно фотографию.")
        return

    face_photo = message.photo[-1].file_id
    await state.update_data(face_photo=face_photo)

    data = await state.get_data()

    if data["mode"] == "team":
        await message.answer("Введите название вашей команды:")
        await state.set_state(Registration.team_name)
    else:
        text = (
            f"Проверьте ваши данные:\n\n"
            f"Режим: Классический\n"
            f"ФИО: {data['name']}\n"
            f"Курс: {data['course']}"
        )
        await message.answer_photo(
            photo=face_photo,
            caption=text,
            reply_markup=registration_confirm_keyboard()
        )
        await state.set_state(Registration.confirm)


@dp.message(Registration.team_name)
async def process_registration_team_name(message: Message, state: FSMContext):
    team_name = message.text.strip()

    if len(team_name) < 2:
        await message.answer("Название команды слишком короткое. Попробуйте ещё раз.")
        return

    await state.update_data(team_name=team_name)
    await message.answer("Отправьте общую фотографию команды:")
    await state.set_state(Registration.team_photo)


@dp.message(Registration.team_photo)
async def process_registration_team_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("Пожалуйста, отправьте именно фотографию команды.")
        return

    team_photo = message.photo[-1].file_id
    await state.update_data(team_photo=team_photo)

    data = await state.get_data()

    text = (
        f"Проверьте ваши данные:\n\n"
        f"Режим: Командный\n"
        f"ФИО: {data['name']}\n"
        f"Курс: {data['course']}\n"
        f"Команда: {data['team_name']}"
    )

    await message.answer_photo(
        photo=data["face_photo"],
        caption=text,
        reply_markup=registration_confirm_keyboard()
    )
    await state.set_state(Registration.confirm)


@dp.callback_query(F.data == "registration_confirm", Registration.confirm)
async def finish_registration(callback: CallbackQuery, state: FSMContext, sessionmaker):
    data = await state.get_data()
    tg_id = str(callback.from_user.id)

    async with sessionmaker() as session:
        team_id = None

        if data["mode"] == "team":
            team = await get_team_by_name(session, data["team_name"])
            if team is None:
                team = await create_team(
                    session,
                    name=data["team_name"],
                    team_photo=data["team_photo"]
                )
            team_id = team.id

        existing_user = await get_user_by_tg_id(session, tg_id)

        if existing_user is None:
            user = await create_user_application(
                session,
                tg_id=tg_id,
                name=data["name"],
                course=data["course"],
                face_photo=data["face_photo"],
                game_mode=data["mode"],
                team_id=team_id,
            )
        else:
            user = await update_user_application(
                session,
                user=existing_user,
                name=data["name"],
                course=data["course"],
                face_photo=data["face_photo"],
                game_mode=data["mode"],
                team_id=team_id,
            )

        await callback.message.answer(
            "Ваша заявка успешно отправлена на рассмотрение."
        )

        admin_text = (
            f"Новая заявка!\n\n"
            f"ID в БД: {user.id}\n"
            f"Telegram ID: {user.tg_id}\n"
            f"ФИО: {user.name}\n"
            f"Курс: {user.course}\n"
            f"Режим: {'Командный' if user.game_mode == 'team' else 'Классический'}"
        )

        if data["mode"] == "team":
            admin_text += f"\nКоманда: {data['team_name']}"

        await bot.send_photo(
            chat_id=int(ADMIN),
            photo=data["face_photo"],
            caption=admin_text,
            reply_markup=admin_application_keyboard(user.id)
        )

        if data["mode"] == "team":
            await bot.send_photo(
                chat_id=int(ADMIN),
                photo=data["team_photo"],
                caption=f"Фото команды: {data['team_name']}"
            )

    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "registration_restart", Registration.confirm)
async def restart_registration(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "Начнём заново. Выберите режим участия:",
        reply_markup=registration_mode_keyboard()
    )
    await state.set_state(Registration.mode)
    await callback.answer()


@dp.callback_query(F.data.startswith("approve_application:"))
async def approve_application_handler(callback: CallbackQuery, sessionmaker):
    if str(callback.from_user.id) != str(ADMIN):
        await callback.answer("У вас нет прав для этого действия.", show_alert=True)
        return

    user_id_str = callback.data.split(":")[1]

    if not user_id_str.isdigit():
        await callback.answer("Некорректный ID заявки.", show_alert=True)
        return

    user_id = int(user_id_str)

    async with sessionmaker() as session:
        user = await approve_user_application(session, user_id)
        if user is None:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return

        await callback.message.edit_caption(
            caption=(
                f"{callback.message.caption}\n\n"
                f"✅ Заявка одобрена"
            ),
            reply_markup=None
        )

        try:
            await bot.send_message(
                chat_id=int(user.tg_id),
                text=(
                    "Ваша заявка одобрена ✅\n\n"
                    "Теперь вы участвуете в игре."
                )
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление пользователю {user.tg_id}: {e}")

        await callback.answer("Заявка одобрена.")


@dp.callback_query(F.data.startswith("reject_application:"))
async def reject_application_start(callback: CallbackQuery, state: FSMContext, sessionmaker):
    if str(callback.from_user.id) != str(ADMIN):
        await callback.answer("У вас нет прав для этого действия.", show_alert=True)
        return

    user_id_str = callback.data.split(":")[1]

    if not user_id_str.isdigit():
        await callback.answer("Некорректный ID заявки.", show_alert=True)
        return

    user_id = int(user_id_str)

    async with sessionmaker() as session:
        user = await get_user_by_id(session, user_id)

        if user is None:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return

    await state.set_state(RejectApplication.reason)
    await state.update_data(user_id=user_id)

    await callback.message.answer(
        f"Введите причину отказа для заявки пользователя {user.name}:"
    )
    await callback.answer()


@dp.message(RejectApplication.reason)
async def reject_application_finish(message: Message, state: FSMContext, sessionmaker):
    if str(message.from_user.id) != str(ADMIN):
        await message.answer("У вас нет прав для этого действия.")
        await state.clear()
        return

    data = await state.get_data()
    user_id = data.get("user_id")

    if user_id is None:
        await message.answer("Не удалось определить заявку.")
        await state.clear()
        return

    reason = message.text.strip()

    async with sessionmaker() as session:
        user = await reject_user_application(session, user_id, reason)

        if user is None:
            await message.answer("Пользователь не найден.")
            await state.clear()
            return

        await message.answer(
            f"Заявка пользователя {user.name} отклонена."
        )

        try:
            await bot.send_message(
                chat_id=int(user.tg_id),
                text=(
                    "Ваша заявка была отклонена ❌\n"
                    f"Причина: {reason}\n\n"
                    "Вы можете подать заявку заново через /start."
                )
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление пользователю {user.tg_id}: {e}")

    await state.clear()


@dp.message(Command("start_classic_round"))
async def cmd_start_classic_round(message: Message, sessionmaker):
    async with sessionmaker() as session:
        admin = await get_user_by_tg_id(session, str(message.from_user.id))

        if admin is None or not admin.is_admin:
            await message.answer("Эта команда доступна только администратору.")
            return

        try:
            players = await assign_classic_targets(session)
        except ValueError as e:
            await message.answer(str(e))
            return
        except Exception as e:
            await message.answer(f"Ошибка при запуске раунда: {e}")
            return

        success_count = 0
        failed_count = 0
        n = len(players)

        for i, player in enumerate(players):
            victim = players[(i + 1) % n]

            text = (
                "Классический раунд запущен!\n\n"
                f"Ваша цель: {victim.name}\n"
                f"Курс: {victim.course}\n\n"
                "Используйте /kill после успешного устранения цели."
            )

            try:
                if victim.face_photo:
                    await bot.send_photo(
                        chat_id=int(player.tg_id),
                        photo=victim.face_photo,
                        caption=text,
                    )
                else:
                    await bot.send_message(
                        chat_id=int(player.tg_id),
                        text=text,
                    )
                success_count += 1
            except Exception as e:
                failed_count += 1
                logging.exception(
                    "Не удалось отправить цель игроку %s: %s",
                    player.tg_id,
                    e,
                )

        await message.answer(
            "Классический раунд успешно запущен.\n"
            f"Игроков: {len(players)}\n"
            f"Успешно отправлено: {success_count}\n"
            f"Не удалось отправить: {failed_count}"
        )


@dp.message(Command("target"))
async def cmd_target(message: Message, sessionmaker):
    async with sessionmaker() as session:
        user = await get_user_by_tg_id(session, str(message.from_user.id))

        if user is None:
            await message.answer("Вы не зарегистрированы в системе.")
            return

        if not user.is_approved:
            await message.answer("Ваша заявка ещё не одобрена.")
            return

        if user.game_mode != "classic":
            await message.answer("Эта команда доступна только в классическом режиме.")
            return

        if not user.is_alive:
            await message.answer("Вы уже выбыли из игры.")
            return

        if user.victim_id is None:
            await message.answer("Вам пока не назначена цель.")
            return

        victim = await get_user_victim(session, user)

        if victim is None:
            await message.answer("Не удалось найти вашу цель.")
            return

        text = (
            f"Ваша текущая цель: {victim.name}\n"
            f"Курс: {victim.course}"
        )

        if victim.face_photo:
            await message.answer_photo(
                photo=victim.face_photo,
                caption=text,
            )
        else:
            await message.answer(text)
        

@dp.message(Command("my_qr"))
async def cmd_my_qr(message: Message, sessionmaker):
    async with sessionmaker() as session:
        user = await get_user_by_tg_id(session, str(message.from_user.id))

        if user is None:
            await message.answer("Вы не зарегистрированы в системе.")
            return

        if not user.is_approved:
            await message.answer("Ваша заявка ещё не одобрена.")
            return

        if not user.qr_code_text:
            user = await ensure_user_qr_code(session, user)

        safe_filename = f"qr_user_{user.id}.png"
        file_path = os.path.join("QR", safe_filename)
        os.makedirs("QR", exist_ok=True)
        generate_custom_qr(
            text=user.qr_code_text,
            filename=file_path,
            box_size=12,
            fill_color="#2E7D32",
            back_color="#FFFFFF",
        )

        qr_file = FSInputFile(file_path)

        await message.answer_document(
            document=qr_file,
            caption=(
                "Вот ваш персональный QR-код.\n"
                "Сохраните его и не передавайте другим игрокам."
            )
        )


@dp.message(Command("kill"))
async def cmd_kill(message: Message, state: FSMContext, sessionmaker):
    async with sessionmaker() as session:
        user = await get_user_by_tg_id(session, str(message.from_user.id))

        if user is None:
            await message.answer("Вы не зарегистрированы в системе.")
            return

        if not user.is_approved:
            await message.answer("Ваша заявка ещё не одобрена.")
            return

        if user.game_mode not in ("classic", "team"):
            await message.answer("Для вас режим игры не определён.")
            return

        if not user.is_alive:
            await message.answer("Вы уже выбыли из игры.")
            return

        if user.game_mode == "classic":
            if user.victim_id is None:
                await message.answer("У вас сейчас нет назначенной цели.")
                return

        elif user.game_mode == "team":
            if user.team_id is None:
                await message.answer("Вы не состоите в команде.")
                return

            team = await get_team_by_id(session, user.team_id)
            if team is None:
                await message.answer("Не удалось найти вашу команду.")
                return

            if team.target_team_id is None:
                await message.answer("У вашей команды сейчас нет назначенной цели.")
                return

    await state.clear()
    await message.answer("Отправьте текст, зашитый в QR-код вашей цели.")
    await state.set_state(Killing.qr_text)


@dp.message(Killing.qr_text)
async def process_kill_qr_text(message: Message, state: FSMContext, sessionmaker):
    if not message.text:
        await message.answer("Пожалуйста, отправьте именно текст из QR-кода.")
        return

    qr_text = message.text.strip()
    if not qr_text:
        await message.answer("Текст QR-кода не может быть пустым. Попробуйте ещё раз.")
        return

    async with sessionmaker() as session:
        killer = await get_user_by_tg_id(session, str(message.from_user.id))

        if killer is None or not killer.is_approved or not killer.is_alive:
            await message.answer("Сейчас вы не можете совершить убийство.")
            await state.clear()
            return

        victim = await get_user_by_qr_text(session, qr_text)
        if victim is None:
            await message.answer("Игрок с таким QR-кодом не найден. Попробуйте ещё раз.")
            return

        if killer.game_mode == "classic":
            if killer.victim_id is None:
                await message.answer("У вас нет текущей цели.")
                await state.clear()
                return

            if victim.id != killer.victim_id:
                await message.answer("Этот QR-код не принадлежит вашей текущей цели.")
                return

        elif killer.game_mode == "team":
            if killer.team_id is None:
                await message.answer("Вы не состоите в команде.")
                await state.clear()
                return

            killer_team = await get_team_by_id(session, killer.team_id)
            if killer_team is None:
                await message.answer("Не удалось найти вашу команду.")
                await state.clear()
                return

            if killer_team.target_team_id is None:
                await message.answer("У вашей команды сейчас нет назначенной цели.")
                await state.clear()
                return

            if not victim.is_alive:
                await message.answer("Эта цель уже выбыла из игры.")
                return

            if victim.game_mode != "team":
                await message.answer("Этот QR-код не принадлежит игроку командного режима.")
                return

            if victim.team_id != killer_team.target_team_id:
                await message.answer("Этот игрок не принадлежит текущей команде-цели вашей команды.")
                return

        else:
            await message.answer("Для вас режим игры не определён.")
            await state.clear()
            return

        await state.update_data(
            victim_id=victim.id,
            victim_name=victim.name,
            qr_text=qr_text,
            game_mode=killer.game_mode,
        )

    await message.answer(
        f"QR-код подтверждён.\n"
        f"Цель: {victim.name}\n\n"
        f"Теперь отправьте фото-подтверждение убийства."
    )
    await state.set_state(Killing.photo)


@dp.message(Killing.photo)
async def process_kill_photo(message: Message, state: FSMContext, sessionmaker):
    if not message.photo:
        await message.answer("Пожалуйста, отправьте именно фотографию.")
        return

    data = await state.get_data()
    qr_text = data.get("qr_text")
    game_mode = data.get("game_mode")

    if not qr_text or not game_mode:
        await message.answer("Не удалось восстановить данные убийства. Начните заново через /kill.")
        await state.clear()
        return

    photo_file_id = message.photo[-1].file_id

    async with sessionmaker() as session:
        try:
            killer_before = await get_user_by_tg_id(session, str(message.from_user.id))
            if killer_before is None:
                await message.answer("Игрок не найден. Начните заново через /kill.")
                await state.clear()
                return

            victim_before = await get_user_by_qr_text(session, qr_text)
            if victim_before is None:
                await message.answer("Игрок с таким QR-кодом не найден.")
                await state.clear()
                return

            photo_bytes = await download_telegram_file_bytes(bot, photo_file_id)
            photo_path = build_kill_photo_path(
                base_dir=KILL_PHOTOS_DIR,
                killer_name=killer_before.name,
                victim_name=victim_before.name,
                ext="jpg",
            )
            save_bytes_to_file(photo_bytes, photo_path)

            new_target = None
            new_target_team = None
            is_game_over = False
            target_team_destroyed = False
            destroyed_team_name = None
            killer_team_id = None

            if game_mode == "classic":
                killer, victim, is_game_over = await process_classic_kill(
                    db=session,
                    killer_tg_id=str(message.from_user.id),
                    victim_qr_text=qr_text,
                    photo_file_id=photo_file_id,
                )

                if killer.victim_id is not None:
                    new_target = await get_user_victim(session, killer)

            elif game_mode == "team":
                if killer_before.team_id is not None:
                    killer_team_id = killer_before.team_id

                    killer_team_before = await get_team_by_id(session, killer_before.team_id)
                    if killer_team_before is not None and killer_team_before.target_team_id is not None:
                        destroyed_team = await get_team_by_id(session, killer_team_before.target_team_id)
                        if destroyed_team is not None:
                            destroyed_team_name = destroyed_team.name

                killer, victim, new_target_team, is_game_over, target_team_destroyed = await process_team_kill(
                    db=session,
                    killer_tg_id=str(message.from_user.id),
                    victim_qr_text=qr_text,
                    photo_file_id=photo_file_id,
                )

            else:
                await message.answer("Не удалось определить режим убийства.")
                await state.clear()
                return

        except ValueError as e:
            await message.answer(str(e))
            await state.clear()
            return
        except Exception as e:
            logging.exception("Ошибка при обработке убийства: %s", e)
            await message.answer("Произошла ошибка при обработке убийства.")
            await state.clear()
            return

    await state.clear()

    await message.answer(
        f"Убийство засчитано.\n"
        f"Вы устранили цель: {victim.name}\n"
        f"Ваш счёт: {killer.score}"
    )

    try:
        await bot.send_message(
            chat_id=int(victim.tg_id),
            text="Вы были устранены из игры."
        )
    except Exception as e:
        logging.error("Не удалось уведомить жертву %s: %s", victim.tg_id, e)

    if game_mode == "team" and target_team_destroyed and killer_team_id is not None:
        async with sessionmaker() as session:
            killer_team_players = await get_alive_team_players(session, killer_team_id)

        if new_target_team is not None:
            notify_text = (
                f"Команда-противник {destroyed_team_name} полностью уничтожена.\n\n"
                f"Новая цель вашей команды: {new_target_team.name}"
            )
        else:
            notify_text = (
                f"Команда-противник {destroyed_team_name} полностью уничтожена."
            )

        for player in killer_team_players:
            try:
                await bot.send_message(
                    chat_id=int(player.tg_id),
                    text=notify_text,
                )
            except Exception as e:
                logging.error(
                    "Не удалось уведомить игрока %s об уничтожении команды: %s",
                    player.tg_id,
                    e,
                )

    if is_game_over:
        async with sessionmaker() as session:
            if game_mode == "classic":
                winner = await get_last_alive_classic_player(session)

                if winner is not None:
                    await message.answer(
                        f"Игра завершена.\n"
                        f"Победитель: {winner.name}"
                    )

                    try:
                        await bot.send_message(
                            chat_id=int(winner.tg_id),
                            text="Поздравляем! Вы победили в классическом режиме."
                        )
                    except Exception as e:
                        logging.error("Не удалось уведомить победителя %s: %s", winner.tg_id, e)

            elif game_mode == "team":
                alive_teams = await get_alive_teams(session)

                if len(alive_teams) == 1:
                    winner_team = alive_teams[0]
                    await message.answer(
                        f"Игра завершена.\n"
                        f"Победила команда: {winner_team.name}"
                    )

                    winner_players = await get_alive_team_players(session, winner_team.id)
                    for player in winner_players:
                        try:
                            await bot.send_message(
                                chat_id=int(player.tg_id),
                                text="Поздравляем! Ваша команда победила в командном режиме."
                            )
                        except Exception as e:
                            logging.error(
                                "Не удалось уведомить участника команды-победителя %s: %s",
                                player.tg_id,
                                e,
                            )

        return

    if game_mode == "classic":
        if new_target is None:
            await message.answer("У вас пока нет новой цели.")
            return

        text = (
            "Ваша новая цель:\n"
            f"{new_target.name}\n"
            f"Курс: {new_target.course}"
        )

        if new_target.face_photo:
            await message.answer_photo(
                photo=new_target.face_photo,
                caption=text,
            )
        else:
            await message.answer(text)

    elif game_mode == "team":
        async with sessionmaker() as session:
            killer_fresh = await get_user_by_tg_id(session, str(message.from_user.id))
            if killer_fresh is None or killer_fresh.team_id is None:
                await message.answer("Не удалось обновить данные вашей команды.")
                return

            killer_team = await get_team_by_id(session, killer_fresh.team_id)
            if killer_team is None or killer_team.target_team_id is None:
                await message.answer("У вашей команды пока нет новой цели.")
                return

            target_team = await get_team_target(session, killer_team)
            if target_team is None:
                await message.answer("Не удалось найти новую команду-цель.")
                return

            target_players = await get_alive_team_players(session, target_team.id)

        if target_players:
            members_text = "\n".join(
                f"• {player.name}, курс {player.course}"
                for player in target_players
            )
        else:
            members_text = "Нет живых участников."

        text = (
            "Текущая цель вашей команды:\n"
            f"{target_team.name}\n\n"
            "Живые участники команды-цели:\n"
            f"{members_text}"
        )

        if target_team.team_photo:
            await message.answer_photo(
                photo=target_team.team_photo,
                caption=text,
            )
        else:
            await message.answer(text)


@dp.message(F.text, Command('admin'))
async def admin_mode(message: Message, state: FSMContext, sessionmaker):
    async with sessionmaker() as session:
        if await is_admin(session, str(message.from_user.id)):
            await message.answer('У вас уже есть права администратора.')
            return
        await message.answer('Введите пароль:')
        await state.set_state(Access.password)


@dp.message(Access.password)
async def get_access(message: Message, state: FSMContext, sessionmaker):
    async with sessionmaker() as session:
        if message.text == config.admin_password.get_secret_value():
            await make_admin(session, str(message.from_user.id))
            await message.answer('Верификация пройдена')
        else:
            await message.answer('Пароль неверный')
        await state.clear()


@dp.message(F.text, Command('send_message'))
async def broadcast_all_command(message: Message, state: FSMContext, sessionmaker):
    async with sessionmaker() as session:
        if not await is_admin(session, str(message.from_user.id)):
            await message.answer('У вас нет прав администратора.')
            return
        await message.answer('Введите сообщение для рассылки:')
        await state.set_state(Admin.message)


@dp.message(Admin.message)
async def process_message(message: Message, state: FSMContext, sessionmaker):
    async with sessionmaker() as session:
        users = await get_all_tg_ids(session)
        for user_id in users:
            try:
                await message.bot.send_message(user_id, message.text)
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
        await message.answer('Рассылка завершена.')
        await state.clear()


@dp.message(F.text, Command('send_private_message'))
async def broadcast_private_command(message: Message, state: FSMContext, sessionmaker):
    async with sessionmaker() as session:
        if not await is_admin(session, str(message.from_user.id)):
            await message.answer('У вас нет прав администратора.')
            return
        await message.answer('Введите id:')
        await state.set_state(PrivateMessage.tg_id)


@dp.message(PrivateMessage.tg_id)
async def process_private_message(message: Message, state: FSMContext, sessionmaker):
    async with sessionmaker() as session:
        await state.update_data(tg_id=message.text)
        await message.answer('Введите сообщение:')
        await state.set_state(PrivateMessage.message)


@dp.message(PrivateMessage.message)
async def process_private_message_sending(message: Message, state: FSMContext, sessionmaker):
    async with sessionmaker() as session:
        data = await state.get_data()
        await message.bot.send_message(data['tg_id'], message.text)
        await message.answer('Рассылка завершена.')
        await state.clear()


@dp.message(Command("start_team_round"))
async def cmd_start_team_round(message: Message, sessionmaker):
    async with sessionmaker() as session:
        admin = await get_user_by_tg_id(session, str(message.from_user.id))

        if admin is None or not admin.is_admin:
            await message.answer("Эта команда доступна только администратору.")
            return

        try:
            teams = await assign_team_targets(session)
        except ValueError as e:
            await message.answer(str(e))
            return
        except Exception as e:
            logging.exception("Ошибка при запуске командного раунда: %s", e)
            await message.answer("Произошла ошибка при запуске командного режима.")
            return

        success_count = 0
        failed_count = 0

        for team in teams:
            target_team = await get_team_target(session, team)
            if target_team is None:
                continue

            target_players = await get_alive_team_players(session, target_team.id)

            members_text = ""
            if target_players:
                members_lines = [
                    f"• {player.name}, курс {player.course}"
                    for player in target_players
                ]
                members_text = "\n".join(members_lines)
            else:
                members_text = "Нет живых участников."

            team_players = await get_alive_team_players(session, team.id)

            text = (
                "Командный раунд запущен!\n\n"
                f"Цель вашей команды: {target_team.name}\n\n"
                "Живые участники команды-цели:\n"
                f"{members_text}\n\n"
                "Используйте /kill после успешного устранения цели."
            )

            for player in team_players:
                try:
                    if target_team.team_photo:
                        await bot.send_photo(
                            chat_id=int(player.tg_id),
                            photo=target_team.team_photo,
                            caption=text,
                        )
                    else:
                        await bot.send_message(
                            chat_id=int(player.tg_id),
                            text=text,
                        )
                    success_count += 1
                except Exception as e:
                    failed_count += 1
                    logging.exception(
                        "Не удалось отправить командную цель игроку %s: %s",
                        player.tg_id,
                        e,
                    )

        await message.answer(
            "Командный раунд успешно запущен.\n"
            f"Команд: {len(teams)}\n"
            f"Успешно отправлено: {success_count}\n"
            f"Не удалось отправить: {failed_count}"
        )


@dp.message(Command("team_target"))
async def cmd_team_target(message: Message, sessionmaker):
    async with sessionmaker() as session:
        user = await get_user_by_tg_id(session, str(message.from_user.id))

        if user is None:
            await message.answer("Вы не зарегистрированы в системе.")
            return

        if not user.is_approved:
            await message.answer("Ваша заявка ещё не одобрена.")
            return

        if user.game_mode != "team":
            await message.answer("Эта команда доступна только в командном режиме.")
            return

        if not user.is_alive:
            await message.answer("Вы уже выбыли из игры.")
            return

        if user.team_id is None:
            await message.answer("Вы не состоите в команде.")
            return

        team = await get_team_by_id(session, user.team_id)
        if team is None:
            await message.answer("Не удалось найти вашу команду.")
            return

        if team.target_team_id is None:
            await message.answer("Вашей команде пока не назначена цель.")
            return

        target_team = await get_team_target(session, team)
        if target_team is None:
            await message.answer("Не удалось найти команду-цель.")
            return

        target_players = await get_alive_team_players(session, target_team.id)

        if target_players:
            members_text = "\n".join(
                f"• {player.name}, курс {player.course}"
                for player in target_players
            )
        else:
            members_text = "Нет живых участников."

        text = (
            "Текущая цель вашей команды:\n"
            f"{target_team.name}\n\n"
            "Живые участники команды-цели:\n"
            f"{members_text}"
        )

        if target_team.team_photo:
            await message.answer_photo(
                photo=target_team.team_photo,
                caption=text,
            )
        else:
            await message.answer(text)


def parse_single_arg(text: str) -> str | None:
    parts = (text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip()


async def find_user_for_admin(sessionmaker, raw_arg: str):
    """
    Ищет пользователя либо по внутреннему user_id, либо по tg_id.
    Сначала пытаемся как user_id, потом как tg_id.
    """
    async with sessionmaker() as session:
        if raw_arg.isdigit():
            user = await get_user_by_id(session, int(raw_arg))
            if user is not None:
                return user

            user = await get_user_by_tg_id(session, raw_arg)
            if user is not None:
                return user
        return None


async def notify_user_about_new_target(
    bot: Bot,
    session: AsyncSession,
    tg_id: str,
    prefix: str = "Ваша цель была обновлена."
) -> None:
    """
    Отправляет пользователю сообщение о новой цели:
    - текст
    - имя цели
    - курс цели
    - фото цели

    Если фото нет, отправляет только текст.
    Предполагается, что user.face_photo может быть:
    1) Telegram file_id
    2) локальным путем до файла
    """
    user = await get_user_by_tg_id(session, tg_id)
    if user is None:
        return

    if user.victim_id is None:
        text = (
            f"{prefix}\n"
            "Сейчас у вас нет назначенной цели."
        )
        try:
            await bot.send_message(chat_id=int(tg_id), text=text)
        except Exception:
            pass
        return

    target = await get_user_by_id(session, user.victim_id)
    if target is None:
        text = (
            f"{prefix}\n"
            "Сейчас у вас нет назначенной цели."
        )
        try:
            await bot.send_message(chat_id=int(tg_id), text=text)
        except Exception:
            pass
        return

    caption = (
        f"{prefix}\n\n"
        f"Ваша новая цель: {target.name}\n"
        f"Курс: {target.course}"
    )

    try:
        if target.face_photo:
            # Если это локальный путь к файлу
            if Path(str(target.face_photo)).exists():
                photo = FSInputFile(str(target.face_photo))
                await bot.send_photo(
                    chat_id=int(tg_id),
                    photo=photo,
                    caption=caption
                )
                return

            # Иначе считаем, что это Telegram file_id
            await bot.send_photo(
                chat_id=int(tg_id),
                photo=target.face_photo,
                caption=caption
            )
            return

        # Если фото нет вообще
        await bot.send_message(chat_id=int(tg_id), text=caption)

    except Exception:
        # Фолбэк: хотя бы текстом
        try:
            await bot.send_message(chat_id=int(tg_id), text=caption)
        except Exception:
            pass


@dp.message(Command("delete_player"))
async def cmd_delete_player(message: Message, sessionmaker, bot: Bot):
    async with sessionmaker() as session:
        if not await is_admin(session, str(message.from_user.id)):
            await message.answer("У вас нет доступа к этой команде.")
            return

        arg = parse_single_arg(message.text)
        if arg is None:
            await message.answer(
                "Использование:\n"
                "/delete_player <user_id>\n"
                "или\n"
                "/delete_player <tg_id>"
            )
            return

        target_user = await find_user_for_admin(sessionmaker, arg)
        if target_user is None:
            await message.answer("Пользователь не найден.")
            return

        if str(target_user.tg_id) == str(message.from_user.id):
            await message.answer("Нельзя удалить самого себя этой командой.")
            return

        result = await delete_user_with_rewire(session, target_user.id)

        if not result["ok"]:
            await message.answer("Не удалось удалить пользователя.")
            return

        await message.answer(
            f"Пользователь удалён: {result['deleted_user_name']}"
        )

    # новая сессия для чтения актуальных целей после commit
    async with sessionmaker() as session:
        for tg_id in result["rewired_user_tg_ids"]:
            await notify_user_about_new_target(
                bot=bot,
                session=session,
                tg_id=tg_id,
            )


@dp.message(Command("revive_player"))
async def cmd_revive_player(message: Message, sessionmaker, bot: Bot):
    async with sessionmaker() as session:
        if not await is_admin(session, str(message.from_user.id)):
            await message.answer("У вас нет доступа к этой команде.")
            return

        arg = parse_single_arg(message.text)
        if arg is None:
            await message.answer(
                "Использование:\n"
                "/revive_player <user_id>\n"
                "или\n"
                "/revive_player <tg_id>"
            )
            return

        target_user = await find_user_for_admin(sessionmaker, arg)
        if target_user is None:
            await message.answer("Пользователь не найден.")
            return

        result = await revive_user_with_rewire(session, target_user.id)

        if not result["ok"]:
            await message.answer("Не удалось оживить пользователя.")
            return

        if result["already_alive"]:
            await message.answer(
                f"Игрок уже был жив: {result['revived_user_name']}"
            )
            return

        await message.answer(
            f"Игрок оживлён: {result['revived_user_name']}"
        )

    async with sessionmaker() as session:
        for tg_id in result["rewired_user_tg_ids"]:
            await notify_user_about_new_target(
                bot=bot,
                session=session,
                tg_id=tg_id,
            )


@dp.message(Command("all_tg_ids"))
async def cmd_all_tg_ids(message: Message, sessionmaker):
    async with sessionmaker() as session:
        if not await is_admin(session, str(message.from_user.id)):
            await message.answer("У вас нет доступа к этой команде.")
            return

        tg_ids = await get_all_tg_ids(session)

        if not tg_ids:
            await message.answer("Список tg_id пуст.")
            return

        text = "Все tg_id пользователей:\n\n" + "\n".join(map(str, tg_ids))

        # Telegram не любит слишком длинные сообщения
        if len(text) <= 4000:
            await message.answer(text)
            return

        chunks = []
        current = "Все tg_id пользователей:\n\n"
        for tg_id in tg_ids:
            line = f"{tg_id}\n"
            if len(current) + len(line) > 4000:
                chunks.append(current)
                current = line
            else:
                current += line
        if current:
            chunks.append(current)

        for chunk in chunks:
            await message.answer(chunk)


def build_player_rating_text(players) -> str:
    if not players:
        return "Рейтинг игроков пуст."

    lines = ["Рейтинг игроков:\n"]
    for i, user in enumerate(players, start=1):
        lines.append(
            f"{i}. {user.name} | "
            f"id={user.id} | "
            f"tg_id={user.tg_id} | "
            f"score={user.score} | "
            f"{'alive' if user.is_alive else 'dead'} | "
            f"mode={user.game_mode}"
        )
    return "\n".join(lines)


def build_team_rating_text(teams) -> str:
    if not teams:
        return "Рейтинг команд пуст."

    lines = ["Рейтинг команд:\n"]
    for i, team in enumerate(teams, start=1):
        lines.append(
            f"{i}. {team.name} | id={team.id} | score={team.score}"
        )
    return "\n".join(lines)


async def send_long_message(message: Message, text: str, chunk_size: int = 4000):
    if len(text) <= chunk_size:
        await message.answer(text)
        return

    start = 0
    while start < len(text):
        await message.answer(text[start:start + chunk_size])
        start += chunk_size


@dp.message(Command("player_rating"))
async def cmd_player_rating(message: Message, sessionmaker):
    async with sessionmaker() as session:
        players = await get_player_rating(session)
        text = build_player_rating_text(players)
        await send_long_message(message, text)


@dp.message(Command("team_rating"))
async def cmd_team_rating(message: Message, sessionmaker):
    async with sessionmaker() as session:
        teams = await get_team_rating(session)
        text = build_team_rating_text(teams)
        await send_long_message(message, text)


def format_users_admin_list(users: list[User]) -> str:
    if not users:
        return "Пользователей нет."

    lines = ["Список всех игроков:\n"]

    for user in users:
        flags = [
            f"is_admin={user.is_admin}",
            f"is_approved={user.is_approved}",
            f"is_alive={user.is_alive}",
        ]

        if hasattr(user, "game_mode"):
            flags.append(f"mode={user.game_mode}")

        if hasattr(user, "team_id"):
            flags.append(f"team_id={user.team_id}")

        if hasattr(user, "victim_id"):
            flags.append(f"victim_id={user.victim_id}")

        lines.append(
            f"id={user.id} | "
            f"tg_id={user.tg_id} | "
            f"name={user.name} | "
            f"course={user.course} | "
            f"score={user.score} | "
            + " | ".join(flags)
        )

    return "\n".join(lines)


@dp.message(Command("all_players_full"))
async def cmd_all_players_full(message: Message, sessionmaker):
    async with sessionmaker() as session:
        if not await is_admin(session, str(message.from_user.id)):
            await message.answer("У вас нет доступа к этой команде.")
            return

        users = await get_all_users_full(session)
        text = format_users_admin_list(users)
        await send_long_message(message, text)


@dp.message(Command("set_score"))
async def cmd_set_score(message: Message, sessionmaker):
    async with sessionmaker() as session:
        if not await is_admin(session, str(message.from_user.id)):
            await message.answer("У вас нет доступа к этой команде.")
            return

        parts = (message.text or "").strip().split()
        if len(parts) != 3:
            await message.answer(
                "Использование:\n"
                "/set_score <user_id> <new_score>"
            )
            return

        _, raw_user_id, raw_score = parts

        if not raw_user_id.isdigit():
            await message.answer("user_id должен быть целым числом.")
            return

        try:
            user_id = int(raw_user_id)
            new_score = int(raw_score)
        except ValueError:
            await message.answer("new_score должен быть целым числом.")
            return

        user = await get_user_by_id(session, user_id)
        if user is None:
            await message.answer("Пользователь не найден.")
            return

        updated_user = await set_user_score(session, user_id, new_score)
        if updated_user is None:
            await message.answer("Не удалось изменить score.")
            return

        await message.answer(
            f"Игроку обновлены очки.\n"
            f"id={updated_user.id}\n"
            f"name={updated_user.name}\n"
            f"Новый score={updated_user.score}"
        )



@dp.message(Command("help"))
async def cmd_help(message: Message, sessionmaker):
    async with sessionmaker() as session:
        if await is_admin(session, str(message.from_user.id)):
            await message.answer(ADMIN_HELP_TEXT)
        else:
            await message.answer(USER_HELP_TEXT)


async def main() -> None:
    SessionLocal = await create_db()
    async with bot:
        await dp.start_polling(bot, sessionmaker=SessionLocal)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())