"""Sender va handlerlar testi. aiogram o'rnatilmagan bo'lsa stub ishlatiladi."""
from tests import aiogram_stub

aiogram_stub.install_if_missing()

import asyncio  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest import mock  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

from aiogram.exceptions import (TelegramAPIError, TelegramBadRequest, TelegramForbiddenError,  # noqa: E402
                                TelegramNetworkError, TelegramRetryAfter)

from config import load_settings  # noqa: E402
from database import Database  # noqa: E402
from downloader import DownloadedVideo  # noqa: E402
from errors import (AccessRestrictedError, TelegramTooLargeError, UploadFailedError,  # noqa: E402
                    UserBlockedBotError)
from handlers import download as dl_handler  # noqa: E402
from handlers import start as start_handler  # noqa: E402
from services import sender  # noqa: E402
from services.download_service import DownloadService  # noqa: E402
from services.file_manager import TempDirManager  # noqa: E402
from tests.helpers import VALID_TOKEN, FakeDownloader  # noqa: E402

URL = "https://www.instagram.com/reel/C1a2B3c4D5e/"


def video(tmp):
    p = Path(tmp) / "v.mp4"
    p.write_bytes(b"x" * 10)
    return DownloadedVideo(path=p, size_bytes=10, duration=3, width=1, height=2)


class SenderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmpd = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpd.cleanup)
        self.video = video(self.tmpd.name)
        patcher = mock.patch.object(sender.asyncio, "sleep", new=AsyncMock())
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    async def send(self, bot):
        await sender.send_video(bot, 1, self.video, caption="c", upload_timeout=10, limit_mb=50)

    async def test_success(self):
        bot = SimpleNamespace(send_video=AsyncMock(), send_document=AsyncMock())
        await self.send(bot)
        bot.send_video.assert_awaited_once()
        self.assertEqual(bot.send_video.await_args.kwargs["request_timeout"], 10)

    async def test_non_mp4_sent_as_document(self):
        self.video = DownloadedVideo(path=self.video.path.rename(self.video.path.with_suffix(".webm")), size_bytes=10)
        bot = SimpleNamespace(send_video=AsyncMock(), send_document=AsyncMock())
        await self.send(bot)
        bot.send_document.assert_awaited_once()
        bot.send_video.assert_not_awaited()

    async def test_retry_after_then_ok(self):
        bot = SimpleNamespace(send_video=AsyncMock(side_effect=[
            TelegramRetryAfter(method=None, message="flood", retry_after=3), None]))
        await self.send(bot)
        self.assertEqual(bot.send_video.await_count, 2)
        self.sleep.assert_awaited_with(3)

    async def test_retry_after_exhausted(self):
        err = TelegramRetryAfter(method=None, message="flood", retry_after=1)
        bot = SimpleNamespace(send_video=AsyncMock(side_effect=err))
        with self.assertRaises(UploadFailedError):
            await self.send(bot)
        self.assertEqual(bot.send_video.await_count, 3)

    async def test_network_error_retried_once(self):
        bot = SimpleNamespace(send_video=AsyncMock(side_effect=TelegramNetworkError(method=None, message="net")))
        with self.assertRaises(UploadFailedError):
            await self.send(bot)
        self.assertEqual(bot.send_video.await_count, 2)

    async def test_too_large(self):
        bot = SimpleNamespace(send_video=AsyncMock(
            side_effect=TelegramBadRequest(method=None, message="Request Entity Too Large")))
        with self.assertRaises(TelegramTooLargeError):
            await self.send(bot)
        self.assertEqual(bot.send_video.await_count, 1)

    async def test_forbidden(self):
        bot = SimpleNamespace(send_video=AsyncMock(
            side_effect=TelegramForbiddenError(method=None, message="bot was blocked")))
        with self.assertRaises(UserBlockedBotError):
            await self.send(bot)

    async def test_bad_request_other(self):
        bot = SimpleNamespace(send_video=AsyncMock(side_effect=TelegramBadRequest(method=None, message="wrong")))
        with self.assertRaises(UploadFailedError):
            await self.send(bot)

    async def test_missing_file(self):
        self.video.path.unlink()
        bot = SimpleNamespace(send_video=AsyncMock(side_effect=FileNotFoundError("gone")))
        with self.assertRaises(UploadFailedError):
            await self.send(bot)


def make_message(text, uid=1):
    status = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
    msg = SimpleNamespace(
        text=text, chat=SimpleNamespace(id=uid),
        from_user=SimpleNamespace(id=uid, username="u", first_name="Ali <b>"),
        answer=AsyncMock(return_value=status),
    )
    return msg, status


class HandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmpd = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpd.cleanup)
        root = Path(self.tmpd.name)
        self.settings = load_settings({"BOT_TOKEN": VALID_TOKEN, "ADMIN_IDS": "99"}, base_dir=root)
        self.db = Database(root / "bot.db")
        await self.db.init()
        self.files = TempDirManager(root / "tmp")
        self.bot = SimpleNamespace(
            send_video=AsyncMock(), send_document=AsyncMock(), send_chat_action=AsyncMock(),
            me=AsyncMock(return_value=SimpleNamespace(username="testbot")))

    def service(self, dl):
        svc = DownloadService(downloader=dl, files=self.files, max_concurrent=2, timeout=5, cooldown=0)
        self.addCleanup(svc.shutdown)
        return svc

    async def call(self, text, dl=None, uid=1):
        msg, status = make_message(text, uid)
        svc = self.service(dl or FakeDownloader())
        await dl_handler.handle_text(msg, self.bot, self.settings, self.db, svc)
        return msg, status

    def tmp_clean(self):
        return list((Path(self.tmpd.name) / "tmp").iterdir()) == []

    async def test_no_url(self):
        msg, _ = await self.call("salom")
        self.assertIn("havolasini yuboring", msg.answer.await_args.args[0])
        self.bot.send_video.assert_not_awaited()

    async def test_unsupported_and_invalid(self):
        for text, expected in [("https://youtube.com/watch?v=abc12345", "qo'llab-quvvatlanmaydi"),
                               ("http://127.0.0.1/reel/C1a2B3c4D5e/", "qo'llab-quvvatlanmaydi"),
                               ("https://instagram.com@evil.com/reel/C1a2B3c4D5e/", "noto'g'ri")]:
            with self.subTest(text=text):
                dl = FakeDownloader()
                msg, _ = await self.call(text, dl)
                self.assertIn(expected, msg.answer.await_args.args[0])
                self.assertEqual(dl.calls, 0)

    async def test_success_flow(self):
        dl = FakeDownloader()
        msg, status = await self.call(f"Mana {URL}", dl)
        self.bot.send_video.assert_awaited_once()
        self.assertEqual(dl.calls, 1)
        status.delete.assert_awaited_once()
        self.assertTrue(self.tmp_clean())
        stats = await self.db.get_stats()
        self.assertEqual((stats["successful_downloads"], stats["failed_downloads"]), (1, 0))
        self.assertEqual(stats["total_bytes"], 1024)

    async def test_download_error_message(self):
        msg, status = await self.call(URL, FakeDownloader(error=AccessRestrictedError("login")))
        status.edit_text.assert_awaited_with(AccessRestrictedError.user_message)
        self.bot.send_video.assert_not_awaited()
        self.assertTrue(self.tmp_clean())
        self.assertEqual((await self.db.get_stats())["top_errors"], [("AccessRestrictedError", 1)])

    async def test_telegram_upload_error(self):
        self.bot.send_video = AsyncMock(side_effect=TelegramBadRequest(method=None, message="Request Entity Too Large"))
        msg, status = await self.call(URL)
        self.assertIn("katta", status.edit_text.await_args.args[0])
        self.assertTrue(self.tmp_clean())
        self.assertEqual((await self.db.get_stats())["failed_downloads"], 1)

    async def test_telegram_generic_error(self):
        self.bot.send_video = AsyncMock(side_effect=TelegramBadRequest(method=None, message="nope"))
        msg, status = await self.call(URL)
        self.assertEqual(status.edit_text.await_args.args[0], UploadFailedError.user_message)
        self.assertTrue(self.tmp_clean())

    async def test_unexpected_error(self):
        msg, status = await self.call(URL, FakeDownloader(error=ZeroDivisionError("bug")))
        self.assertIn("Kutilmagan", status.edit_text.await_args.args[0])
        self.assertTrue(self.tmp_clean())

    async def test_blocked_user_silent(self):
        self.bot.send_video = AsyncMock(side_effect=TelegramForbiddenError(method=None, message="blocked"))
        msg, status = await self.call(URL)
        self.assertTrue(self.tmp_clean())

    async def test_parallel_users(self):
        dl = FakeDownloader(delay=0.1)
        svc = self.service(dl)
        msgs = [make_message(URL, uid) for uid in range(1, 7)]
        await asyncio.gather(*(dl_handler.handle_text(m, self.bot, self.settings, self.db, svc) for m, _ in msgs))
        self.assertEqual(self.bot.send_video.await_count, 6)
        self.assertLessEqual(dl.max_seen, 2)
        self.assertTrue(self.tmp_clean())

    async def test_same_user_second_request_rejected(self):
        dl = FakeDownloader(delay=0.2)
        svc = self.service(dl)
        m1, _ = make_message(URL)
        m2, s2 = make_message(URL)
        t = asyncio.create_task(dl_handler.handle_text(m1, self.bot, self.settings, self.db, svc))
        await asyncio.sleep(0.05)
        await dl_handler.handle_text(m2, self.bot, self.settings, self.db, svc)
        await t
        self.assertIn("hali bajarilmoqda", s2.edit_text.await_args.args[0])
        self.assertEqual(dl.calls, 1)
        self.assertEqual((await self.db.get_stats())["failed_downloads"], 0)

    async def test_commands_and_stats(self):
        msg, _ = make_message("/start")
        await start_handler.cmd_start(msg, self.db)
        self.assertIn("&lt;b&gt;", msg.answer.await_args.args[0])  # HTML escape
        msg, _ = make_message("/help")
        await start_handler.cmd_help(msg, self.db, self.settings)
        self.assertIn("50 MB", msg.answer.await_args.args[0])
        msg, _ = make_message("/about")
        await start_handler.cmd_about(msg, self.db)
        msg, _ = make_message("/stats", uid=5)
        await start_handler.cmd_stats(msg, self.db, self.settings)
        self.assertIn("faqat administratorlar", msg.answer.await_args.args[0])
        msg, _ = make_message("/stats", uid=99)
        await start_handler.cmd_stats(msg, self.db, self.settings)
        self.assertIn("Statistika", msg.answer.await_args.args[0])


class ImportSmoke(unittest.TestCase):
    def test_bot_module_imports(self):
        import bot
        self.assertTrue(callable(bot.main))


if __name__ == "__main__":
    unittest.main()
