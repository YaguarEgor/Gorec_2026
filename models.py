from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, Boolean, ForeignKey


class Base(AsyncAttrs, DeclarativeBase):
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class User(Base):
    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(128))
    photo: Mapped[str] = mapped_column(String(300))  # TODO: сколько символов выделить
    tg_id: Mapped[str] = mapped_column(String(128))

    qr_name: Mapped[str] = mapped_column(String(128))
    victim: Mapped[int] = mapped_column(Integer)
    is_admin: Mapped[bool] = mapped_column(Boolean)
    dead: Mapped[bool] = mapped_column(Boolean)


class Daily(Base): 
    __tablename__ = "daily"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    score: Mapped[int] = mapped_column(Integer)
