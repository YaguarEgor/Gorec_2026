from __future__ import annotations

import io
import re
from pathlib import Path

from aiogram import Bot


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


async def download_telegram_file_bytes(bot: Bot, file_id: str) -> bytes:
    telegram_file = await bot.get_file(file_id)

    buffer = io.BytesIO()
    await bot.download_file(telegram_file.file_path, destination=buffer)

    return buffer.getvalue()


def sanitize_filename_part(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r'[<>:"/\\|?*\n\r\t]+', "", text)
    text = text.strip(" .")
    return text or "unknown"


def build_kill_photo_path(
    base_dir: str | Path,
    killer_name: str,
    victim_name: str,
    ext: str = "jpg",
) -> Path:
    base = ensure_dir(base_dir)

    killer_part = sanitize_filename_part(killer_name)
    victim_part = sanitize_filename_part(victim_name)

    filename = f"{killer_part}__{victim_part}.{ext}"
    return base / filename


def save_bytes_to_file(data: bytes, path: str | Path) -> None:
    Path(path).write_bytes(data)