"""Instagram havolalarini qabul qilish va videoni yuborish."""
import logging
import time

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from config import Settings
from database import Database
from errors import BotError, RequestRejectedError, UserBlockedBotError
from handlers import texts
from services.download_service import DownloadService
from services.sender import send_video
from services.url_validator import extract_first_url, validate_instagram_url

logger = logging.getLogger(__name__)
router = Router(name="download")


async def _safe_edit(status: Message | None, text: str) -> None:
    if status is None:
        return
    try:
        await status.edit_text(text)
    except TelegramAPIError as exc:
        logger.debug("Holat xabarini tahrirlab bo'lmadi: %s", exc)


async def _safe_delete(status: Message | None) -> None:
    if status is None:
        return
    try:
        await status.delete()
    except TelegramAPIError as exc:
        logger.debug("Holat xabarini o'chirib bo'lmadi: %s", exc)


async def _record(db: Database, **kwargs) -> None:
    try:
        await db.record_download(**kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("Statistikani yozib bo'lmadi")


@router.message(F.text)
async def handle_text(
    message: Message,
    bot: Bot,
    settings: Settings,
    db: Database,
    download_service: DownloadService,
) -> None:
    user = message.from_user
    if user is None or not message.text:
        return

    try:
        await db.upsert_user(user.id, user.username, user.first_name)
    except Exception:  # noqa: BLE001
        logger.exception("Foydalanuvchini bazaga yozib bo'lmadi")

    raw_url = extract_first_url(message.text)
    if raw_url is None:
        await message.answer(texts.NO_URL)
        return

    try:
        parsed = validate_instagram_url(raw_url)
    except BotError as exc:
        logger.info("URL rad etildi (user=%s): %s", user.id, type(exc).__name__)
        await message.answer(exc.user_message)
        return

    status = await message.answer(texts.DOWNLOADING)
    started = time.monotonic()
    size_bytes = None
    try:
        async with download_service.download(user.id, parsed) as video:
            size_bytes = video.size_bytes
            await _safe_edit(status, texts.UPLOADING)
            try:
                await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)
            except TelegramAPIError:
                pass
            try:
                me = await bot.me()
                username = me.username
            except Exception:  # noqa: BLE001
                username = None
            await send_video(
                bot,
                message.chat.id,
                video,
                caption=texts.caption(username),
                upload_timeout=settings.upload_timeout,
                limit_mb=settings.max_file_size_mb,
            )
    except RequestRejectedError as exc:
        await _safe_edit(status, exc.user_message)
        return
    except UserBlockedBotError:
        logger.info("Foydalanuvchi botni bloklagan (user=%s)", user.id)
        await _record(
            db, user_id=user.id, shortcode=parsed.shortcode, kind=parsed.kind,
            success=False, error_type="UserBlockedBotError",
        )
        return
    except BotError as exc:
        logger.warning("Yuklash xatosi (user=%s, %s): %s", user.id, parsed.shortcode, type(exc).__name__)
        await _record(
            db, user_id=user.id, shortcode=parsed.shortcode, kind=parsed.kind,
            success=False, error_type=type(exc).__name__,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        await _safe_edit(status, exc.user_message)
        return
    except Exception:  # noqa: BLE001
        logger.exception("Kutilmagan xatolik (user=%s, %s)", user.id, parsed.shortcode)
        await _record(
            db, user_id=user.id, shortcode=parsed.shortcode, kind=parsed.kind,
            success=False, error_type="UnexpectedError",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        await _safe_edit(status, texts.UNEXPECTED)
        return

    await _record(
        db, user_id=user.id, shortcode=parsed.shortcode, kind=parsed.kind, success=True,
        file_size=size_bytes, duration_ms=int((time.monotonic() - started) * 1000),
    )
    await _safe_delete(status)
