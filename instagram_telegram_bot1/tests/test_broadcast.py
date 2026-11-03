from tests import aiogram_stub

aiogram_stub.install_if_missing()

import sqlite3  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,  # noqa: E402
                                TelegramRetryAfter)

from config import load_settings  # noqa: E402
from database import Database  # noqa: E402
from handlers import admin  # noqa: E402
from services.broadcast import BroadcastManager, BroadcastPlan, run_broadcast  # noqa: E402
from tests.helpers import VALID_TOKEN  # noqa: E402


async def no_sleep(_):
    return None


class RunBroadcastTests(unittest.IsolatedAsyncioTestCase):
    async def test_counts_and_blocked_marking(self):
        marked = []

        async def send(uid):
            if uid == 2:
                raise TelegramForbiddenError(method=None, message="bot was blocked by the user")
            if uid == 3:
                raise TelegramBadRequest(method=None, message="Bad Request: chat not found")
            if uid == 4:
                raise TelegramBadRequest(method=None, message="something else")
            if uid == 5:
                raise RuntimeError("boom")

        async def on_blocked(uid):
            marked.append(uid)

        res = await run_broadcast([1, 2, 3, 4, 5, 6], send, on_blocked=on_blocked, sleep=no_sleep)
        self.assertEqual((res.total, res.sent, res.blocked, res.failed), (6, 2, 2, 2))
        self.assertEqual(marked, [2, 3])

    async def test_retry_after_then_success(self):
        calls = []

        async def send(uid):
            calls.append(uid)
            if len(calls) == 1:
                raise TelegramRetryAfter(method=None, message="flood", retry_after=2)

        sleeps = []

        async def sleep(s):
            sleeps.append(s)

        res = await run_broadcast([10], send, delay=0, sleep=sleep)
        self.assertEqual((res.sent, res.failed), (1, 0))
        self.assertEqual(calls, [10, 10])
        self.assertEqual(sleeps, [2])

    async def test_rate_limit_delay_applied(self):
        sleeps = []

        async def sleep(s):
            sleeps.append(s)

        await run_broadcast([1, 2, 3], AsyncMock(), delay=0.05, sleep=sleep)
        self.assertEqual(sleeps, [0.05, 0.05, 0.05])


class ManagerTests(unittest.TestCase):
    def test_pending_expiry_and_cancel(self):
        now = [0.0]
        m = BroadcastManager(ttl=300, clock=lambda: now[0])
        plan = BroadcastPlan(kind="text", text="x")
        m.prepare(1, plan)
        self.assertEqual(m.take(1), plan)
        self.assertIsNone(m.take(1))
        m.prepare(1, plan)
        now[0] = 301
        self.assertIsNone(m.take(1))
        m.prepare(1, plan)
        self.assertTrue(m.cancel(1))
        self.assertFalse(m.cancel(1))


def make_msg(uid, text="", reply_id=None):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=uid, username="u", first_name="A"),
        chat=SimpleNamespace(id=uid),
        reply_to_message=SimpleNamespace(message_id=reply_id) if reply_id else None,
        answer=AsyncMock(),
    )


class AdminHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.settings = load_settings({"BOT_TOKEN": VALID_TOKEN, "ADMIN_IDS": "99"}, base_dir=root)
        self.db = Database(root / "bot.db")
        await self.db.init()
        for uid in (99, 1, 2, 3):
            await self.db.upsert_user(uid, "u", "n")
        self.bot = SimpleNamespace(send_message=AsyncMock(), copy_message=AsyncMock())
        self.mgr = BroadcastManager()

    async def run_cmd(self, fn, msg, args=None):
        kwargs = dict(bot=self.bot, db=self.db, settings=self.settings, broadcasts=self.mgr)
        if fn is admin.cmd_broadcast:
            kwargs["command"] = SimpleNamespace(args=args)
        elif fn is admin.cmd_cancel_broadcast:
            kwargs = dict(settings=self.settings, broadcasts=self.mgr)
        await fn(msg, **kwargs)

    def last(self, msg):
        return msg.answer.await_args.args[0]

    async def test_non_admin_rejected(self):
        for fn in (admin.cmd_broadcast, admin.cmd_confirm_broadcast, admin.cmd_cancel_broadcast):
            msg = make_msg(5)
            await self.run_cmd(fn, msg, "salom")
            self.assertIn("faqat administratorlar", self.last(msg))
        self.bot.send_message.assert_not_awaited()

    async def test_usage_when_empty(self):
        msg = make_msg(99)
        await self.run_cmd(admin.cmd_broadcast, msg, None)
        self.assertIn("/broadcast", self.last(msg))

    async def test_text_flow_requires_confirmation(self):
        msg = make_msg(99)
        await self.run_cmd(admin.cmd_broadcast, msg, "Salom <b> hammaga")
        self.assertIn("4", self.last(msg))                      # 4 ta qabul qiluvchi
        self.assertEqual(self.bot.send_message.await_count, 1)  # faqat adminga preview
        msg2 = make_msg(99)
        await self.run_cmd(admin.cmd_confirm_broadcast, msg2)
        self.assertEqual(self.bot.send_message.await_count, 1 + 4)
        sent_texts = {c.kwargs["text"] for c in self.bot.send_message.await_args_list}
        self.assertEqual(sent_texts, {"Salom &lt;b&gt; hammaga"})  # HTML escape
        self.assertIn("Yuborildi: 4", self.last(msg2))
        self.assertFalse(self.mgr.running)

    async def test_copy_flow_and_blocked_users_marked(self):
        async def copy(chat_id, from_chat_id, message_id):
            if chat_id == 2:
                raise TelegramForbiddenError(method=None, message="blocked")
        self.bot.copy_message = AsyncMock(side_effect=copy)
        msg = make_msg(99, reply_id=777)
        await self.run_cmd(admin.cmd_broadcast, msg, None)
        msg2 = make_msg(99)
        await self.run_cmd(admin.cmd_confirm_broadcast, msg2)
        self.assertIn("Botni bloklagan: 1", self.last(msg2))
        self.assertEqual(await self.db.get_broadcast_recipients(), [1, 3, 99])
        self.assertEqual((await self.db.get_stats())["blocked_users"], 1)
        # foydalanuvchi qaytib yozsa, yana ro'yxatga qo'shiladi
        await self.db.upsert_user(2, "u", "n")
        self.assertEqual(await self.db.get_broadcast_recipients(), [1, 2, 3, 99])

    async def test_confirm_without_pending_and_cancel(self):
        msg = make_msg(99)
        await self.run_cmd(admin.cmd_confirm_broadcast, msg)
        self.assertIn("yo'q yoki muddati", self.last(msg))
        await self.run_cmd(admin.cmd_broadcast, make_msg(99), "x")
        await self.run_cmd(admin.cmd_cancel_broadcast, make_msg(99))
        msg2 = make_msg(99)
        await self.run_cmd(admin.cmd_confirm_broadcast, msg2)
        self.assertIn("yo'q yoki muddati", self.last(msg2))

    async def test_busy_rejected(self):
        self.mgr.running = True
        msg = make_msg(99)
        await self.run_cmd(admin.cmd_broadcast, msg, "x")
        self.assertIn("yuborilmoqda", self.last(msg))

    async def test_preview_failure(self):
        self.bot.send_message = AsyncMock(side_effect=TelegramBadRequest(method=None, message="x"))
        msg = make_msg(99)
        await self.run_cmd(admin.cmd_broadcast, msg, "x")
        self.assertIn("nusxalab bo'lmadi", self.last(msg))


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_db_gets_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, "
                         "first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, requests_count INTEGER NOT NULL DEFAULT 0)")
            conn.execute("INSERT INTO users VALUES (7,'a','b','2026-01-01 00:00:00','2026-01-01 00:00:00',3)")
            conn.commit()
            conn.close()
            db = Database(path)
            await db.init()
            self.assertEqual(await db.get_broadcast_recipients(), [7])
            await db.mark_blocked(7)
            self.assertEqual(await db.get_broadcast_recipients(), [])


if __name__ == "__main__":
    unittest.main()
