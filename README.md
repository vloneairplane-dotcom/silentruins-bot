# SilentRuins Bot V3.2

V3.2 focuses on editorial quality rather than adding more features. The bot now treats each post as a coherent package of **mood + Persian caption + dark visual + music**.

### V3.2 improvements
- Time-of-day mood priorities, with strong Midnight identity for Night/Lonely/Ruins.
- Semantic music taxonomy: Heartbreak, Missing, Memories, Loneliness, etc. map to the six channel moods.
- Better music candidate selection without consuming the no-repeat cycle during preview/candidate generation.
- Persian caption quality scoring and replacement of weak/awkward legacy captions.
- Visual intent scoring for rain/night/loneliness/love/tired/ruins instead of darkness-only scoring.
- Quality score is a real production gate: low-quality candidates are rejected.
- Stronger recent-track, recent-caption, recent-image and recent-post anti-repeat memory.
- Existing SQLite analytics, admin panel, scheduler, Pexels integration, Railway support and backup system are preserved.

### Recommended production settings
```env
POST_TIMES=10:00,16:00,22:00,02:00
QUALITY_THRESHOLD=85
MAX_CANDIDATES=10
TIMEZONE=Asia/Tehran
```

> Important: V3.2 improves content selection, but the best posting times should eventually be learned from real channel engagement data.
# SilentRuins Bot 🥀 — Pro Edition

ربات حرفه‌ای تلگرام برای چنل‌های غمگین و دپ — هر پست یه «ستِ هم‌حس»:

**📸 عکس دارک از Pexels ← متن سنگین + ایموجی مرتبط ← 🎧 آهنگ مرتبط** (با اسم خواننده و ترک)

## ✨ امکانات

### 🆕 Pro v3 Upgrade
- 🗄 **SQLite Analytics Database** برای ثبت پست‌ها، خطاها، آهنگ‌ها و تعداد استفاده از هر آهنگ
- 📊 **گزارش تحلیلی** با `/report`
- 🔎 **جستجوی آهنگ** با `/findsong`
- ⏰ **زمان‌بندی دستی یک‌باره** با `/schedule` و نمایش Jobها با `/jobs`
- 💾 **Backup یک‌کلیکی** با `/backup` شامل Library، State و Database
- 🎛️ دکمه‌های جدید در پنل مدیریت برای گزارش، Jobها و Backup
- 📈 آمار `/stats` اکنون از داده‌های واقعی Analytics نیز استفاده می‌کند


- 🔗 **سیستم حس‌محور** — ۶ حس (بارون 🌧 شب 🌃 تنهایی 🚶 دلتنگی 🥀 خستگی 🕯 ویرونه 🏚)؛ هر پست عکس و کپشنش از **یک** حس انتخاب می‌شن و آهنگ هم ترجیحاً از همون حسه
- ✍️ **متن‌های سنگین و ادبی-عامیانه** — ۵۰ متن غمگینِ دلنشین (مثل «همه‌چیز به وقتش قشنگه؛ هیچ‌چیزی بعدا قشنگ نیس») که بدون تکرار می‌چرخن
- 🌑 **عکس‌های دارک و تک‌نفره** — کوئری‌های تاریک + فیلتر خودکار رنگ میانگین؛ ربات از بین نتایج Pexels تاریک‌ترین‌ها رو برمی‌داره
- 📸 زیر عکس **فقط متن مرتبط** — بدون هشتگ، بدون آیدی چنل، بدون شلوغی
- 🥀 **امضای آخر هر پست**: `— silent ruins 🥀`
- 🌧 **ایموجی مرتبط با هر متن** — ته هر کپشن یه ایموجی هم‌حس‌اش میاد (بارون 🌧 ماه 🌙 رز 🥀 شمع 🕯 …)
- 🎧 **آهنگ با کپشن خواننده و ترک** — اسم خواننده (🎤) و ترک (🎵) خودکار از فایل MP3 خونده می‌شه و موقع پست هم توی خود پلیر ست می‌شه
- 🔁 **بدون تکرار** — نه آهنگ تکراری می‌شه، نه کپشن؛ تا همه یک دور رد نشن، تکرار نمی‌شه
- 👁 **پیش‌نمایش** (`/preview`) — نمونه‌ی پست بعدی رو فقط تو پیوی خودت ببین، بدون انتشار و بدون سوختن نوبت آهنگ
- ⏰ پست خودکار زمان‌بندی‌شده (پیش‌فرض ۱۰، ۱۶، ۲۲ و ۰۲ به‌وقت تهران)
- 🎛 پنل مدیریت کامل — فقط ادمین
- 📝 کپشن روی عکس **ساده و تمیزه** (بدون شلوغی) — اسم عکاس فقط با `PHOTO_CREDIT=true` اضافه می‌شه
- 🚫 بدون عکس می‌خوای؟ `SEND_PHOTOS=false` → فقط متن + آهنگ

