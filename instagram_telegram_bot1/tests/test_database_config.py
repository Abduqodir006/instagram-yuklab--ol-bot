import tempfile
import unittest
from pathlib import Path

from config import ConfigError, load_settings
from database import Database
from logging_setup import redact
from tests.helpers import VALID_TOKEN


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "sub" / "bot.db")
            await db.init()
            await db.upsert_user(1, "a", "Ali")
            await db.upsert_user(1, "a2", "Ali")
            await db.upsert_user(2, None, "Vali")
            await db.record_download(user_id=1, shortcode="abc12", kind="reel", success=True, file_size=2 * 1024 * 1024)
            await db.record_download(user_id=2, shortcode="abc13", kind="p", success=False, error_type="PrivateContentError")
            await db.record_download(user_id=2, shortcode=None, kind=None, success=False, error_type="PrivateContentError")
            s = await db.get_stats()
            self.assertEqual(s["total_users"], 2)
            self.assertEqual(s["active_users_today"], 2)
            self.assertEqual(s["new_users_today"], 2)
            self.assertEqual((s["total_downloads"], s["successful_downloads"], s["failed_downloads"]), (3, 1, 2))
            self.assertEqual(s["downloads_last_24h"], 3)
            self.assertEqual(s["total_bytes"], 2 * 1024 * 1024)
            self.assertEqual(s["top_errors"], [("PrivateContentError", 2)])

    async def test_concurrent_writes(self):
        import asyncio
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "bot.db")
            await db.init()
            await asyncio.gather(*(db.upsert_user(i % 5, "u", "n") for i in range(40)))
            self.assertEqual((await db.get_stats())["total_users"], 5)


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = load_settings({"BOT_TOKEN": VALID_TOKEN, "ADMIN_IDS": "1, 2;3"}, base_dir=Path(tmp))
            self.assertEqual(s.admin_ids, (1, 2, 3))
            self.assertEqual(s.max_file_size_bytes, 50 * 1024 * 1024)
            self.assertEqual(s.temp_dir, Path(tmp).resolve() / "tmp_downloads")
            self.assertIsNone(s.cookies_file)

    def test_errors(self):
        for env in [{}, {"BOT_TOKEN": "abc"}, {"BOT_TOKEN": VALID_TOKEN, "MAX_FILE_SIZE_MB": "500"},
                    {"BOT_TOKEN": VALID_TOKEN, "DOWNLOAD_TIMEOUT": "x"}, {"BOT_TOKEN": VALID_TOKEN, "ADMIN_IDS": "a"},
                    {"BOT_TOKEN": VALID_TOKEN, "LOG_LEVEL": "LOUD"},
                    {"BOT_TOKEN": VALID_TOKEN, "YTDLP_COOKIES_FILE": "nope.txt"}]:
            with self.subTest(env=env):
                with self.assertRaises(ConfigError):
                    load_settings(env, base_dir=Path("/tmp"))

    def test_redact(self):
        text = f"POST https://api.telegram.org/bot{VALID_TOKEN}/sendVideo failed"
        self.assertNotIn(VALID_TOKEN, redact(text))
        self.assertNotIn("sekret", redact("pw=sekret", ["sekret"]))


if __name__ == "__main__":
    unittest.main()
