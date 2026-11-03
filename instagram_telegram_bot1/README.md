# Instagram Video Yuklovchi Telegram Bot

Foydalanuvchi Instagram havolasini (Reel, post, IGTV) yuboradi, bot videoni **ochiq (public)** manbadan
yuklab, Telegram orqali qaytaradi. Python 3.12 · aiogram 3 · yt-dlp · SQLite.

> ⚠️ **Muhim:** Instagram tizimini tez-tez o'zgartiradi. Havolalar real sharoitda ishlashini alohida sinab
> ko'ring va yt-dlp'ni muntazam yangilang (`pip install -U yt-dlp`). Bot login, CAPTCHA yoki yopiq profil
> cheklovlarini aylanib o'tmaydi; bunday holatda foydalanuvchiga aniq xabar beradi. Instagram bloklashini
> 100% bartaraf etib bo'lmaydi. Faqat o'zingizga tegishli yoki yuklashga ruxsat berilgan videolardan foydalaning.

## Arxitektura

```
bot.py                  ishga tushirish: sozlamalar, DB, xizmatlar, polling
config.py               .env -> Settings (tekshiruv bilan)
errors.py               xatoliklar + foydalanuvchiga matnlar
downloader.py           yt-dlp o'rami (sinxron), xatolarni tasniflash, hajm/timeout nazorati
logging_setup.py        log fayli (rotatsiya), tokenni loglardan yashirish
handlers/               Telegram handlerlar (start/help/about/stats, havola qabul qilish), texts.py
services/url_validator  havolani ajratish + SSRF himoyasi (allowlist + qayta qurish)
services/download_service  parallellik limiti, navbat, per-user limit, timeout, tozalash
services/file_manager   vaqtinchalik papkalar va xavfsiz tozalash
services/sender         Telegramga yuborish, flood/tarmoq xatolarini qayta ishlash
database/db.py          SQLite statistika (foydalanuvchilar, yuklashlar)
tests/                  unittest/pytest testlari (tarmoqsiz, mock bilan)
```

