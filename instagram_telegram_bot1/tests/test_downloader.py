import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from downloader import YtDlpDownloader, classify_error
from errors import (AccessRestrictedError, ContentNotFoundError, DownloadFailedError, DownloadTimeoutError,
                    FileTooLargeError, NetworkProblemError, NoVideoError, PrivateContentError, UnsupportedURLError)

MB = 1024 * 1024


class Classify(unittest.TestCase):
    def test_mapping(self):
        cases = {
            "ERROR: [Instagram] X: There is no video in this post": NoVideoError,
            "ERROR: [Instagram] X: This account is private": PrivateContentError,
            "Requested content is not available, rate-limit reached or login required": AccessRestrictedError,
            "Instagram sent an empty media response. Check cookies": AccessRestrictedError,
            "HTTP Error 429: Too Many Requests": AccessRestrictedError,
            "Unable to download webpage: HTTP Error 404: Not Found": ContentNotFoundError,
            "This video has been removed": ContentNotFoundError,
            "Unsupported URL: https://x": UnsupportedURLError,
            "Unable to download webpage: <urlopen error [Errno -2] Name or service not known>": NetworkProblemError,
            "The read operation timed out": NetworkProblemError,
            "\x1b[0;31mERROR:\x1b[0m something weird": DownloadFailedError,
        }
        for msg, cls in cases.items():
            with self.subTest(msg=msg):
                self.assertIsInstance(classify_error(msg), cls)


class FakeYoutubeDLError(Exception):
    pass


def install_fake_yt_dlp(behavior):
    """sys.modules ichiga soxta yt_dlp qo'yadi (haqiqiy tarmoq/kutubxona kerak emas)."""
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            return behavior(self.opts, url)

    utils = types.ModuleType("yt_dlp.utils")
    utils.YoutubeDLError = FakeYoutubeDLError
    pkg = types.ModuleType("yt_dlp")
    pkg.YoutubeDL = FakeYDL
    pkg.utils = utils
    return mock.patch.dict(sys.modules, {"yt_dlp": pkg, "yt_dlp.utils": utils})


class DownloaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.cancel = threading.Event()
        self.dl = YtDlpDownloader(max_bytes=5 * MB, ffmpeg_available=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_dl(self, behavior):
        with install_fake_yt_dlp(behavior):
            return self.dl.download("https://www.instagram.com/reel/C1a2B3c4D5e/", self.out, self.cancel)

    def test_success(self):
        def behavior(opts, url):
            f = self.out / "C1a2B3c4D5e.mp4"
            f.write_bytes(b"v" * 2048)
            opts["progress_hooks"][0]({"status": "downloading", "filename": str(f), "total_bytes": 2048})
            return {"title": "T", "duration": 7.5, "width": 720, "height": 1280,
                    "requested_downloads": [{"filepath": str(f)}]}
        v = self.run_dl(behavior)
        self.assertEqual((v.size_bytes, v.duration, v.width, v.height), (2048, 7, 720, 1280))

    def test_options_safe(self):
        seen = {}
        def behavior(opts, url):
            seen.update(opts, url_=url)
            (self.out / "a.mp4").write_bytes(b"1")
            return {}
        self.run_dl(behavior)
        self.assertEqual(seen["url_"], "https://www.instagram.com/reel/C1a2B3c4D5e/")
        self.assertTrue(seen["outtmpl"].startswith(str(self.out)))
        self.assertIn("socket_timeout", seen)
        self.assertNotIn("cookiefile", seen)

    def test_error_mapping(self):
        def behavior(opts, url):
            raise FakeYoutubeDLError("ERROR: [Instagram] X: This account is private")
        with self.assertRaises(PrivateContentError):
            self.run_dl(behavior)

    def test_unexpected_exception(self):
        def behavior(opts, url):
            raise RuntimeError("boom")
        with self.assertRaises(DownloadFailedError):
            self.run_dl(behavior)

    def test_too_large_via_hook(self):
        def behavior(opts, url):
            opts["progress_hooks"][0]({"status": "downloading", "filename": "a", "total_bytes": 50 * MB})
            raise AssertionError("hook to'xtatishi kerak edi")
        with self.assertRaises(FileTooLargeError):
            self.run_dl(behavior)

    def test_too_large_sum_of_streams(self):
        def behavior(opts, url):
            hook = opts["progress_hooks"][0]
            hook({"status": "finished", "filename": "v", "total_bytes": 3 * MB})
            hook({"status": "downloading", "filename": "a", "total_bytes": 3 * MB})
        with self.assertRaises(FileTooLargeError):
            self.run_dl(behavior)

    def test_too_large_after_download(self):
        def behavior(opts, url):
            f = self.out / "big.mp4"
            f.write_bytes(b"0" * (6 * MB))
            return {"requested_downloads": [{"filepath": str(f)}]}
        with self.assertRaises(FileTooLargeError):
            self.run_dl(behavior)

    def test_cancel(self):
        self.cancel.set()
        def behavior(opts, url):
            opts["progress_hooks"][0]({"status": "downloading", "filename": "a", "total_bytes": 1})
        with self.assertRaises(DownloadTimeoutError):
            self.run_dl(behavior)

    def test_no_file(self):
        with self.assertRaises(DownloadFailedError):
            self.run_dl(lambda o, u: {"title": "x"})

    def test_empty_playlist(self):
        with self.assertRaises(NoVideoError):
            self.run_dl(lambda o, u: {"entries": []})

    def test_playlist_first_entry(self):
        def behavior(opts, url):
            f = self.out / "e.mp4"
            f.write_bytes(b"z" * 10)
            return {"entries": [None, {"requested_downloads": [{"filepath": str(f)}], "width": 1, "height": 2}]}
        self.assertEqual(self.run_dl(behavior).size_bytes, 10)

    def test_cookies_copied_not_original(self):
        src = self.out / "orig_cookies.txt"
        src.write_text("# Netscape HTTP Cookie File\n")
        job = self.out / "job"
        job.mkdir()
        dl = YtDlpDownloader(max_bytes=MB, cookies_file=src, ffmpeg_available=False)
        seen = {}
        def behavior(opts, url):
            seen.update(opts)
            (job / "a.mp4").write_bytes(b"1")
            return {}
        with install_fake_yt_dlp(behavior):
            dl.download("u", job, self.cancel)
        self.assertEqual(Path(seen["cookiefile"]).parent, job)
        self.assertEqual(seen["format"], "b[ext=mp4]/b")


if __name__ == "__main__":
    unittest.main()
