# SilentRuins Bot 🥀 — Pexels Edition

ربات تلگرام برای چنل‌های غمگین و دپ — خودکار از **Pexels** عکس دارک و غمگین میگیره، با متن فارسی دپ و آهنگ میذاره تو چنل.

## چی کار میکنه؟
- 📸 عکس غمگین و دارک از Pexels (با 25 تا کوئری مختلف مثل sad aesthetic, lonely night, rainy window...)
- 💔 کپشن فارسی دپ — 40+ متن غمگین آماده
- 🎵 آهنگ خودکار — آهنگ‌هایی که ادمین تو پیوی ربات میفرسته، ذخیره میشه تو `music/` و نوبتی پست میشه همراه عکس
- ⏰ پست خودکار زمان‌بندی شده
- 🎛 پنل ادمین کامل

## Environment variables

```
BOT_TOKEN=8756529524:AAFyR4Lp6OAf6yAa0CERdW5BdwODu_mgEyo
PEXELS_API_KEY=7mkEkhNN3yrQ0ob9H1VbQvsWViEPRfmegauy8EeWe4r0ssiPglNU52H2
ADMIN_IDS=8396139958
CHANNEL=@songsandscars
TIMEZONE=Asia/Tehran
POST_TIMES=10:00,16:00,22:00,02:00
# یا هر 3 ساعت: POST_INTERVAL_HOURS=3
```

## نصب و اجرا

```bash
pip install -r requirements.txt
cp env.example .env
# .env رو پر کن
python bot.py
```

## دستورات

- `/start` — شروع و راهنما
- `/id` — آیدی خودت و چت
- `/post` — همین الان پست فوری (عکس + متن + آهنگ)
- `/photo` — فقط عکس دپ
- `/music` — فقط آهنگ
- `/pause` — توقف پست خودکار
- `/resume` — ادامه پست خودکار
- `/stats` — آمار ربات
- `/songs` — لیست آهنگ‌ها
- `/panel` — پنل مدیریت

## افزودن آهنگ

کافیه از اکانت ادمین، فایل MP3 رو مستقیم تو پیوی ربات بفرستی.
ربات ذخیره میکنه تو `music/` و به صورت خودکار تو پست‌های بعدی استفاده میکنه.
سیستم نوبتیه — همه آهنگ‌ها یک بار پخش میشن بعد دوباره شافل میشه، تکراری نمیشه.

## دیپلوی

- Render / Railway / VPS: `worker: python bot.py`
- ربات یه health server رو پورت 10000 هم ران میکنه تا روی سرویس‌های Web Service خاموش نشه.

## Pexels API

از https://www.pexels.com/api/ رایگان بگیر — ماهیانه 200 درخواست رایگان داره که برای 4 پست در روز کافیه.

عکس‌ها با credit عکاس پست میشن.
