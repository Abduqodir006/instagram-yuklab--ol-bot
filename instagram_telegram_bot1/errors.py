"""Loyiha bo'ylab ishlatiladigan xatoliklar.

Har bir xatolikda foydalanuvchiga ko'rsatiladigan tushunarli matn
(`user_message`) bor. Matnlar HTML parse_mode bilan xavfsiz (`<`, `&` yo'q).
"""
from __future__ import annotations

import math


class BotError(Exception):
    """Barcha bot xatoliklarining asosi."""

    user_message: str = "⚠️ Kutilmagan xatolik yuz berdi. Keyinroq qayta urinib ko'ring."

    def __init__(self, message: str | None = None, *, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(message or self.user_message)


# --- URL xatoliklari -------------------------------------------------------
class InvalidURLError(BotError):
    user_message = "❌ Havola noto'g'ri ko'rinadi. Instagram havolasini to'liq nusxalab yuboring."


class UnsupportedURLError(BotError):
    user_message = (
        "⚠️ Bu havola qo'llab-quvvatlanmaydi.\n"
        "Faqat Instagram Reel, post (/p/) va IGTV (/tv/) havolalarini yuboring."
    )


# --- So'rov rad etilishi (statistikaga xato sifatida yozilmaydi) ------------
class RequestRejectedError(BotError):
    """So'rov navbat/limit sabab qabul qilinmadi."""


class UserBusyError(RequestRejectedError):
    user_message = "⏳ Oldingi so'rovingiz hali bajarilmoqda. Iltimos, tugashini kuting."


class RateLimitedError(RequestRejectedError):
    def __init__(self, wait_seconds: float) -> None:
        self.wait_seconds = max(1, int(math.ceil(wait_seconds)))
        msg = f"🕒 Iltimos, biroz sekinroq. {self.wait_seconds} soniyadan keyin qayta urinib ko'ring."
        super().__init__(msg, user_message=msg)


class ServerBusyError(RequestRejectedError):
    user_message = "🚦 Hozir bot juda band. Bir ozdan keyin qayta urinib ko'ring."


# --- Yuklab olish xatoliklari ----------------------------------------------
class DownloaderError(BotError):
    """Videoni olish jarayonidagi xatoliklar."""


class ContentNotFoundError(DownloaderError):
    user_message = "🗑 Video topilmadi. Post o'chirilgan yoki havola noto'g'ri bo'lishi mumkin."


class PrivateContentError(DownloaderError):
    user_message = "🔒 Bu post yopiq (private) profilga tegishli. Bot yopiq kontentni yuklay olmaydi."


class NoVideoError(DownloaderError):
    user_message = "🖼 Bu postda video topilmadi (u faqat rasm bo'lishi mumkin)."


class AccessRestrictedError(DownloaderError):
    user_message = (
        "🚫 Instagram hozircha bu videoga kirishni cheklayapti "
        "(kirish talab qilinishi yoki so'rovlar limiti). Birozdan keyin qayta urinib ko'ring."
    )


class NetworkProblemError(DownloaderError):
    user_message = "🌐 Tarmoq xatosi yuz berdi. Birozdan keyin qayta urinib ko'ring."


class DownloadTimeoutError(DownloaderError):
    user_message = "⏱ Yuklab olish juda uzoq davom etdi va to'xtatildi. Qayta urinib ko'ring."


class DownloadFailedError(DownloaderError):
    user_message = "⚠️ Videoni yuklab bo'lmadi. Keyinroq qayta urinib ko'ring."


class FileTooLargeError(DownloaderError):
    def __init__(self, limit_mb: int = 50, detail: str | None = None) -> None:
        self.limit_mb = limit_mb
        msg = (
            f"📦 Video hajmi Telegram cheklovidan ({limit_mb} MB) katta, "
            "shuning uchun uni yuborib bo'lmaydi."
        )
        super().__init__(detail or msg, user_message=msg)


# --- Telegramga yuborish xatoliklari ---------------------------------------
class UploadFailedError(BotError):
    user_message = "📤 Videoni Telegramga yuborib bo'lmadi. Keyinroq qayta urinib ko'ring."


class TelegramTooLargeError(FileTooLargeError):
    """Telegram faylni hajmi sababli rad etdi."""


class UserBlockedBotError(BotError):
    """Foydalanuvchi botni bloklagan; unga xabar yuborib bo'lmaydi."""

    user_message = ""
