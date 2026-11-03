"""Telegram handlerlar."""
from aiogram import Dispatcher


def register_handlers(dp: Dispatcher) -> None:
    # Tartib muhim: buyruqlar avval, umumiy matn handleri oxirida.
    from handlers import admin, download, start

    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(download.router)
