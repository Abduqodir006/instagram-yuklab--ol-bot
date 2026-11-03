"""Instagram havolalarini ajratib olish va xavfsiz tekshirish.

SSRF himoyasi: foydalanuvchi yuborgan havola hech qachon to'g'ridan-to'g'ri
yuklovchiga berilmaydi. Faqat ruxsat etilgan Instagram domenlari qabul qilinadi
va yuklovchiga havola *qayta quriladi* (`https://www.instagram.com/<tur>/<kod>/`).
IP manzillar, localhost, ichki domenlar, `user@host` ko'rinishlari va boshqa
domenlar shu bosqichda rad etiladi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from errors import InvalidURLError, UnsupportedURLError

ALLOWED_HOSTS = frozenset({"instagram.com", "www.instagram.com", "m.instagram.com"})
MAX_URL_LENGTH = 2048

# Matn ichidan havolani topish: http(s)://... yoki sxemasiz instagram.com/...
_URL_RE = re.compile(
    r"""(?:https?://|(?<![\w@./-])(?:www\.|m\.)?instagram\.com/)[^\s<>"'`]+""",
    re.IGNORECASE,
)
# /<username>/(p|reel|reels|tv)/<kod>/ yoki /(p|reel|reels|tv)/<kod>/
_PATH_RE = re.compile(
    r"^/(?:[A-Za-z0-9._]{1,30}/)?(?P<kind>p|reel|reels|tv)/(?P<code>[A-Za-z0-9_-]{5,40})/?$"
)
_TRAILING_PUNCTUATION = ".,;:!?)]}>'\"»"


@dataclass(frozen=True)
class ParsedURL:
    """Tekshirilgan va normallashtirilgan Instagram havolasi."""

    url: str        # yuklovchiga beriladigan toza havola
    kind: str       # "reel" | "p" | "tv"
    shortcode: str


def extract_first_url(text: str | None) -> str | None:
    """Matndagi birinchi havolani qaytaradi (bo'lmasa None)."""
    if not text:
        return None
    match = _URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(_TRAILING_PUNCTUATION) or None


def validate_instagram_url(raw: str) -> ParsedURL:
    """Havolani tekshiradi.

    Raises:
        InvalidURLError: havola buzuq (sxema, port, login/parol, noto'g'ri belgilar).
        UnsupportedURLError: havola to'g'ri, lekin Instagram post/reel/tv emas.
    """
    candidate = (raw or "").strip()
    if not candidate or len(candidate) > MAX_URL_LENGTH:
        raise InvalidURLError("Bo'sh yoki juda uzun havola")
    if any(ch.isspace() or ord(ch) < 32 for ch in candidate):
        raise InvalidURLError("Havolada ruxsat etilmagan belgilar bor")
    if "://" not in candidate:
        candidate = "https://" + candidate

    try:
        parts = urlsplit(candidate)
        port = parts.port
    except ValueError as exc:
        raise InvalidURLError(f"Havolani o'qib bo'lmadi: {exc}") from exc

    if parts.scheme.lower() not in ("http", "https"):
        raise InvalidURLError("Faqat http/https havolalar qabul qilinadi")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise InvalidURLError("Havolada login/parol bo'lishi mumkin emas")

    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise InvalidURLError("Havolada domen yo'q")
    if host not in ALLOWED_HOSTS:
        raise UnsupportedURLError(f"Qo'llab-quvvatlanmaydigan domen: {host}")
    if port not in (None, 80, 443):
        raise InvalidURLError("Nostandart port ruxsat etilmaydi")

    match = _PATH_RE.match(parts.path)
    if not match:
        raise UnsupportedURLError("Havola post, reel yoki tv emas")

    kind = "reel" if match.group("kind") in ("reel", "reels") else match.group("kind")
    code = match.group("code")
    return ParsedURL(url=f"https://www.instagram.com/{kind}/{code}/", kind=kind, shortcode=code)
