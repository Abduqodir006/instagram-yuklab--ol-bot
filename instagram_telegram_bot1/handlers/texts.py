"""Foydalanuvchiga ko'rsatiladigan matnlar (HTML parse_mode)."""
from __future__ import annotations

import html

from config import APP_NAME, APP_VERSION


def start_text(first_name: str | None) -> str:
    name = html.escape(first_name or "do'stim")
    return (
        f"👋 Salom, <b>{name}</b>!\n\n"
        "Men Instagram videolarini havola orqali yuklab beruvchi botman.\n\n"
        "📌 <b>Qanday ishlaydi:</b>\n"
        "1️⃣ Instagramda videoni oching va «Havolani nusxalash» ni bosing\n"
        "2️⃣ Havolani shu yerga yuboring\n"
        "3️⃣ Bir necha soniyada videoni olasiz\n\n"
        "Batafsil: /help"
    )


def help_text(max_mb: int) -> str:
    return (
        "ℹ️ <b>Yo'riqnoma</b>\n\n"
        "Menga Instagram havolasini yuboring, masalan:\n"
        "• <code>https://www.instagram.com/reel/XXXXXXXXXXX/</code>\n"
        "• <code>https://www.instagram.com/p/XXXXXXXXXXX/</code>\n"
        "• <code>https://www.instagram.com/tv/XXXXXXXXXXX/</code>\n\n"
        "⚠️ <b>Cheklovlar:</b>\n"
        f"• Video hajmi {max_mb} MB dan oshmasligi kerak\n"
        "• Yopiq (private) profillar va hikoyalar (stories) qo'llab-quvvatlanmaydi\n"
        "• Bir vaqtda bitta so'rov yuborish mumkin\n"
        "• Instagram vaqti-vaqti bilan kirishni cheklashi mumkin - u holda keyinroq urinib ko'ring\n\n"
        "📜 Faqat o'zingizga tegishli yoki yuklab olishga ruxsat berilgan videolardan foydalaning. "
        "Mualliflik huquqlariga rioya qilish foydalanuvchi zimmasida.\n\n"
        "Buyruqlar: /start, /help, /about"
    )


def about_text() -> str:
    return (
        f"🤖 <b>{html.escape(APP_NAME)}</b> v{APP_VERSION}\n\n"
        "Ochiq (public) Instagram videolarini havola orqali yuklab beradi.\n"
        "Texnologiyalar: Python, aiogram 3, yt-dlp, SQLite.\n\n"
        "Bot Instagram bilan rasmiy bog'liq emas. Instagram tizimi o'zgarganda "
        "ba'zi havolalar vaqtincha ishlamasligi mumkin."
    )


NO_URL = (
    "🔗 Iltimos, Instagram video havolasini yuboring.\n"
    "Masalan: <code>https://www.instagram.com/reel/XXXXXXXXXXX/</code>"
)
DOWNLOADING = "⏳ Havola tekshirildi, video yuklanmoqda..."
UPLOADING = "📤 Video yuborilmoqda..."
UNEXPECTED = "⚠️ Kutilmagan xatolik yuz berdi. Keyinroq qayta urinib ko'ring."
ADMIN_ONLY = "🚫 Bu buyruq faqat administratorlar uchun."


def caption(bot_username: str | None) -> str:
    if bot_username:
        return f"✅ Tayyor!\n🤖 @{html.escape(bot_username)}"
    return "✅ Tayyor!"


def stats_text(stats: dict) -> str:
    size_mb = stats["total_bytes"] / (1024 * 1024)
    lines = [
        "📊 <b>Statistika</b>",
        "",
        f"👥 Foydalanuvchilar: <b>{stats['total_users']}</b> "
        f"(bugun yangi: {stats['new_users_today']}, bugun faol: {stats['active_users_today']}, "
        f"botni bloklaganlar: {stats['blocked_users']})",
        f"📥 Yuklashlar: <b>{stats['total_downloads']}</b> "
        f"(muvaffaqiyatli: {stats['successful_downloads']}, xato: {stats['failed_downloads']})",
        f"🕐 Oxirgi 24 soat: {stats['downloads_last_24h']}",
        f"💾 Yuborilgan hajm: {size_mb:.1f} MB",
    ]
    if stats["top_errors"]:
        lines.append("")
        lines.append("⚠️ Eng ko'p xatolar:")
        lines.extend(f"• {html.escape(name)}: {count}" for name, count in stats["top_errors"])
    return "\n".join(lines)


# --- Ommaviy xabar (admin) ---------------------------------------------------
BROADCAST_USAGE = (
    "📣 <b>Ommaviy xabar yuborish</b>\n\n"
    "1) Matn yuborish: <code>/broadcast Xabar matni</code>\n"
    "2) Rasm/video/formatlangan xabar: avval xabarni o'zingizga yuboring (yoki shu chatda yozing), "
    "so'ng uni <b>reply</b> qilib <code>/broadcast</code> deb yozing.\n\n"
    "Bot oldin sizdan tasdiq so'raydi: yuborish /confirm_broadcast, bekor qilish /cancel_broadcast."
)
BROADCAST_NO_RECIPIENTS = "ℹ️ Hozircha xabar yuboriladigan foydalanuvchilar yo'q."
BROADCAST_BUSY = "⏳ Boshqa ommaviy xabar hozir yuborilmoqda. Tugashini kuting."
BROADCAST_NOTHING_PENDING = "ℹ️ Tasdiqlanishi kutilayotgan xabar yo'q yoki muddati tugagan. /broadcast dan boshlang."
BROADCAST_CANCELLED = "❎ Ommaviy xabar bekor qilindi."
BROADCAST_STARTED = "🚀 Yuborish boshlandi. Tugagach natijani yuboraman..."
BROADCAST_PREVIEW_FAILED = "⚠️ Xabarni nusxalab bo'lmadi. Xabar mavjudligini tekshiring."


def broadcast_confirm(count: int, minutes: int) -> str:
    return (
        f"📣 Yuqoridagi xabar <b>{count}</b> ta foydalanuvchiga yuboriladi.\n\n"
        f"✅ Tasdiqlash: /confirm_broadcast\n"
        f"❎ Bekor qilish: /cancel_broadcast\n"
        f"(Tasdiq {minutes} daqiqa amal qiladi)"
    )


def broadcast_report(total: int, sent: int, blocked: int, failed: int) -> str:
    return (
        "✅ <b>Ommaviy xabar yakunlandi</b>\n\n"
        f"👥 Jami: {total}\n"
        f"📨 Yuborildi: {sent}\n"
        f"🚫 Botni bloklagan: {blocked}\n"
        f"⚠️ Xato: {failed}"
    )
