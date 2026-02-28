from models import Base, User, Daily
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker
from sqlalchemy import select

import random
import os
from functools import partial

new_point_system = False  # когда со множителями работаем


async def create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def register_user(db: AsyncSession, tg_id: str, name: str, photo: str) -> None:
    """Регистрация нового участника"""
    db_user = User(tg_id=tg_id, name=name, photo=photo, is_admin=False, qr_name="", victim=-1, dead=False)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    user = await get_user(db, tg_id)
    db_daily = Daily(user_id=user.id, score=0)
    db.add(db_daily)
    await db.commit()
    await db.refresh(db_daily)


async def set_nule_score(db: AsyncSession) -> None:
    users = await get_data(db)
    for user in users:
        stmt = select(Daily).where(Daily.user_id == user.id)
        dailys = await db.execute(stmt)
        daily = dailys.scalar()
        daily.score = 0
        await db.commit()



async def get_user(db: AsyncSession, tg_id: str):
    """Получение участника по tg_ID"""
    stmt = select(User).where(User.tg_id == tg_id)
    result = await db.execute(stmt)
    user = result.scalar()
    return user


async def add_to_daily_db(db: AsyncSession, tg_id: str) -> None:
    user = await get_user(db, tg_id=tg_id)
    db_daily = Daily(user_id=user.id, score=0)
    db.add(db_daily)
    await db.commit()
    await db.refresh(db_daily)


async def get_data(db: AsyncSession):  # возвращает список классов пользователей
    stmt = select(User)
    result = await db.execute(stmt)
    users = result.scalars().all()
    return users


async def get_tg_ids(db: AsyncSession):  # возвращает список тг_айди
    stmt = select(User.tg_id)
    result = await db.execute(stmt)
    tg_ids = result.scalars().all()
    return tg_ids


async def get_user_ids(db: AsyncSession):
    stmt = select(User.id)
    result = await db.execute(stmt)
    ids = result.scalars().all()
    return ids


async def delete_user(db: AsyncSession, tg_id: str) -> None:
    user = await get_user(db, tg_id=tg_id)
    await db.delete(user)
    await db.commit()


async def is_admin(db: AsyncSession, tg_id: str):
    user = await get_user(db, tg_id=tg_id)
    return True if user.is_admin else False


async def make_admin(db: AsyncSession, tg_id: str):
    user = await get_user(db, tg_id=tg_id)
    user.is_admin = True
    await db.commit()
    await db.refresh(user)


async def set_victim(db: AsyncSession, id_current, id_victim):
    user = await db.get(User, id_current)
    user.victim = id_victim
    await db.commit()
    await db.refresh(user)


async def list_filenames(directory_path: str) -> list[str]:
    """возвращает список названий файлов в указанной директории (без подпапок)."""
    loop = asyncio.get_running_loop()

    def _sync_list(dir_path: str) -> list[str]:
        return [
            name
            for name in os.listdir(dir_path)
            if os.path.isfile(os.path.join(dir_path, name))
        ]

    return await loop.run_in_executor(None, partial(_sync_list, directory_path))


async def shuffle_players(db: AsyncSession):
    users = await get_data(db)
    players = [user for user in users if not user.is_admin]
    filenames: list[str] = await list_filenames("./QR")
    if (len(players) < 2) or (len(filenames) < len(players)):
        return []
    print("!!! QR коды", filenames)
    random.shuffle(filenames)
    random.shuffle(players)
    players[0].qr_name = filenames[0]
    await db.commit()
    print(f"!!! user: {players[0].name} with tg_id: {players[0].tg_id} have qr name: {players[0].qr_name}")
    for i in range(1, len(players)):
        players[i].qr_name = filenames[i]
        await db.commit()
        print(f"!!! user: {players[i].name} with tg_id: {players[i].tg_id} have qr name: {players[i].qr_name}")

        await set_victim(db, players[i - 1].id, players[i].id)
        await make_alive(db, players[i].tg_id)

    await set_victim(db, players[-1].id, players[0].id)
    await make_alive(db, players[0].tg_id)
    return players


async def get_rating(db: AsyncSession):
    stmt = select(Daily)
    result = await db.execute(stmt)
    daily_users = result.scalars().all()

    admins_ids = await get_data(db)
    admins_ids = [user.id for user in admins_ids if user.is_admin]

    players = [player for player in daily_users if player.user_id not in admins_ids]
    players.sort(key=lambda x: x.score, reverse=True)
    return players


async def add_point(db: AsyncSession, id):
    rating = await get_rating(db)
    place, multiplier, prev_score = 0, 1, 0
    for i in range(len(rating)):
        if rating[i].user_id == id:
            prev_score = rating[i].score
            place = i + 1
    if place <= len(rating) / 3 and new_point_system:
        multiplier = 0.5
    elif place > 2 * len(rating) / 3 and new_point_system:
        multiplier = 1.5

    stmt = select(Daily).where(Daily.user_id == id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    user.score = int(prev_score + multiplier)
    await db.commit()
    await db.refresh(user)


async def is_dead(db: AsyncSession, tg_id: str):
    user = await get_user(db, tg_id=tg_id)
    return True if user.dead else False


async def make_dead(db: AsyncSession, tg_id: str):
    user = await get_user(db, tg_id=tg_id)
    user.dead = True
    await db.commit()
    await db.refresh(user)


async def make_alive(db: AsyncSession, tg_id: str):
    user = await get_user(db, tg_id=tg_id)
    user.dead = False
    await db.commit()
    await db.refresh(user)


async def get_alive(db: AsyncSession):
    users = await get_data(db)
    data = [user for user in users if (not user.dead) and (not user.is_admin)]
    return data


async def get_killer(db: AsyncSession, id):
    stmt = select(User).where(User.victim == id)
    result = await db.execute(stmt)
    return result.scalar()


async def get_user_by_id(db: AsyncSession, bd_id: str):
    result = await db.get(User, int(bd_id))
    return result


async def create_db():
    db_url = 'sqlite+aiosqlite:///db/database.db'
    engine: AsyncEngine = create_async_engine(db_url, echo=True, future=True)
    async_session_local = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await create_tables(engine)

    # async with async_session_local() as session:
    #     # await register_user(session, 'tg_id', "Artem", 'photo_id')
    #     print('!')
    #     print(await get_data(session))

    return async_session_local


if __name__ == "__main__":
    asyncio.run(create_db())
