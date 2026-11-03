"""Yuklash xizmati: bir vaqtdagi yuklashlar, navbat, limit, timeout va tozalash."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

from downloader import DownloadedVideo, VideoDownloader
from errors import DownloadTimeoutError, RateLimitedError, ServerBusyError, UserBusyError
from services.file_manager import TempDirManager
from services.url_validator import ParsedURL

logger = logging.getLogger(__name__)


class DownloadService:
    """Yuklashni boshqaradi.

    * Global limit: bir vaqtda `max_concurrent` ta yuklash (semaphore).
    * Navbat: kutayotganlar `max_queue` dan oshsa so'rov rad etiladi.
    * Har bir foydalanuvchi bir vaqtda faqat bitta so'rov yubora oladi.
    * Foydalanuvchi uchun so'rovlar orasida `cooldown` soniya.
    * Vaqtinchalik papka har doim (xato bo'lsa ham) o'chiriladi.
    """

    def __init__(
        self,
        *,
        downloader: VideoDownloader,
        files: TempDirManager,
        max_concurrent: int,
        timeout: float,
        cooldown: float = 0,
        max_queue: int = 20,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._downloader = downloader
        self._files = files
        self._timeout = timeout
        self._cooldown = cooldown
        self._max_queue = max_queue
        self._clock = clock
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent + 2, thread_name_prefix="download")
        self._active_users: set[int] = set()
        self._last_request: dict[int, float] = {}
        self._waiting = 0

    # -- limitlar ----------------------------------------------------------
    def _check_limits(self, user_id: int) -> None:
        if user_id in self._active_users:
            raise UserBusyError()
        now = self._clock()
        last = self._last_request.get(user_id)
        if last is not None and self._cooldown > 0 and now - last < self._cooldown:
            raise RateLimitedError(self._cooldown - (now - last))
        if self._semaphore.locked() and self._waiting >= self._max_queue:
            raise ServerBusyError()
        self._last_request[user_id] = now
        if len(self._last_request) > 5000:  # xotira o'sib ketmasligi uchun
            horizon = now - max(self._cooldown, 1) * 2
            self._last_request = {u: t for u, t in self._last_request.items() if t >= horizon}

    # -- asosiy API --------------------------------------------------------
    @asynccontextmanager
    async def download(self, user_id: int, parsed: ParsedURL) -> AsyncIterator[DownloadedVideo]:
        """`async with service.download(...) as video:` - blok tugagach fayllar o'chiriladi."""
        self._check_limits(user_id)
        self._active_users.add(user_id)
        job_dir = None
        try:
            job_dir = await asyncio.to_thread(self._files.create_job_dir)
            self._waiting += 1
            try:
                await self._semaphore.acquire()
            finally:
                self._waiting -= 1
            try:
                video = await self._run(parsed.url, job_dir)
            finally:
                self._semaphore.release()
            yield video
        finally:
            self._active_users.discard(user_id)
            if job_dir is not None:
                await asyncio.shield(asyncio.to_thread(self._files.cleanup, job_dir))

    async def _run(self, url: str, job_dir) -> DownloadedVideo:
        loop = asyncio.get_running_loop()
        cancel_event = threading.Event()
        future = loop.run_in_executor(self._executor, self._downloader.download, url, job_dir, cancel_event)
        try:
            return await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            cancel_event.set()
            logger.warning("Yuklash vaqt limitidan oshdi (%ss)", self._timeout)
            raise DownloadTimeoutError() from None
        except asyncio.CancelledError:
            cancel_event.set()
            raise

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
