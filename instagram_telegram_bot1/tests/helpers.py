"""Testlar uchun umumiy yordamchilar."""
import threading
import time
from pathlib import Path

from downloader import DownloadedVideo

VALID_TOKEN = "123456789:" + "A" * 35


class FakeDownloader:
    """Haqiqiy tarmoqsiz yuklovchi: fayl yaratadi, parallellikni o'lchaydi."""

    def __init__(self, *, delay=0.0, size=1024, error=None, block_until_cancel=False, name="video.mp4"):
        self.delay, self.size, self.error, self.name = delay, size, error, name
        self.block_until_cancel = block_until_cancel
        self.calls = 0
        self.current = 0
        self.max_seen = 0
        self.dirs = []
        self._lock = threading.Lock()

    def download(self, url, out_dir, cancel_event):
        with self._lock:
            self.calls += 1
            self.current += 1
            self.max_seen = max(self.max_seen, self.current)
            self.dirs.append(Path(out_dir))
        try:
            if self.block_until_cancel:
                cancel_event.wait(3)
            elif self.delay:
                time.sleep(self.delay)
            if self.error:
                raise self.error
            path = Path(out_dir) / self.name
            path.write_bytes(b"x" * self.size)
            return DownloadedVideo(path=path, size_bytes=self.size, duration=5, width=720, height=1280)
        finally:
            with self._lock:
                self.current -= 1
