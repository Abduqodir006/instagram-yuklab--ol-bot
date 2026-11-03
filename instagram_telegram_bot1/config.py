"""Bot sozlamalari: `.env` fayli va muhit o'zgaruvchilaridan o'qiladi."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

APP_NAME = "Instagram Video Yuklovchi Bot"
APP_VERSION = "1.0.0"
BASE_DIR = Path(__file__).resolve().parent

# Telegram bulutli Bot API orqali yuboriladigan fayl chegarasi.
TELEGRAM_UPLOAD_LIMIT_MB = 50

_TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


class ConfigError(Exception):
    """Sozlamalar noto'g'ri yoki yetishmayotgan."""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: tuple[int, ...]
    max_file_size_mb: int
    download_timeout: int
    upload_timeout: int
    max_concurrent_downloads: int
    max_queue_size: int
    user_cooldown_seconds: int
    socket_timeout: int
    stale_temp_minutes: int
    temp_dir: Path
    db_path: Path
    log_file: Path
    log_level: str
    cookies_file: Path | None

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


def _get_int(env: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} butun son bo'lishi kerak (hozir: {raw!r}).") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} {minimum} dan {maximum} gacha bo'lishi kerak (hozir: {value}).")
    return value


def _parse_admin_ids(raw: str) -> tuple[int, ...]:
    ids: list[int] = []
    for part in re.split(r"[,\s;]+", (raw or "").strip()):
        if not part:
            continue
        if not part.lstrip("-").isdigit():
            raise ConfigError(f"ADMIN_IDS ichida noto'g'ri qiymat: {part!r} (faqat Telegram ID raqamlari).")
        ids.append(int(part))
    return tuple(ids)


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base_dir / path).resolve()


def load_settings(env: Mapping[str, str] | None = None, *, base_dir: Path = BASE_DIR) -> Settings:
    """Sozlamalarni o'qiydi va tekshiradi. `env` berilmasa `.env` + os.environ ishlatiladi."""
    if env is None:
        load_dotenv(base_dir / ".env", override=False)
        env = os.environ

    token = (env.get("BOT_TOKEN") or "").strip()
    if not token:
        raise ConfigError(
            "BOT_TOKEN topilmadi. .env fayliga BOT_TOKEN=... qatorini yozing (tokenni @BotFather beradi)."
        )
    if not _TOKEN_RE.match(token):
        raise ConfigError("BOT_TOKEN formati noto'g'ri. U '123456789:AA...' ko'rinishida bo'lishi kerak.")

    log_level = (env.get("LOG_LEVEL") or "INFO").strip().upper()
    if log_level not in _LOG_LEVELS:
        raise ConfigError(f"LOG_LEVEL quyidagilardan biri bo'lishi kerak: {', '.join(sorted(_LOG_LEVELS))}.")

    cookies_raw = (env.get("YTDLP_COOKIES_FILE") or "").strip()
    cookies_file: Path | None = None
    if cookies_raw:
        cookies_file = _resolve_path(cookies_raw, base_dir)
        if not cookies_file.is_file():
            raise ConfigError(f"YTDLP_COOKIES_FILE topilmadi: {cookies_file}")

    return Settings(
        bot_token=token,
        admin_ids=_parse_admin_ids(env.get("ADMIN_IDS", "")),
        max_file_size_mb=_get_int(env, "MAX_FILE_SIZE_MB", 50, 1, TELEGRAM_UPLOAD_LIMIT_MB),
        download_timeout=_get_int(env, "DOWNLOAD_TIMEOUT", 120, 10, 1800),
        upload_timeout=_get_int(env, "UPLOAD_TIMEOUT", 300, 10, 3600),
        max_concurrent_downloads=_get_int(env, "MAX_CONCURRENT_DOWNLOADS", 3, 1, 32),
        max_queue_size=_get_int(env, "MAX_QUEUE_SIZE", 20, 0, 1000),
        user_cooldown_seconds=_get_int(env, "USER_COOLDOWN_SECONDS", 5, 0, 3600),
        socket_timeout=_get_int(env, "SOCKET_TIMEOUT", 20, 3, 120),
        stale_temp_minutes=_get_int(env, "STALE_TEMP_MINUTES", 30, 5, 1440),
        temp_dir=_resolve_path(env.get("TEMP_DIR") or "tmp_downloads", base_dir),
        db_path=_resolve_path(env.get("DB_PATH") or "data/bot.db", base_dir),
        log_file=_resolve_path(env.get("LOG_FILE") or "logs/bot.log", base_dir),
        log_level=log_level,
        cookies_file=cookies_file,
    )
