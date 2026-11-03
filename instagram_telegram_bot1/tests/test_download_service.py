import asyncio
import tempfile
import unittest
from pathlib import Path

from errors import (DownloadFailedError, DownloadTimeoutError, FileTooLargeError, RateLimitedError,
                    ServerBusyError, UserBusyError)
from services.download_service import DownloadService
from services.file_manager import TempDirManager
from services.url_validator import ParsedURL
from tests.helpers import FakeDownloader

PARSED = ParsedURL(url="https://www.instagram.com/reel/C1a2B3c4D5e/", kind="reel", shortcode="C1a2B3c4D5e")


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.files = TempDirManager(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, dl, **kw):
        params = dict(downloader=dl, files=self.files, max_concurrent=2, timeout=5, cooldown=0, max_queue=20)
        params.update(kw)
        svc = DownloadService(**params)
        self.addCleanup(svc.shutdown)
        return svc

    def leftovers(self):
        return [p for p in Path(self.tmp.name).iterdir()]

    async def test_success_and_cleanup(self):
        dl = FakeDownloader()
        svc = self.make(dl)
        async with svc.download(1, PARSED) as video:
            self.assertTrue(video.path.exists())
            path = video.path
        self.assertFalse(path.exists())
        self.assertEqual(self.leftovers(), [])

    async def test_cleanup_when_body_fails(self):
        svc = self.make(FakeDownloader())
        with self.assertRaises(RuntimeError):
            async with svc.download(1, PARSED):
                raise RuntimeError("Telegramga yuborishda xato")
        self.assertEqual(self.leftovers(), [])

    async def test_download_error_cleanup(self):
        svc = self.make(FakeDownloader(error=DownloadFailedError("x")))
        with self.assertRaises(DownloadFailedError):
            async with svc.download(1, PARSED):
                pass
        self.assertEqual(self.leftovers(), [])

    async def test_file_too_large_propagates(self):
        svc = self.make(FakeDownloader(error=FileTooLargeError(50)))
        with self.assertRaises(FileTooLargeError):
            async with svc.download(1, PARSED):
                pass
        self.assertEqual(self.leftovers(), [])

    async def test_concurrent_limit(self):
        dl = FakeDownloader(delay=0.15)
        svc = self.make(dl, max_concurrent=2)

        async def one(uid):
            async with svc.download(uid, PARSED):
                return uid

        results = await asyncio.gather(*(one(i) for i in range(6)))
        self.assertEqual(sorted(results), list(range(6)))
        self.assertEqual(dl.calls, 6)
        self.assertLessEqual(dl.max_seen, 2)
        self.assertEqual(dl.max_seen, 2)
        self.assertEqual(self.leftovers(), [])

    async def test_same_user_busy(self):
        svc = self.make(FakeDownloader(delay=0.2))
        async def first():
            async with svc.download(7, PARSED):
                pass
        task = asyncio.create_task(first())
        await asyncio.sleep(0.05)
        with self.assertRaises(UserBusyError):
            async with svc.download(7, PARSED):
                pass
        await task
        async with svc.download(7, PARSED):  # tugagach yana mumkin
            pass

    async def test_cooldown(self):
        now = [100.0]
        svc = self.make(FakeDownloader(), cooldown=5, clock=lambda: now[0])
        async with svc.download(1, PARSED):
            pass
        with self.assertRaises(RateLimitedError) as ctx:
            async with svc.download(1, PARSED):
                pass
        self.assertEqual(ctx.exception.wait_seconds, 5)
        now[0] += 6
        async with svc.download(1, PARSED):
            pass

    async def test_queue_full(self):
        svc = self.make(FakeDownloader(delay=0.3), max_concurrent=1, max_queue=1)
        async def run(uid):
            async with svc.download(uid, PARSED):
                pass
        t1 = asyncio.create_task(run(1))
        await asyncio.sleep(0.05)     # 1-chi semaforni oldi
        t2 = asyncio.create_task(run(2))
        await asyncio.sleep(0.05)     # 2-chi navbatda
        with self.assertRaises(ServerBusyError):
            await run(3)
        await asyncio.gather(t1, t2)

    async def test_timeout(self):
        dl = FakeDownloader(block_until_cancel=True)
        svc = self.make(dl, timeout=0.2)
        with self.assertRaises(DownloadTimeoutError):
            async with svc.download(1, PARSED):
                pass
        await asyncio.sleep(0.1)
        self.assertEqual(self.leftovers(), [])


if __name__ == "__main__":
    unittest.main()
