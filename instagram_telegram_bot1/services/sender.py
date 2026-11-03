"""Videoni Telegramga yuborish va Telegram API xatoliklarini qayta ishlash."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import FSInputFile

from downloader import DownloadedVideo
from errors import TelegramTooLargeError, UploadFailedError, UserBlockedBotError

logger = logging.getLogger(__name__)

_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}
_TOO_LARGE_MARKERS = ("too large", "too big", "entity too large", "file is too big")
MAX_RETRY_AFTER_SECONDS = 30


def _looks_too_large(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TOO_LARGE_MARKERS)


async def send_video(
    bot: Any,
    chat_id: int,
    video: DownloadedVideo,
    *,
    caption: str | None,
    upload_timeout: int,
    limit_mb: int = 50,
    max_retries: int = 2,
) -> None:
    """Videoni yuboradi.

    * Flood-limit (RetryAfter) bo'lsa kutib, qayta urinadi.
    * Tarmoq xatosida bir marta qayta urinadi.
    * Fayl katta bo'lsa `TelegramTooLargeError`, foydalanuvchi botni bloklagan
      bo'lsa `UserBlockedBotError`, boshqa holatlarda `UploadFailedError` ko'taradi.
    """
    input_file = FSInputFile(video.path, filename=video.path.name)
    as_video = video.path.suffix.lower() in _VIDEO_SUFFIXES
    retries_left = max_retries
    network_retry_used = False

    while True:
        try:
            if as_video:
                await bot.send_video(
                    chat_id=chat_id,
                    video=input_file,
                    caption=caption,
                    duration=video.duration,
                    width=video.width,
                    height=video.height,
                    supports_streaming=True,
                    request_timeout=upload_timeout,
                )
            else:
                await bot.send_document(
                    chat_id=chat_id,
                    document=input_file,
                    caption=caption,
                    request_timeout=upload_timeout,
                )
            return
        except TelegramForbiddenError as exc:
            raise UserBlockedBotError("Foydalanuvchi botni bloklagan yoki chatga ruxsat yo'q") from exc
        except TelegramAPIError as exc:
            if _looks_too_large(exc):
                raise TelegramTooLargeError(limit_mb) from exc
            if isinstance(exc, TelegramRetryAfter) and retries_left > 0:
                retries_left -= 1
                delay = min(max(int(getattr(exc, "retry_after", 1)), 1), MAX_RETRY_AFTER_SECONDS)
                logger.warning("Telegram flood limit: %s soniya kutiladi", delay)
                await asyncio.sleep(delay)
                continue
            if isinstance(exc, TelegramNetworkError) and not network_retry_used:
                network_retry_used = True
                logger.warning("Telegram tarmoq xatosi, qayta uriniladi: %s", exc)
                await asyncio.sleep(2)
                continue
            logger.error("Telegram videoni qabul qilmadi: %s", exc)
            raise UploadFailedError(str(exc)) from exc
        except OSError as exc:
            logger.error("Faylni o'qib bo'lmadi: %s", exc)
            raise UploadFailedError(f"Fayl xatosi: {exc}") from exc
