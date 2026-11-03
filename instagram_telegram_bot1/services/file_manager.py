"""Vaqtinchalik fayllar: yaratish va xavfsiz tozalash."""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class TempDirManager:
    """Har bir yuklash uchun alohida papka (`job_xxxx`) beradi va uni tozalaydi.

    Tozalash faqat `base_dir` ichidagi `job_` bilan boshlanuvchi papkalarga
    ta'sir qiladi - tasodifan boshqa joyni o'chirib yubormaslik uchun.
    """

    PREFIX = "job_"

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_job_dir(self) -> Path:
        return Path(tempfile.mkdtemp(prefix=self.PREFIX, dir=self.base_dir))

    def _is_managed(self, path: Path) -> bool:
        try:
            resolved = Path(path).resolve()
        except OSError:
            return False
        return resolved.parent == self.base_dir and resolved.name.startswith(self.PREFIX)

    def cleanup(self, path: Path, attempts: int = 3) -> bool:
        """Papkani o'chiradi. Muvaffaqiyatli bo'lsa (yoki papka yo'q bo'lsa) True."""
        path = Path(path)
        if not self._is_managed(path):
            logger.error("Tozalashdan bosh tortildi: boshqariladigan papka emas (%s)", path.name)
            return False
        for attempt in range(1, attempts + 1):
            if not path.exists():
                return True
            try:
                shutil.rmtree(path)
                return True
            except OSError as exc:
                # Windows'da fayl bir zum band bo'lishi mumkin.
                logger.warning("Papkani o'chirib bo'lmadi (urinish %d/%d): %s", attempt, attempts, exc)
                time.sleep(0.2 * attempt)
        return not path.exists()

    @staticmethod
    def _newest_mtime(path: Path) -> float:
        newest = path.stat().st_mtime
        try:
            for child in path.iterdir():
                try:
                    newest = max(newest, child.stat().st_mtime)
                except OSError:
                    continue
        except OSError:
            pass
        return newest

    def cleanup_stale(self, max_age_seconds: float) -> int:
        """`max_age_seconds` dan eski papkalarni o'chiradi; o'chirilganlar sonini qaytaradi."""
        removed = 0
        now = time.time()
        try:
            entries = list(self.base_dir.iterdir())
        except OSError:
            return 0
        for entry in entries:
            if not entry.is_dir() or not entry.name.startswith(self.PREFIX):
                continue
            try:
                age = now - self._newest_mtime(entry)
            except OSError:
                continue
            if age > max_age_seconds and self.cleanup(entry):
                removed += 1
        if removed:
            logger.info("Eskirgan vaqtinchalik papkalar o'chirildi: %d", removed)
        return removed

    def cleanup_all(self) -> int:
        """Barcha job papkalarini o'chiradi (faqat bot ishga tushganda chaqiriladi)."""
        return self.cleanup_stale(-1)

    async def run_periodic_cleanup(self, interval_seconds: float, max_age_seconds: float) -> None:
        """Orqa fonda vaqti-vaqti bilan eski papkalarni tozalab turadi."""
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await asyncio.to_thread(self.cleanup_stale, max_age_seconds)
            except Exception:  # noqa: BLE001 - fon vazifasi yiqilmasligi kerak
                logger.exception("Davriy tozalashda xatolik")
