"""Ommaviy xabar yuborish (admin): tezlik limiti, bloklanganlarni belgilash, hisobot."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

logger = logging.getLogger(__name__)

PENDING_TTL_SECONDS = 300
# Telegram chegarasi ~30 xabar/soniya; 20/s xavfsiz.
DEFAULT_DELAY = 0.05
_BLOCKED_MARKERS = ("chat not found", "user is deactivated", "bot was blocked", "blocked by the user")


@dataclass(frozen=True)
class BroadcastPlan:
    kind: str                       # "copy" (reply qilingan xabarni nusxalash) | "text"
    text: str | None = None
    from_chat_id: int | None = None
    message_id: int | None = None


@dataclass(frozen=True)
class BroadcastResult:
    total: int
    sent: int
    blocked: int
    failed: int


class BroadcastManager:
    """Kutayotgan rejalar (admin tasdig'ini kutayotgan) va "bir vaqtda bitta" qulfi."""

    def __init__(self, ttl: float = PENDING_TTL_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl
        self._clock = clock
        self._pending: dict[int, tuple[BroadcastPlan, float]] = {}
        self.running = False

    @property
    def ttl_minutes(self) -> int:
        return max(1, int(self._ttl // 60))

    def prepare(self, admin_id: int, plan: BroadcastPlan) -> None:
        self._pending[admin_id] = (plan, self._clock())

    def take(self, admin_id: int) -> BroadcastPlan | None:
        item = self._pending.pop(admin_id, None)
        if item is None:
            return None
        plan, created = item
        return plan if self._clock() - created <= self._ttl else None

    def cancel(self, admin_id: int) -> bool:
        return self._pending.pop(admin_id, None) is not None


async def _deliver(user_id: int, send_one: Callable[[int], Awaitable[object]], sleep) -> str:
    for attempt in range(2):
        try:
            await send_one(user_id)
            return "sent"
        except TelegramForbiddenError:
            return "blocked"
        except TelegramRetryAfter as exc:
            if attempt == 0:
                wait = min(max(int(getattr(exc, "retry_after", 1)), 1), 30)
                logger.warning("Broadcast: flood limit, %s soniya kutiladi", wait)
                await sleep(wait)
                continue
            return "failed"
        except TelegramAPIError as exc:
            if any(marker in str(exc).lower() for marker in _BLOCKED_MARKERS):
                return "blocked"
            logger.warning("Broadcast: user=%s xato: %s", user_id, exc)
            return "failed"
        except Exception:  # noqa: BLE001
            logger.exception("Broadcast: kutilmagan xato (user=%s)", user_id)
            return "failed"
    return "failed"


async def run_broadcast(
    recipients: Iterable[int],
    send_one: Callable[[int], Awaitable[object]],
    *,
    on_blocked: Callable[[int], Awaitable[object]] | None = None,
    delay: float = DEFAULT_DELAY,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> BroadcastResult:
    """Xabarni ketma-ket, tezlik limiti bilan yuboradi."""
    counts = {"sent": 0, "blocked": 0, "failed": 0}
    total = 0
    for user_id in recipients:
        total += 1
        status = await _deliver(user_id, send_one, sleep)
        counts[status] += 1
        if status == "blocked" and on_blocked is not None:
            try:
                await on_blocked(user_id)
            except Exception:  # noqa: BLE001
                logger.exception("Bloklangan foydalanuvchini belgilab bo'lmadi")
        if delay:
            await sleep(delay)
    logger.info("Broadcast tugadi: %s", {**counts, "total": total})
    return BroadcastResult(total=total, **counts)
