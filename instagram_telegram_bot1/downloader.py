"""yt-dlp asosidagi yuklovchi.

Bu modul *sinxron*: chaqiruvchi (DownloadService) uni alohida thread'da ishga
tushiradi. yt-dlp faqat shu yerda import qilinadi (kechiktirilgan import), shuning
uchun uning yo'qligi boshqa modullarni buzmaydi va testlarda almashtirish oson.

Cheklovlar:
  * Login, CAPTCHA va yopiq profillar aylanib o'tilmaydi - aniq xatolik qaytariladi.
  * Instagram tizimini tez-tez o'zgartiradi, shuning uchun yt-dlp'ni muntazam
    yangilab turish kerak (`pip install -U yt-dlp`).
"""
from __future__ import annotations

import logging
import re
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from errors import (
    AccessRestrictedError,
    BotError,
    ContentNotFoundError,
    DownloadFailedError,
    DownloadTimeoutError,
    FileTooLargeError,
    NetworkProblemError,
    NoVideoError,
    PrivateContentError,
    UnsupportedURLError,
)

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v", ".webm", ".mkv"})
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# FFmpeg bor bo'lsa alohida video+audio oqimlarini birlashtirish mumkin.
_FORMAT_WITH_FFMPEG = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
_FORMAT_WITHOUT_FFMPEG = "b[ext=mp4]/b"


@dataclass(frozen=True)
class DownloadedVideo:
    path: Path
    size_bytes: int
    title: str | None = None
    duration: int | None = None
    width: int | None = None
    height: int | None = None


class VideoDownloader(Protocol):
    def download(self, url: str, out_dir: Path, cancel_event: threading.Event) -> DownloadedVideo:
        ...


# --------------------------------------------------------------------------
# Xatoliklarni tasniflash
# --------------------------------------------------------------------------
def classify_error(message: str, *, limit_mb: int = 50) -> BotError:
    """yt-dlp xabarini mos BotError'ga aylantiradi (tartib muhim)."""
    text = _ANSI_RE.sub("", message or "").strip()
    low = text.lower()
    detail = text[:300]

    def has(*needles: str) -> bool:
        return any(needle in low for needle in needles)

    if has("there is no video in this post", "no video formats found", "no video could be found"):
        return NoVideoError(detail)
    if has("private", "follow this account"):
        return PrivateContentError(detail)
    if has(
        "rate-limit", "rate limit", "login required", "log in", "logged in", "login",
        "empty media response", "checkpoint", "challenge", "captcha", "too many requests",
        "http error 429", "http error 401", "http error 403", "registered users",
        "cookies", "geo restrict", "not available in your country",
    ):
        return AccessRestrictedError(detail)
    if has(
        "http error 404", "not found", "has been removed", "was deleted", "deleted",
        "does not exist", "unavailable", "no longer available", "isn't available",
    ):
        return ContentNotFoundError(detail)
    if has("unsupported url"):
        return UnsupportedURLError(detail)
    if has(
        "timed out", "timeout", "connection", "name or service not known",
        "temporary failure", "unable to download webpage", "network is unreachable",
        "urlopen error", "getaddrinfo", "remote end closed", "ssl", "http error 5",
    ):
        return NetworkProblemError(detail)
    return DownloadFailedError(detail or "Noma'lum yuklash xatosi")


# --------------------------------------------------------------------------
# Yordamchi sinflar
# --------------------------------------------------------------------------
class _Aborted(Exception):
    """Progress hook ichidan yuklashni to'xtatish uchun."""


class _ProgressState:
    """yt-dlp progress hook: hajm limiti va bekor qilish (timeout) nazorati."""

    def __init__(self, max_bytes: int, cancel_event: threading.Event) -> None:
        self.max_bytes = max_bytes
        self.cancel_event = cancel_event
        self.totals: dict[str, int] = {}
        self.too_large = False
        self.cancelled = False

    def __call__(self, data: dict[str, Any]) -> None:
        if self.cancel_event.is_set():
            self.cancelled = True
            raise _Aborted("bekor qilindi")
        if data.get("status") not in ("downloading", "finished"):
            return
        name = str(data.get("filename") or data.get("tmpfilename") or "?")
        total = data.get("total_bytes") or data.get("total_bytes_estimate") or data.get("downloaded_bytes") or 0
        try:
            self.totals[name] = int(total)
        except (TypeError, ValueError):
            return
        if sum(self.totals.values()) > self.max_bytes:
            self.too_large = True
            raise _Aborted("fayl hajmi limitdan katta")


class _YtDlpLogger:
    """yt-dlp xabarlarini bizning logga yo'naltiradi (debug shovqinini o'chirib)."""

    def debug(self, msg: str) -> None:  # noqa: D401
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        logger.warning("yt-dlp: %s", _ANSI_RE.sub("", str(msg))[:300])

    def error(self, msg: str) -> None:
        logger.warning("yt-dlp xato: %s", _ANSI_RE.sub("", str(msg))[:300])


def _as_positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if value > 0 else None


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except (ValueError, OSError):
        return False


