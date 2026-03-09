from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    team_photo: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    destroyed_target_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="team", foreign_keys="User.team_id")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    course: Mapped[int] = mapped_column(Integer, nullable=False)
    face_photo: Mapped[str] = mapped_column(String(256), nullable=False)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    game_mode: Mapped[str] = mapped_column(String(16), nullable=False)  # "classic" / "team"
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reject_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)

    is_alive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    victim_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    qr_code_text = mapped_column(String, unique=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    team: Mapped[Optional["Team"]] = relationship(back_populates="users", foreign_keys=[team_id])


class Kill(Base):
    __tablename__ = "kills"

    id = mapped_column(Integer, primary_key=True)
    killer_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    victim_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    photo_file_id = mapped_column(String, nullable=True)
    qr_text = mapped_column(String, nullable=True)
    mode = mapped_column(String, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    killer = relationship("User", foreign_keys=[killer_id])
    victim = relationship("User", foreign_keys=[victim_id])