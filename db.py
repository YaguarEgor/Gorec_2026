from datetime import datetime

from models import Base, Kill, Team, User
from qr_generating import generate_random_qr_text
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker
from sqlalchemy.engine import URL
from sqlalchemy import NullPool, select, func

import random
import os
from functools import partial

new_point_system = False  # когда со множителями работаем


async def get_user_by_tg_id(db: AsyncSession, tg_id: str) -> User | None:
    stmt = select(User).where(User.tg_id == tg_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_team_by_name(db: AsyncSession, team_name: str) -> Team | None:
    stmt = select(Team).where(Team.name == team_name)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_team(db: AsyncSession, name: str, team_photo: str) -> Team:
    team = Team(
        name=name,
        team_photo=team_photo,
        score=0,
        target_team_id=None,
        destroyed_target_at=None,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


async def create_user_application(
    db: AsyncSession,
    tg_id: str,
    name: str,
    course: int,
    face_photo: str,
    game_mode: str,
    team_id: int | None = None,
) -> User:
    user = User(
        tg_id=tg_id,
        name=name,
        course=course,
        face_photo=face_photo,
        is_admin=False,
        game_mode=game_mode,
        is_approved=False,
        reject_reason=None,
        team_id=team_id,
        is_alive=True,
        score=0,
        victim_id=None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_application(
    db: AsyncSession,
    user: User,
    name: str,
    course: int,
    face_photo: str,
    game_mode: str,
    team_id: int | None = None,
) -> User:
    user.name = name
    user.course = course
    user.face_photo = face_photo
    user.game_mode = game_mode
    user.team_id = team_id
    user.is_approved = False
    user.reject_reason = None
    user.is_alive = True
    user.victim_id = None
    await db.commit()
    await db.refresh(user)
    return user


async def approve_user_application(db: AsyncSession, user_id: int) -> User | None:
    user = await get_user_by_id(db, user_id)
    if user is None:
        return None
    user.is_approved = True
    user.reject_reason = None
    user.is_alive = True
    user.victim_id = None
    if not user.qr_code_text:
        while True:
            qr_text = generate_random_qr_text()
            existing = await get_user_by_qr_text(db, qr_text)
            if existing is None:
                user.qr_code_text = qr_text
                break
    await db.commit()
    await db.refresh(user)
    return user


async def reject_user_application(db: AsyncSession, user_id: int, reason: str) -> User | None:
    user = await get_user_by_id(db, user_id)
    if user is None:
        return None
    user.is_approved = False
    user.reject_reason = reason
    await db.commit()
    await db.refresh(user)
    return user


async def get_pending_users(db: AsyncSession) -> list[User]:
    stmt = select(User).where(
        User.is_approved == False,
        User.reject_reason.is_(None)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_alive_classic_players(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User)
        .where(
            User.game_mode == "classic",
            User.is_approved == True,
            User.is_alive == True,
        )
        .order_by(User.id)
    )
    return list(result.scalars().all())


async def assign_classic_targets(session: AsyncSession) -> list[User]:
    """
    Назначает цели игрокам классического режима в виде одного цикла:
    A -> B -> C -> ... -> A

    Условия:
    - берутся только одобренные живые игроки classic-режима;
    - у каждого игрока будет ровно одна цель;
    - сам себе игрок целью стать не может;
    - цикл корректен при количестве игроков >= 2.

    Возвращает список игроков в том порядке, в котором они были
    после перемешивания и назначения целей.
    """
    players = await get_alive_classic_players(session)

    if len(players) < 2:
        raise ValueError("Для запуска классического режима нужно минимум 2 живых одобренных игрока.")

    random.shuffle(players)

    n = len(players)
    for i in range(n):
        current_player = players[i]
        next_player = players[(i + 1) % n]
        current_player.victim_id = next_player.id

    await session.commit()

    return players


async def get_user_victim(session: AsyncSession, user: User) -> User | None:
    if user.victim_id is None:
        return None

    result = await session.execute(
        select(User).where(User.id == user.victim_id)
    )
    return result.scalar_one_or_none()


async def count_alive_classic_players(db: AsyncSession) -> int:
    stmt = select(func.count()).select_from(User).where(
        User.game_mode == "classic",
        User.is_approved == True,
        User.is_alive == True,
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_last_alive_classic_player(db: AsyncSession) -> User | None:
    stmt = select(User).where(
        User.game_mode == "classic",
        User.is_approved == True,
        User.is_alive == True,
    )
    result = await db.execute(stmt)
    players = list(result.scalars().all())

    if len(players) == 1:
        return players[0]
    return None


async def get_alive_classic_user_by_tg_id(db: AsyncSession, tg_id: str) -> User | None:
    stmt = select(User).where(
        User.tg_id == tg_id,
        User.game_mode == "classic",
        User.is_approved == True,
        User.is_alive == True,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_qr_text(db: AsyncSession, qr_text: str) -> User | None:
    stmt = select(User).where(User.qr_code_text == qr_text)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def ensure_user_qr_code(db: AsyncSession, user: User) -> User:
    if user.qr_code_text:
        return user

    while True:
        qr_text = generate_random_qr_text()
        existing = await get_user_by_qr_text(db, qr_text)
        if existing is None:
            user.qr_code_text = qr_text
            await db.commit()
            await db.refresh(user)
            return user


async def process_classic_kill(
    db: AsyncSession,
    killer_tg_id: str,
    victim_qr_text: str,
    photo_file_id: str,
) -> tuple[User, User, bool]:
    killer = await get_user_by_tg_id(db, killer_tg_id)
    if killer is None:
        raise ValueError("Игрок не найден.")

    if not killer.is_approved:
        raise ValueError("Ваша заявка ещё не одобрена.")

    if killer.game_mode != "classic":
        raise ValueError("Убийства через эту команду доступны только в классическом режиме.")

    if not killer.is_alive:
        raise ValueError("Вы уже выбыли из игры.")

    if killer.victim_id is None:
        raise ValueError("У вас сейчас нет назначенной цели.")

    victim = await get_user_by_qr_text(db, victim_qr_text)
    if victim is None:
        raise ValueError("Игрок с таким QR-кодом не найден.")

    if victim.id != killer.victim_id:
        raise ValueError("Этот QR-код не принадлежит вашей текущей цели.")

    if not victim.is_alive:
        raise ValueError("Эта цель уже выбыла из игры.")
    

    next_target_id = victim.victim_id

    kill = Kill(
        killer_id=killer.id,
        victim_id=victim.id,
        photo_file_id=photo_file_id,
        qr_text=victim_qr_text,
        mode="classic",
    )
    db.add(kill)

    victim.is_alive = False
    victim.victim_id = None

    killer.score += 1

    if next_target_id == killer.id:
        killer.victim_id = None
    else:
        killer.victim_id = next_target_id

    await db.commit()
    await db.refresh(killer)
    await db.refresh(victim)

    alive_count = await count_alive_classic_players(db)
    is_game_over = alive_count <= 1

    return killer, victim, is_game_over


async def is_admin(db: AsyncSession, tg_id: str):
    user = await get_user_by_tg_id(db, tg_id=tg_id)
    return True if user.is_admin else False


async def make_admin(db: AsyncSession, tg_id: str):
    user = await get_user_by_tg_id(db, tg_id=tg_id)
    user.is_admin = True
    await db.commit()
    await db.refresh(user)


async def get_alive_team_players(db: AsyncSession, team_id: int) -> list[User]:
    stmt = (
        select(User)
        .where(
            User.team_id == team_id,
            User.game_mode == "team",
            User.is_approved == True,
            User.is_alive == True,
        )
        .order_by(User.id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_alive_team_players(db: AsyncSession, team_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(User)
        .where(
            User.team_id == team_id,
            User.game_mode == "team",
            User.is_approved == True,
            User.is_alive == True,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_alive_teams(db: AsyncSession) -> list[Team]:
    stmt = (
        select(Team)
        .join(User, User.team_id == Team.id)
        .where(
            User.game_mode == "team",
            User.is_approved == True,
            User.is_alive == True,
        )
        .distinct()
        .order_by(Team.id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_team_target(db: AsyncSession, team: Team) -> Team | None:
    if team.target_team_id is None:
        return None

    stmt = select(Team).where(Team.id == team.target_team_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def assign_team_targets(db: AsyncSession) -> list[Team]:
    """
    Назначает командам цели в виде цикла:
    Team A -> Team B -> Team C -> ... -> Team A

    Берутся только команды, у которых есть хотя бы один живой
    одобренный игрок в командном режиме.

    Возвращает список команд в том порядке, в котором они были
    после перемешивания и назначения целей.
    """
    teams = await get_alive_teams(db)

    if len(teams) < 2:
        raise ValueError("Для запуска командного режима нужно минимум 2 живые команды.")

    random.shuffle(teams)

    n = len(teams)
    for i in range(n):
        current_team = teams[i]
        next_team = teams[(i + 1) % n]
        current_team.target_team_id = next_team.id
        current_team.destroyed_target_at = None

    await db.commit()

    return teams


async def get_team_by_id(db: AsyncSession, team_id: int) -> Team | None:
    stmt = select(Team).where(Team.id == team_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def process_team_kill(
    db: AsyncSession,
    killer_tg_id: str,
    victim_qr_text: str,
    photo_file_id: str,
) -> tuple[User, User, Team | None, bool, bool]:
    killer = await get_user_by_tg_id(db, killer_tg_id)
    if killer is None:
        raise ValueError("Игрок не найден.")

    if not killer.is_approved:
        raise ValueError("Ваша заявка ещё не одобрена.")

    if killer.game_mode != "team":
        raise ValueError("Убийства через эту команду доступны только в командном режиме.")

    if not killer.is_alive:
        raise ValueError("Вы уже выбыли из игры.")

    if killer.team_id is None:
        raise ValueError("Вы не состоите в команде.")

    killer_team = await get_team_by_id(db, killer.team_id)
    if killer_team is None:
        raise ValueError("Команда убийцы не найдена.")

    if killer_team.target_team_id is None:
        raise ValueError("У вашей команды сейчас нет назначенной цели.")

    victim = await get_user_by_qr_text(db, victim_qr_text)
    if victim is None:
        raise ValueError("Игрок с таким QR-кодом не найден.")

    if victim.game_mode != "team":
        raise ValueError("Этот QR-код не принадлежит игроку командного режима.")

    if victim.team_id is None:
        raise ValueError("Игрок не состоит в команде.")

    if not victim.is_alive:
        raise ValueError("Эта цель уже выбыла из игры.")

    if victim.team_id != killer_team.target_team_id:
        raise ValueError("Этот игрок не принадлежит текущей команде-цели вашей команды.")

    if victim.id == killer.id:
        raise ValueError("Нельзя устранить самого себя.")

    target_team = await get_team_by_id(db, killer_team.target_team_id)
    if target_team is None:
        raise ValueError("Команда-цель не найдена.")

    kill = Kill(
        killer_id=killer.id,
        victim_id=victim.id,
        photo_file_id=photo_file_id,
        qr_text=victim_qr_text,
        mode="team",
    )
    db.add(kill)

    victim.is_alive = False
    victim.victim_id = None

    killer.score += 1
    killer_team.score += 1

    await db.flush()

    remaining_in_target_team = await count_alive_team_players(db, target_team.id)

    new_target_team = None
    target_team_destroyed = False

    if remaining_in_target_team == 0:
        target_team_destroyed = True
        killer_team.target_team_id = target_team.target_team_id
        target_team.destroyed_target_at = datetime.utcnow()

        if killer_team.target_team_id == killer_team.id:
            killer_team.target_team_id = None
        elif killer_team.target_team_id is not None:
            new_target_team = await get_team_by_id(db, killer_team.target_team_id)

    await db.commit()
    await db.refresh(killer)
    await db.refresh(victim)
    await db.refresh(killer_team)

    if new_target_team is not None:
        await db.refresh(new_target_team)

    alive_teams = await get_alive_teams(db)
    is_game_over = len(alive_teams) <= 1

    return killer, victim, new_target_team, is_game_over, target_team_destroyed


async def get_all_tg_ids(db: AsyncSession) -> list[str]:
    """
    Возвращает tg_id всех пользователей вообще, без фильтров.
    """
    stmt = select(User.tg_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_player_rating(db: AsyncSession) -> list[User]:
    """
    Возвращает рейтинг игроков по score по убыванию.
    Админы не исключаются, потому что пользователь отдельно уточнил:
    рейтинг всех игроков. Если захочешь — потом можно легко добавить фильтр.
    """
    stmt = select(User).order_by(User.score.desc(), User.id.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_team_rating(db: AsyncSession) -> list[Team]:
    """
    Возвращает рейтинг команд по score по убыванию.
    """
    stmt = select(Team).order_by(Team.score.desc(), Team.id.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_user_with_rewire(db: AsyncSession, user_id: int) -> dict:
    """
    Удаляет пользователя и, если нужно, сшивает круг в classic mode.

    Возвращает dict:
    {
        "ok": bool,
        "deleted_user_name": str | None,
        "rewired_user_tg_ids": list[str],   # кому надо прислать уведомление
    }
    """
    user = await db.get(User, user_id)
    if user is None:
        return {
            "ok": False,
            "deleted_user_name": None,
            "rewired_user_tg_ids": [],
        }

    rewired_users: list[User] = []

    if user.game_mode == "classic" and user.is_alive:
        hunter_stmt = select(User).where(User.victim_id == user.id)
        hunter_result = await db.execute(hunter_stmt)
        hunter = hunter_result.scalar_one_or_none()

        if hunter is not None:
            hunter.victim_id = user.victim_id
            rewired_users.append(hunter)

    deleted_user_name = user.name

    await db.delete(user)
    await db.commit()

    return {
        "ok": True,
        "deleted_user_name": deleted_user_name,
        "rewired_user_tg_ids": [str(u.tg_id) for u in rewired_users],
    }


async def revive_user_with_rewire(db: AsyncSession, user_id: int) -> dict:
    """
    Оживляет игрока и встраивает его в classic-круг.

    Возвращает dict:
    {
        "ok": bool,
        "already_alive": bool,
        "revived_user_tg_id": str | None,
        "revived_user_name": str | None,
        "rewired_user_tg_ids": list[str],   # чьи цели изменились
    }
    """
    user = await db.get(User, user_id)
    if user is None:
        return {
            "ok": False,
            "already_alive": False,
            "revived_user_tg_id": None,
            "revived_user_name": None,
            "rewired_user_tg_ids": [],
        }

    if user.is_alive:
        return {
            "ok": True,
            "already_alive": True,
            "revived_user_tg_id": str(user.tg_id),
            "revived_user_name": user.name,
            "rewired_user_tg_ids": [],
        }

    user.is_alive = True

    rewired_users: list[User] = []

    if user.game_mode != "classic":
        await db.commit()
        return {
            "ok": True,
            "already_alive": False,
            "revived_user_tg_id": str(user.tg_id),
            "revived_user_name": user.name,
            "rewired_user_tg_ids": [],
        }

    alive_stmt = select(User).where(
        User.game_mode == "classic",
        User.is_alive.is_(True),
        User.id != user.id,
    )
    alive_result = await db.execute(alive_stmt)
    alive_players = list(alive_result.scalars().all())

    if not alive_players:
        user.victim_id = user.id
        await db.commit()
        return {
            "ok": True,
            "already_alive": False,
            "revived_user_tg_id": str(user.tg_id),
            "revived_user_name": user.name,
            "rewired_user_tg_ids": [str(user.tg_id)],
        }

    last_kill_stmt = (
        select(Kill)
        .where(Kill.victim_id == user.id, Kill.mode == "classic")
        .order_by(Kill.created_at.desc(), Kill.id.desc())
    )
    last_kill_result = await db.execute(last_kill_stmt)
    last_kill = last_kill_result.scalars().first()

    insert_after: User | None = None

    if last_kill is not None:
        possible_hunter = await db.get(User, last_kill.killer_id)
        if (
            possible_hunter is not None
            and possible_hunter.is_alive
            and possible_hunter.game_mode == "classic"
            and possible_hunter.id != user.id
        ):
            insert_after = possible_hunter

    if insert_after is None:
        insert_after = alive_players[0]

    old_target_id = insert_after.victim_id
    user.victim_id = old_target_id
    insert_after.victim_id = user.id

    rewired_users.append(insert_after)

    await db.commit()

    return {
        "ok": True,
        "already_alive": False,
        "revived_user_tg_id": str(user.tg_id),
        "revived_user_name": user.name,
        "rewired_user_tg_ids": [str(u.tg_id) for u in rewired_users] + [str(user.tg_id)],
    }


async def get_current_target_for_tg_id(db: AsyncSession, tg_id: str) -> User | None:
    user = await get_user_by_tg_id(db, tg_id)
    if user is None or user.victim_id is None:
        return None
    return await db.get(User, user.victim_id)


async def get_all_users_full(db: AsyncSession) -> list[User]:
    """
    Возвращает всех пользователей.
    Удобно для админского просмотра полного списка игроков.
    """
    stmt = select(User).order_by(User.id.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def set_user_score(db: AsyncSession, user_id: int, new_score: int) -> User | None:
    """
    Устанавливает пользователю score = new_score.
    Возвращает обновлённого пользователя или None, если пользователь не найден.
    """
    user = await db.get(User, user_id)
    if user is None:
        return None

    user.score = new_score
    await db.commit()
    await db.refresh(user)
    return user


async def create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def create_db():
    db_url = ''

    # async with async_session_local() as session:
    #     # await register_user(session, 'tg_id', "Artem", 'photo_id')
    #     print('!')
    #     print(await get_data(session))

    engine: AsyncEngine = create_async_engine(
        db_url,
        echo=True,
        poolclass=NullPool,
        pool_pre_ping=True,
    )

    async_session_local = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession
    )

    await create_tables(engine)
    return async_session_local