def _import_yt_dlp() -> tuple[Any, Any]:
    try:
        import yt_dlp
        from yt_dlp import utils as yt_utils
    except ImportError as exc:  # pragma: no cover - o'rnatish xatosi
        raise DownloadFailedError("yt-dlp o'rnatilmagan (pip install yt-dlp)") from exc
    return yt_dlp, yt_utils


# --------------------------------------------------------------------------
# Asosiy yuklovchi
# --------------------------------------------------------------------------
class YtDlpDownloader:
    def __init__(
        self,
        *,
        max_bytes: int,
        socket_timeout: int = 20,
        cookies_file: Path | None = None,
        ffmpeg_available: bool | None = None,
    ) -> None:
        self._max_bytes = max_bytes
        self._limit_mb = max(1, max_bytes // (1024 * 1024))
        self._socket_timeout = socket_timeout
        self._cookies_file = cookies_file
        self._ffmpeg = shutil.which("ffmpeg") is not None if ffmpeg_available is None else ffmpeg_available
        if not self._ffmpeg:
            logger.warning("FFmpeg topilmadi: faqat tayyor (birlashtirilgan) formatlar yuklanadi.")

    # -- sozlamalar --------------------------------------------------------
    def _build_options(self, out_dir: Path, state: _ProgressState) -> dict[str, Any]:
        options: dict[str, Any] = {
            "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
            "format": _FORMAT_WITH_FFMPEG if self._ffmpeg else _FORMAT_WITHOUT_FFMPEG,
            "merge_output_format": "mp4",
            "playlist_items": "1",          # karusel postlarda faqat birinchi element
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "no_color": True,
            "logger": _YtDlpLogger(),
            "progress_hooks": [state],
            "socket_timeout": self._socket_timeout,
            "retries": 2,
            "fragment_retries": 2,
            "extractor_retries": 1,
            "concurrent_fragment_downloads": 1,
            "restrictfilenames": True,
            "overwrites": True,
            "cachedir": False,
            "updatetime": False,
            "ignoreerrors": False,
        }
        if self._cookies_file is not None:
            # Cookie faylining nusxasi ish papkasiga olinadi: yt-dlp uni qayta yozishi
            # mumkin va bir vaqtdagi yuklashlar asl faylni buzmasligi kerak.
            local_copy = out_dir / "cookies.txt"
            shutil.copyfile(self._cookies_file, local_copy)
            options["cookiefile"] = str(local_copy)
        return options

    # -- yuklash -----------------------------------------------------------
    def download(self, url: str, out_dir: Path, cancel_event: threading.Event) -> DownloadedVideo:
        yt_dlp, yt_utils = _import_yt_dlp()
        out_dir = Path(out_dir)
        state = _ProgressState(self._max_bytes, cancel_event)

        try:
            options = self._build_options(out_dir, state)
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as exc:  # noqa: BLE001 - quyida tasniflanadi
            if state.too_large:
                raise FileTooLargeError(self._limit_mb) from exc
            if state.cancelled:
                raise DownloadTimeoutError() from exc
            if isinstance(exc, BotError):
                raise
            if isinstance(exc, getattr(yt_utils, "YoutubeDLError", Exception)):
                raise classify_error(str(exc), limit_mb=self._limit_mb) from exc
            raise DownloadFailedError(f"Kutilmagan xato: {exc!r}") from exc

        return self._build_result(info, out_dir)

    def _build_result(self, info: Any, out_dir: Path) -> DownloadedVideo:
        if not isinstance(info, dict):
            raise DownloadFailedError("yt-dlp natija qaytarmadi")
        entries = info.get("entries")
        if entries is not None:
            first = next((entry for entry in entries if entry), None)
            if first is None:
                raise NoVideoError("Postda video elementi yo'q")
            info = first

        path = self._locate_file(info, out_dir)
        if path is None:
            raise DownloadFailedError("Yuklangan fayl topilmadi")
        size = path.stat().st_size
        if size <= 0:
            raise DownloadFailedError("Yuklangan fayl bo'sh")
        if size > self._max_bytes:
            raise FileTooLargeError(self._limit_mb)

        title = info.get("title")
        return DownloadedVideo(
            path=path,
            size_bytes=size,
            title=str(title)[:200] if title else None,
            duration=_as_positive_int(info.get("duration")),
            width=_as_positive_int(info.get("width")),
            height=_as_positive_int(info.get("height")),
        )

    @staticmethod
    def _locate_file(info: dict[str, Any], out_dir: Path) -> Path | None:
        candidates: list[Path] = []
        for item in info.get("requested_downloads") or []:
            filepath = item.get("filepath") or item.get("_filename")
            if filepath:
                candidates.append(Path(filepath))
        if info.get("filepath"):
            candidates.append(Path(info["filepath"]))
        for candidate in candidates:
            if candidate.is_file() and _is_within(candidate, out_dir):
                return candidate

        files = [p for p in out_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
        return max(files, key=lambda p: p.stat().st_size) if files else None
