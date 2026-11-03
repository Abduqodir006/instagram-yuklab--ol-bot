import unittest

from errors import InvalidURLError, UnsupportedURLError
from services.url_validator import extract_first_url, validate_instagram_url


class ValidUrls(unittest.TestCase):
    def test_reel_post_tv(self):
        for kind, url in [
            ("reel", "https://www.instagram.com/reel/C1a2B3c4D5e/"),
            ("p", "https://www.instagram.com/p/C1a2B3c4D5e/"),
            ("tv", "https://www.instagram.com/tv/C1a2B3c4D5e/"),
        ]:
            parsed = validate_instagram_url(url)
            self.assertEqual(parsed.kind, kind)
            self.assertEqual(parsed.shortcode, "C1a2B3c4D5e")
            self.assertEqual(parsed.url, f"https://www.instagram.com/{kind}/C1a2B3c4D5e/")

    def test_normalization(self):
        cases = [
            "https://instagram.com/reel/C1a2B3c4D5e",
            "http://m.instagram.com/reel/C1a2B3c4D5e/?igsh=abc&utm_source=qr",
            "https://www.instagram.com/some.user_1/reel/C1a2B3c4D5e/#frag",
            "https://www.instagram.com/reels/C1a2B3c4D5e/",
            "instagram.com/reel/C1a2B3c4D5e/",
            "HTTPS://WWW.INSTAGRAM.COM/reel/C1a2B3c4D5e/",
        ]
        for url in cases:
            with self.subTest(url=url):
                self.assertEqual(validate_instagram_url(url).url, "https://www.instagram.com/reel/C1a2B3c4D5e/")


class InvalidUrls(unittest.TestCase):
    def test_invalid(self):
        for url in ["", "   ", "http://", "https://", "ftp://instagram.com/reel/C1a2B3c4D5e/",
                    "https://instagram.com@evil.com/reel/C1a2B3c4D5e/",
                    "https://user:pw@www.instagram.com/reel/C1a2B3c4D5e/",
                    "https://www.instagram.com:8080/reel/C1a2B3c4D5e/",
                    "javascript:alert(1)", "https://insta gram.com/reel/abc", "https://[::1/",
                    "https://www.instagram.com/reel/C1a2B3c4D5e/" + "a" * 3000]:
            with self.subTest(url=url[:50]):
                with self.assertRaises(InvalidURLError):
                    validate_instagram_url(url)


class UnsupportedUrls(unittest.TestCase):
    def test_unsupported(self):
        for url in ["https://www.youtube.com/watch?v=abc12345", "https://www.instagram.com/someuser/",
                    "https://www.instagram.com/stories/user/123456789/", "https://www.instagram.com/explore/",
                    "https://www.instagram.com/reel/ab/", "https://www.instagram.com/reel/%2e%2e/",
                    "https://www.instagram.com/reel/C1a2B3c4D5e/extra/"]:
            with self.subTest(url=url):
                with self.assertRaises(UnsupportedURLError):
                    validate_instagram_url(url)


class SsrfUrls(unittest.TestCase):
    def test_ssrf_blocked(self):
        for url in [
            "http://127.0.0.1/reel/C1a2B3c4D5e/", "http://localhost/reel/C1a2B3c4D5e/",
            "http://169.254.169.254/latest/meta-data/", "http://[::1]/reel/C1a2B3c4D5e/",
            "http://2130706433/reel/C1a2B3c4D5e/", "http://10.0.0.5/p/C1a2B3c4D5e/",
            "https://instagram.com.evil.com/reel/C1a2B3c4D5e/",
            "https://evil.com/instagram.com/reel/C1a2B3c4D5e/",
            "https://notinstagram.com/reel/C1a2B3c4D5e/",
            "https://evil.com/?u=https://www.instagram.com/reel/C1a2B3c4D5e/",
        ]:
            with self.subTest(url=url):
                with self.assertRaises((InvalidURLError, UnsupportedURLError)):
                    validate_instagram_url(url)


class Extraction(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(extract_first_url("Mana: https://www.instagram.com/reel/C1a2B3c4D5e/?igsh=1, ko'ring!"),
                         "https://www.instagram.com/reel/C1a2B3c4D5e/?igsh=1")
        self.assertEqual(extract_first_url("(https://www.instagram.com/p/C1a2B3c4D5e/)"),
                         "https://www.instagram.com/p/C1a2B3c4D5e/")
        self.assertEqual(extract_first_url("qarang instagram.com/reel/C1a2B3c4D5e/"),
                         "instagram.com/reel/C1a2B3c4D5e/")
        self.assertIsNone(extract_first_url("salom"))
        self.assertIsNone(extract_first_url(None))
        self.assertIsNone(extract_first_url("notinstagram.com/reel/C1a2B3c4D5e/"))

    def test_first_of_many(self):
        text = "https://youtu.be/abc12345 https://www.instagram.com/reel/C1a2B3c4D5e/"
        self.assertEqual(extract_first_url(text), "https://youtu.be/abc12345")


if __name__ == "__main__":
    unittest.main()
