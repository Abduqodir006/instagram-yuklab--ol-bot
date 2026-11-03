"""Log sozlamalari: faylga yozish (rotatsiya bilan) va maxfiy ma'lumotlarni yashirish."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

_TOKEN_PATTERN = re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}")
_MARK = "_igbot_handler"


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Matndagi bot tokeni va berilgan maxfiy qiymatlarni yashiradi."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return _TOKEN_PATTERN.sub("<token>", text)


class RedactingFormatter(logging.Formatter):
    """Yakuniy log qatori (traceback bilan) maxfiy ma'lumotdan tozalanadi."""

    def __init__(self, fmt: str, datefmt: str | None = None, secrets: Iterable[str] = ()) -> None:
        super().__init__(fmt, datefmt)
        self._secrets = tuple(secrets)

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record), self._secrets)


def setup_logging(log_file: Path, level: str = "INFO", secrets: Iterable[str] = ()) -> None:
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, _MARK, False):
            root.removeHandler(handler)
            handler.close()

    formatter = RedactingFormatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", secrets=tuple(secrets)
    )
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    console_handler = logging.StreamHandler()
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
        setattr(handler, _MARK, True)
        root.addHandler(handler)

    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
