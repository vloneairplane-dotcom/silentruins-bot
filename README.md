# SilentRuins Bot 🥀 — Pexels Edition

ربات تلگرام برای چنل‌های غمگین و دپ — خودکار از **Pexels** عکس دارک و غمگین میگیره، با متن فارسی دپ و آهنگ میذاره تو چنل.

## چی کار میکنه؟
- 📸 عکس غمگین و دارک از Pexels (با 25 تا کوئری مختلف مثل sad aesthetic, lonely night, rainy window...)
- 💔 کپشن فارسی دپ — 40+ متن غمگین آماده
- 🎵 آهنگ خودکار — آهنگ‌هایی که ادمین تو پیوی ربات میفرسته، ذخیره میشه تو `music/` و نوبتی پست میشه همراه عکس
- ⏰ پست خودکار زمان‌بندی شده
- 🎛 پنل ادمین کامل

## ⚠️ مهم — امنیت

تو کامیت‌های قبلی این ریپو **توکن واقعی ربات و کلید واقعی Pexels** (مربوط به چنل @songsandscars)
به‌صورت عمومی قرار داشت. حتی با پاک کردنشون از فایل‌ها، توی تاریخچه‌ی گیت می‌مونن، پس **حتماً**
این دو کار رو بکن:

1. تو چت **@BotFather** دستور `/revoke` رو بزن → رباتت رو انتخاب کن → **توکن جدید** میگیری
2. تو **[pexels.com/api/dashboard](https://www.pexels.com/api/dashboard)** کلید قدیمی رو عوض کن (یا کلید جدید بساز)

توکن و کلید جدید رو **فقط** تو فایل `.env` (لوکال) یا Environment Variables هاست بذار —
فایل `.gitignore` جلوی کامیت شدنش رو میگیره.

## Environment variables

```
BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PEXELS_API_KEY=your_pexels_api_key
ADMIN_IDS=123456789
CHANNEL=@yourchannel
TIMEZONE=Asia/Tehran
POST_TIMES=10:00,16:00,22:00,02:00
# یا هر 3 ساعت: POST_INTERVAL_HOURS=3
```

- `BOT_TOKEN` → از **@BotFather** با `/newbot`
- `PEXELS_API_KEY` → از [pexels.com/api](https://www.pexels.com/api/) (رایگان)
- `ADMIN_IDS` → آیدی عددی خودت از **@userinfobot** (چند نفر؟ با کاما جدا کن)
- `CHANNEL` → یوزرنیم چنل پابلیک با `@` یا آیدی عددی چنل پرایوت (`-100...`)
- یادت نره **ربات رو ادمین چنل کنی** با دسترسی Post Messages، وگرنه نمی‌تونه پست بذاره

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

از https://www.pexels.com/api/ رایگان بگیر — ساعتی 200 و ماهانه 20,000 درخواست رایگان داره که برای 4 پست در روز خیلی هم کافیه.

عکس‌ها با credit عکاس پست میشن.