## 📦 شکل هر پست

```
① عکس دپ (مثلاً بارون پشت شیشه) با کپشنِ مرتبط:
   «بارون سرای اوناس که نمی‌دونن چرا دلشون گرفته.» 🌧

   — silent ruins 🥀
② 🎧 آهنگ هم‌حس (ریپلایِ عکس) با کپشن:
   🎤 اسم خواننده
   🎵 اسم ترک

   — silent ruins 🥀
```

## ⚠️ مهم — امنیت

تو کامیت‌های قبلی این ریپو **توکن واقعی ربات و کلید Pexels** لو رفته. حتماً:
1. تو چت **@BotFather** → `/revoke` → توکن جدید بگیر
2. کلید Pexels رو توی داشبورد pexels.com عوض کن (اگه از حالت عکس‌دار استفاده می‌کنی)

توکن جدید رو فقط تو `.env` (لوکال) یا Variables هاست بذار — `.gitignore` از کامیت شدنش جلوگیری می‌کنه.

## 🚀 راه‌اندازی

### ۱) چیزهایی که لازمه

| چیز | از کجا |
|---|---|
| `BOT_TOKEN` | **@BotFather** → `/newbot` |
| `ADMIN_IDS` | آیدی عددی خودت از **@userinfobot** |
| `CHANNEL` | یوزرنیم چنل پابلیک با `@` یا آیدی عددی (`-100...`) برای پرایوت |
| `PEXELS_API_KEY` | از [pexels.com/api](https://www.pexels.com/api/) رایگان (برای حالت عکس لازمه) |

### ۲) ربات رو ادمین چنل کن

تنظیمات چنل → Administrators → Add Admin → ربات → دسترسی **Post Messages**.

### ۳) اجرا

```bash
pip install -r requirements.txt
cp env.example .env   # پرش کن
python bot.py
```

### ۴) تست تو تلگرام

تو **پیوی ربات**:
1. چند تا **MP3** بفرست ← با «✅ ذخیره شد! 🎤 … 🎵 …» تأیید می‌شه (می‌تونی تو کپشن MP3 بنویسی «خواننده - ترک»)
3. `/preview` ← نمونه‌ی پست رو ببین
4. `/post` ← پست واقعی بره تو چنل 🎉
5. `/panel` ← پنل شیشه‌ای مدیریت

### 🎵 حس دادن به آهنگ‌ها (مهم برای تطبیق با عکس)

موقع فرستادن MP3 تو کپشنش یه کلمه بنویس تا آهنگ اون حس رو بگیره و با عکس‌های هم‌حس پخش بشه:

`بارون` `شب` `تنهایی` `دلتنگی` `خستگی` `ویرونه`
(انگلیسی و فینگلیش هم می‌فهمه: rain, night, shab, deltangi, virane…)

می‌تونی هم‌زمان اسم خواننده و ترک رو هم این‌جور بنویسی: `خواننده - ترک`

## 📋 دستورات

| دستور | کار |
|---|---|
| `/post` | پست فوری کامل (عکس + متن + آهنگ) |
| `/preview` | پیش‌نمایش فقط برای خودت (بدون انتشار) |
| `/songs` | لیست آهنگ‌ها با خواننده |
| `/del <شماره>` | حذف آهنگ |
| `/pause` / `/resume` | توقف/ادامه‌ی پست خودکار |
| `/stats` | آمار کامل + زمان پست بعدی |
| `/panel` | پنل **شیشه‌ای** مدیریت (پست فوری، پیش‌نمایش، آمار، لیست آهنگ‌ها، توقف/ادامه — همه با دکمه) |
| `/id` | آیدی عددی خودت |
| `/report` | گزارش Analytics |
| `/findsong <کلمه>` | جستجوی آهنگ |
| `/schedule <زمان>` | زمان‌بندی یک پست؛ مثال `/schedule 23:30` |
| `/jobs` | نمایش Jobهای فعال |
| `/backup` | ساخت و ارسال Backup |

## ⚙️ متغیرها (`.env`)

| متغیر | پیش‌فرض | توضیح |
|---|---|---|
| `BOT_TOKEN` | — | توکن ربات |
| `ADMIN_IDS` | — | آیدی(های) عددی ادمین با کاما |
| `CHANNEL` | — | `@yourchannel` یا آیدی عددی |
| `SEND_PHOTOS` | `true` | `false` کن تا فقط متن + آهنگ پست بشه |
| `PEXELS_API_KEY` | — | برای پست عکس لازمه (اگه نباشه، خودکار فعلاً متنی پست می‌شه) |
| `PHOTO_CREDIT` | `false` | `true` کن تا اسم عکاس ته کپشن بیاد |
| `TIMEZONE` | `Asia/Tehran` | منطقه‌ی زمانی |
| `POST_TIMES` | `10:00,16:00,22:00,02:00` | ساعت‌های پست، با کاما |
| `DATA_DIR` | `.` | مسیر دیتای دائمی (روی Railway: `/data`) |
| `PORT` | — | فقط برای هاست‌های Web Service |

دیتابیس Analytics به‌صورت خودکار در `DATA_DIR/silentruins.db` ساخته می‌شود.

## ☁️ دیپلوی روی Railway

ریپو `railway.toml` داره و آماده‌ست:

1. توی [railway.com](https://railway.com) با GitHub لاگین کن
2. **New Project → Deploy from GitHub repo** → `silentruins-bot`
3. تو **Variables** متغیرها رو بذار (`BOT_TOKEN`, `ADMIN_IDS`, `CHANNEL`, `TIMEZONE` و…)
4. برای موندن کتابخونه آهنگ بعد از هر دیپلوی: **+ Volume** با Mount Path `/data` + متغیر `DATA_DIR=/data`
5. از این به بعد **هر push به برنچ = دیپلوی خودکار** ✅

تو Logs باید `Silent Ruins 🥀 started` رو ببینی.

## 🛠 سفارشی‌سازی

تو `bot.py`:
- **حس‌ها + متن‌ها + کوئری‌های عکس** → دیکشنری `MOODS` (از هر حس می‌تونی کم/زیاد کنی یا حس جدید اضافه کنی)
- **امضای ته پست‌ها** → `SIGNATURE`
- **کلیدواژه‌های تشخیص حس آهنگ** → `MOOD_ALIASES`

بعد از ویرایش، push کن — Railway خودش ری‌دیپلوی می‌کنه.

## Pexels API (فقط حالت عکس‌دار)

از https://www.pexels.com/api/ رایگان بگیر — ساعتی 200 و ماهانه 20,000 درخواست رایگانه. عکس‌ها با credit عکاس پست می‌شن.

## Smart Content Engine (v3 upgrade)

The bot now builds coherent sad-content sets instead of selecting everything independently:

- **Mood Engine:** chooses moods using time-of-day windows and recent-mood cooldowns.
- **Content Matching:** scores text, image, and music compatibility with the selected mood.
- **Anti-Repetition:** remembers recent post signatures, captions, and image URLs to avoid immediate repeats.
- **Smart Selection:** tries multiple candidate sets and publishes the strongest fresh set.
- **Quality Score:** stores a 0–100 score for text/image/music/overall coherence.
- **Mood Status:** `/mood` shows recent mood rotation and the latest quality score.

The existing Music Library, Pexels search, scheduler, analytics database, admin panel, backup, and Railway deployment remain in place.
