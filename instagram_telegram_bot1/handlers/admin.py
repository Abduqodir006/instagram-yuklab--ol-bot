"""Administrator buyruqlari: ommaviy xabar (/broadcast)."""
import html
import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from config import Settings
from database import Database
from handlers import texts
from services.broadcast import BroadcastManager, BroadcastPlan, run_broadcast

logger = logging.getLogger(__name__)
router = Router(name="admin")


def _is_admin(message: Message, settings: Settings) -> bool:
    user = message.from_user
    return user is not None and user.id in settings.admin_ids


@router.message(Command("broadcast"))
async def cmd_broadcast(
    message: Message,
    command: CommandObject,
    bot: Bot,
    db: Database,
    settings: Settings,
    broadcasts: BroadcastManager,
) -> None:
    if not _is_admin(message, settings):
        await message.answer(texts.ADMIN_ONLY)
        return
    if broadcasts.running:
        await message.answer(texts.BROADCAST_BUSY)
        return

    reply = getattr(message, "reply_to_message", None)
    text = (command.args or "").strip()
    if reply is not None:
        plan = BroadcastPlan(kind="copy", from_chat_id=message.chat.id, message_id=reply.message_id)
    elif text:
        plan = BroadcastPlan(kind="text", text=text)
    else:
        await message.answer(texts.BROADCAST_USAGE)
        return

    recipients = await db.get_broadcast_recipients()
    if not recipients:
        await message.answer(texts.BROADCAST_NO_RECIPIENTS)
        return

    # Admin xabarni avval o'zi ko'rib chiqadi.
    try:
        if plan.kind == "copy":
            await bot.copy_message(chat_id=message.chat.id, from_chat_id=plan.from_chat_id, message_id=plan.message_id)
        else:
            await bot.send_message(chat_id=message.chat.id, text=html.escape(plan.text))
    except TelegramAPIError as exc:
        logger.warning("Broadcast preview xatosi: %s", exc)
        await message.answer(texts.BROADCAST_PREVIEW_FAILED)
        return

    broadcasts.prepare(message.from_user.id, plan)
    await message.answer(texts.broadcast_confirm(len(recipients), broadcasts.ttl_minutes))


@router.message(Command("cancel_broadcast"))
async def cmd_cancel_broadcast(message: Message, settings: Settings, broadcasts: BroadcastManager) -> None:
    if not _is_admin(message, settings):
        await message.answer(texts.ADMIN_ONLY)
        return
    broadcasts.cancel(message.from_user.id)
    await message.answer(texts.BROADCAST_CANCELLED)


@router.message(Command("confirm_broadcast"))
async def cmd_confirm_broadcast(
    message: Message,
    bot: Bot,
    db: Database,
    settings: Settings,
    broadcasts: BroadcastManager,
) -> None:
    if not _is_admin(message, settings):
        await message.answer(texts.ADMIN_ONLY)
        return
    if broadcasts.running:
        await message.answer(texts.BROADCAST_BUSY)
        return
    plan = broadcasts.take(message.from_user.id)
    if plan is None:
        await message.answer(texts.BROADCAST_NOTHING_PENDING)
        return

    broadcasts.running = True
    try:
        recipients = await db.get_broadcast_recipients()
        await message.answer(texts.BROADCAST_STARTED)

        if plan.kind == "copy":
            async def send_one(user_id: int):
                return await bot.copy_message(
                    chat_id=user_id, from_chat_id=plan.from_chat_id, message_id=plan.message_id
                )
        else:
            safe_text = html.escape(plan.text or "")

            async def send_one(user_id: int):
                return await bot.send_message(chat_id=user_id, text=safe_text)

        result = await run_broadcast(recipients, send_one, on_blocked=db.mark_blocked)
    finally:
        broadcasts.running = False

    await message.answer(texts.broadcast_report(result.total, result.sent, result.blocked, result.failed))
