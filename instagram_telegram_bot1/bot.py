"""Botni ishga tushirish nuqtasi:  python bot.py"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from config import ConfigError, load_settings
from database import Database
from downloader import YtDlpDownloader
from handlers import register_handlers
from logging_setup import setup_logging
from services.broadcast import BroadcastManager
from services.download_service import DownloadService
from services.file_manager import TempDirManager

logger = logging.getLogger("bot")


async def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Sozlama xatosi: {exc}", file=sys.stderr)
        return 2

    setup_logging(settings.log_file, settings.log_level, secrets=[settings.bot_token])

    db = Database(settings.db_path)
    await db.init()

    files = TempDirManager(settings.temp_dir)
    files.cleanup_all()  # oldingi ishga tushishdan qolgan fayllar

    downloader = YtDlpDownloader(
        max_bytes=settings.max_file_size_bytes,
        socket_timeout=settings.socket_timeout,
        cookies_file=settings.cookies_file,
    )
    download_service = DownloadService(
        downloader=downloader,
        files=files,
        max_concurrent=settings.max_concurrent_downloads,
        timeout=settings.download_timeout,
        cooldown=settings.user_cooldown_seconds,
        max_queue=settings.max_queue_size,
    )

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.workflow_data.update(
        settings=settings, db=db, download_service=download_service, broadcasts=BroadcastManager()
    )
    register_handlers(dp)

    cleanup_task = None
    try:
        try:
            me = await bot.get_me()
        except TelegramAPIError as exc:
            logger.error("Telegramga ulanib bo'lmadi (token noto'g'ri bo'lishi mumkin): %s", exc)
            return 1
        logger.info("Bot ishga tushdi: @%s", me.username)

        cleanup_task = asyncio.create_task(
            files.run_periodic_cleanup(600, settings.stale_temp_minutes * 60)
        )
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if cleanup_task:
            cleanup_task.cancel()
        download_service.shutdown()
        await bot.session.close()
        logger.info("Bot to'xtatildi")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except (KeyboardInterrupt, SystemExit):
        pass
