"""/start, /help, /about va administratorlar uchun /stats."""
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import Settings
from database import Database
from handlers import texts

import logging

logger = logging.getLogger(__name__)
router = Router(name="start")


async def _register_user(message: Message, db: Database) -> None:
    user = message.from_user
    if user is None:
        return
    try:
        await db.upsert_user(user.id, user.username, user.first_name)
    except Exception:  # noqa: BLE001 - statistika xatosi botni to'xtatmasin
        logger.exception("Foydalanuvchini bazaga yozib bo'lmadi")


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    await _register_user(message, db)
    first_name = message.from_user.first_name if message.from_user else None
    await message.answer(texts.start_text(first_name))


@router.message(Command("help"))
async def cmd_help(message: Message, db: Database, settings: Settings) -> None:
    await _register_user(message, db)
    await message.answer(texts.help_text(settings.max_file_size_mb))


@router.message(Command("about"))
async def cmd_about(message: Message, db: Database) -> None:
    await _register_user(message, db)
    await message.answer(texts.about_text())


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database, settings: Settings) -> None:
    user = message.from_user
    if user is None or user.id not in settings.admin_ids:
        await message.answer(texts.ADMIN_ONLY)
        return
    stats = await db.get_stats()
    await message.answer(texts.stats_text(stats))