Oqim: matn → havola ajratish → tekshirish (faqat instagram.com; yuklovchiga **qayta qurilgan** toza havola
beriladi) → limitlar (1 foydalanuvchi = 1 so'rov, cooldown, global parallellik) → yt-dlp alohida thread'da
→ Telegramga yuborish → vaqtinchalik papka har doim o'chiriladi.

Xususiyatlar: `/start`, `/help`, `/about`, `/stats` (faqat `ADMIN_IDS`), statistika (faqat post kodi saqlanadi,
to'liq havola emas), Karusel postlarda birinchi element yuboriladi, Telegram limiti 50 MB.

## Windows 11 da o'rnatish (PowerShell)

```powershell
# 1. Python versiyasini tekshirish (3.12 tavsiya)
py --version
# Yo'q bo'lsa:  winget install Python.Python.3.12

# 2. Loyiha papkasiga o'ting va virtual muhit yarating
cd C:\path\to\instagram_telegram_bot
py -3.12 -m venv .venv

# 3. Faollashtirish
.\.venv\Scripts\Activate.ps1
# "running scripts is disabled" chiqsa:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   (so'ng qaytadan)

# 4. Kutubxonalar
python -m pip install --upgrade pip
pip install -r requirements-dev.txt

# (Tavsiya) FFmpeg - alohida video/audio oqimlarini birlashtirish uchun
winget install Gyan.FFmpeg      # terminalni qayta oching
ffmpeg -version
```

5. **Token olish:** Telegramda `@BotFather` → `/newbot` → nom va `..._bot` bilan tugaydigan username bering →
   u sizga `123456789:AA...` ko'rinishidagi token beradi. Tokenni hech kimga bermang.
6. **.env:** `Copy-Item .env.example .env` → `.env` ni oching va `BOT_TOKEN=...` ni to'ldiring
   (o'z Telegram ID'ngizni `@userinfobot` dan bilib, `ADMIN_IDS=` ga yozsangiz `/stats` ishlaydi).
7. **Ishga tushirish:** `python bot.py` (to'xtatish: Ctrl+C). Loglar: `logs\bot.log`.
8. **Testlar:** `python -m pytest -v` yoki `python -m unittest discover -s tests -t . -v`
9. **Xatolarni aniqlash:**

| Belgi | Sabab / yechim |
|---|---|
| `Sozlama xatosi: BOT_TOKEN...` | `.env` yo'q yoki token noto'g'ri |
| `Telegramga ulanib bo'lmadi` | Token xato yoki internet/VPN muammosi |
| Doim "Instagram kirishni cheklayapti" | `pip install -U yt-dlp`; keyin ham bo'lsa Instagram IP/serverni cheklagan bo'lishi mumkin |
| "FFmpeg topilmadi" ogohlantirishi | FFmpeg o'rnating (ba'zi videolar usiz yuklanmasligi mumkin) |
| `ModuleNotFoundError` | Virtual muhit faol emas yoki `pip install -r requirements.txt` bajarilmagan |
| Katta video | Telegram bot limiti 50 MB - bu cheklov dasturiy emas |

Ixtiyoriy: `YTDLP_COOKIES_FILE` — **faqat o'zingizning** akkauntingiz cookie fayli. Bu Instagram qoidalariga
zid kelishi va akkauntingiz cheklanishiga olib kelishi mumkin; yopiq kontentni boshqalarga tarqatmang.

## Linux serverga joylashtirish (Ubuntu/Debian, systemd)

```bash
sudo apt update && sudo apt install -y python3 python3-venv ffmpeg git
sudo useradd --system --create-home --shell /usr/sbin/nologin igbot
sudo mkdir -p /opt/instagram_telegram_bot && sudo chown igbot: /opt/instagram_telegram_bot
# loyiha fayllarini /opt/instagram_telegram_bot ga nusxalang (scp/git)
sudo -u igbot python3 -m venv /opt/instagram_telegram_bot/.venv
sudo -u igbot /opt/instagram_telegram_bot/.venv/bin/pip install -r /opt/instagram_telegram_bot/requirements.txt
sudo -u igbot cp /opt/instagram_telegram_bot/.env.example /opt/instagram_telegram_bot/.env
sudo -u igbot nano /opt/instagram_telegram_bot/.env      # BOT_TOKEN ni kiriting
sudo chmod 600 /opt/instagram_telegram_bot/.env
```

`/etc/systemd/system/instagram-bot.service`:

```ini
[Unit]
Description=Instagram Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
User=igbot
WorkingDirectory=/opt/instagram_telegram_bot
ExecStart=/opt/instagram_telegram_bot/.venv/bin/python bot.py
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/instagram_telegram_bot

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now instagram-bot
sudo systemctl status instagram-bot
journalctl -u instagram-bot -f            # yoki: tail -f /opt/instagram_telegram_bot/logs/bot.log
# yt-dlp'ni yangilash (haftada bir tavsiya):
sudo -u igbot /opt/instagram_telegram_bot/.venv/bin/pip install -U yt-dlp && sudo systemctl restart instagram-bot
```

Server (ayniqsa datacenter IP) Instagram tomonidan cheklanishi mumkin - bu odatiy holat.

## Administrator buyruqlari

`.env` dagi `ADMIN_IDS` ga raqamli Telegram ID'ingizni yozing (ID'ni @userinfobot beradi).

| Buyruq | Vazifasi |
|---|---|
| `/stats` | Foydalanuvchilar va yuklashlar statistikasi |
| `/broadcast matn` | Matnni barcha foydalanuvchilarga yuborishga tayyorlaydi |
| (xabarga reply) `/broadcast` | Rasm/video/formatlangan xabarni nusxalab yuborishga tayyorlaydi |
| `/confirm_broadcast` | Tayyorlangan xabarni yuboradi (tasdiq 5 daqiqa amal qiladi) |
| `/cancel_broadcast` | Bekor qiladi |

Yuborish tezligi ~20 xabar/soniya (Telegram limitidan past). Botni bloklaganlar avtomatik belgilanadi va
keyingi e'lonlarga kiritilmaydi; ular botga qayta yozsa ro'yxatga qaytadi. Oxirida hisobot keladi.

## Sozlamalar (.env)

`.env.example` ga qarang: limitlar (`MAX_FILE_SIZE_MB` ≤ 50, `DOWNLOAD_TIMEOUT`, `MAX_CONCURRENT_DOWNLOADS`,
`USER_COOLDOWN_SECONDS`, `MAX_QUEUE_SIZE`...), yo'llar va log darajasi.

## Ma'lum cheklovlar

* Stories, profil, highlight havolalari, `/share/` qisqa havolalari qo'llab-quvvatlanmaydi.
* Faqat rasm bo'lgan postlar uchun "video topilmadi" xabari chiqadi.
* Telegram bulutli Bot API: yuborish limiti 50 MB.
