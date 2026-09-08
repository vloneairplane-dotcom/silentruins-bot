"""
SilentRuins Bot 🥀 — Pro Edition
--------------------------------
ربات چنل‌های دپ/غمگین:

هر پست = متن ساده‌ی احساسی + استیکر + آهنگ (با اسم خواننده و ترک)

- 📚 کتابخونه‌ی آهنگ: MP3 رو تو پیوی ربات می‌فرستی، ذخیره می‌شه و نوبتی پست می‌شه
- 🎭 کتابخونه‌ی استیکر: استیکر موردعلاقه‌ات رو تو پیوی می‌فرستی، یا یه پک عمومی معرفی می‌کنی
- 🔁 بدون تکرار: نه آهنگ تکراری می‌شه، نه کپشن — تا همه یک دور رد نشن
- 👁 پیش‌نمایش: قبل از انتشار، نمونه‌ی پست رو تو پیوی خودت ببین (/preview)
- 📸 اگه عکس بخوای: SEND_PHOTOS=true → پست‌ها عکس Pexels هم می‌گیرن (پیش‌فرض: خاموش)
"""

import asyncio
import json
import logging
import os
import random
import threading
import time as time_module
from datetime import time as dtime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Config — همه از متغیرهای محیطی (نمونه: env.example)
# ---------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN تنظیم نشده — توی .env یا Variables هاست بذارش")


def _env_flag(name, default=False):
    return os.getenv(name, "true" if default else "false").strip().lower() in (
        "1", "true", "yes", "on",
    )


# حالت عکس‌دار (پیش‌فرض خاموش — فقط متن + استیکر + آهنگ)
SEND_PHOTOS = _env_flag("SEND_PHOTOS", False)

# منشن آیدی چنل ته کپشن پست اصلی
SHOW_CHANNEL_TAG = _env_flag("SHOW_CHANNEL_TAG", True)

PEXELS_API_KEY = (
    os.getenv("PEXELS_API_KEY")
    or os.getenv("PIXEL_API_KEY")
    or os.getenv("UNSPLASH_ACCESS_KEY")
)
if SEND_PHOTOS and not PEXELS_API_KEY:
    raise RuntimeError("❌ SEND_PHOTOS فعاله ولی PEXELS_API_KEY نیست — از pexels.com/api رایگان بگیر")

# پک استیکر عمومی تلگرام (اختیاری) — مثلاً STICKER_SET=SadHamster
# اگه خالی باشه، فقط استیکرهایی که خودت تو پیوی می‌فرستی استفاده می‌شن
STICKER_SET = (os.getenv("STICKER_SET") or "").strip()

# ادمین‌ها: ADMIN_IDS (با کاما) یا ADMIN_USER_ID (تکی)
_admin_raw = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_USER_ID") or ""
ADMIN_IDS = set()
for part in str(_admin_raw).split(","):
    part = part.strip()
    if part.lstrip("-").isdigit():
        ADMIN_IDS.add(int(part))
if not ADMIN_IDS:
    logging.warning("⚠️ ADMIN_IDS تنظیم نشده — ربات به دستورات ادمین جواب نمی‌ده")

# چنل: CHANNEL یا CHANNEL_ID (پابلیک با @ / پرایوت با آیدی عددی)
_raw_channel = os.getenv("CHANNEL") or os.getenv("CHANNEL_ID") or ""
if not _raw_channel:
    raise RuntimeError("❌ CHANNEL تنظیم نشده (مثل @songsandscars یا -100123...)")
CHANNEL_ID = (
    _raw_channel
    if _raw_channel.startswith("@")
    else int(_raw_channel) if _raw_channel.lstrip("-").isdigit() else _raw_channel
)

TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Tehran")
try:
    TIMEZONE = ZoneInfo(TIMEZONE_STR)
except Exception:
    TIMEZONE = ZoneInfo("Asia/Tehran")

# زمان‌بندی پست‌ها
POST_TIMES_RAW = os.getenv("POST_TIMES") or os.getenv("PHOTO_TIMES") or "10:00,16:00,22:00,02:00"
POST_TIMES = [t.strip() for t in POST_TIMES_RAW.split(",") if t.strip()]
MUSIC_TIMES_RAW = os.getenv("MUSIC_TIMES", "")
MUSIC_TIMES = [t.strip() for t in MUSIC_TIMES_RAW.split(",") if t.strip()]

POST_INTERVAL_HOURS = os.getenv("POST_INTERVAL_HOURS")
try:
    POST_INTERVAL_HOURS = float(POST_INTERVAL_HOURS) if POST_INTERVAL_HOURS else None
except ValueError:
    POST_INTERVAL_HOURS = None

# مسیر دیتای دائمی (روی Railway: Volume با Mount Path=/data و DATA_DIR=/data)
DATA_DIR = Path(os.getenv("DATA_DIR", ".")).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)
LIBRARY_FILE = DATA_DIR / "library.json"
STATE_FILE = DATA_DIR / "state.json"
MUSIC_DIR = DATA_DIR / "music"
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# محتوا: متن‌های فارسی طبیعی
# ---------------------------------------------------------------------------
# کوئری‌های عکس (فقط وقتی SEND_PHOTOS=true)
SAD_QUERIES = [
    "sad aesthetic", "depression dark aesthetic", "lonely girl night window",
    "sad boy alone dark", "melancholy portrait", "dark moody aesthetic",
    "broken heart aesthetic", "alone in dark room", "crying in rain aesthetic",
    "rainy night alone", "empty room depression", "sad eyes close up",
    "foggy lonely road night", "withered roses dark", "black and white sadness",
    "gothic melancholy", "abandoned room dark", "loneliness aesthetic",
    "sad girl black and white", "dark forest loneliness",
    "cigarette smoke sad night", "empty bed sadness", "window rain night sad",
    "depressed aesthetic girl", "moody dark portrait",
]

# متن‌های پست — رایج‌ترین حالت روزمره‌ی حس دپ. ویرایش/اضافه کن؛ ربات بدون تکرار می‌چرخه روشون.
PERSIAN_SAD_CAPTIONS = [
    "اینجا همه چی خوبه جز خودم... 🖤",
    "یه وقتایی آدم دلش میخواد گم بشه، نه پیدا.",
    "خسته‌ام از تظاهر به خوب بودن 🥀",
    "بارون که میزنه، دلتنگی بیشتر میفهمه چیکار کنه.",
    "بعضی شبا خوابم نمیبره، خاطره‌هات بیدارم نگه میدارن.",
    "چقدر سخته وانمود کنی حالت خوبه وقتی نیست.",
    "دلم یه جای دور میخواد، جایی که هیچکس نباشه.",
    "همه رفتن، فقط جای خالیشون مونده.",
    "یه وقتایی سکوت از هر فریادی بلندتره.",
    "کاش میشد برگشت به روزایی که بی‌دلیل شاد بودیم.",
    "من اونقدر قوی نیستم که نشون میدم.",
    "تو شلوغی هم تنهام... 🖤",
    "بعضی زخما هیچوقت خوب نمیشن، فقط عادت میکنی به دردشون.",
    "دلم گرفته، نه از بارون، از خودم.",
    "چقدر دلتنگم برای کسی که هیچوقت نفهمید.",
    "شبا طولانی‌ترن وقتی کسی رو نداری بهش فکر کنی... یا داری و نیست.",
    "خسته شدم از جنگیدن با خودم هر شب.",
    "هیچی بدتر از این نیست که خودت مقصر حال بدت باشی.",
    "یه روز میفهمی چقدر بی‌صدا شکستی.",
    "دنیا قشنگه ولی نه برای همه.",
    "بعضی آدما میان که تا ابد دلتنگت کنن و برن.",
    "من خوبم، فقط یکم خسته‌ام، یکم شکسته‌ام، یکم...",
    "کاش میشد یه بار دیگه بیخیال بود.",
    "تنهایی قشنگ نیست، فقط عادت میشه.",
    "دلم میخواد یه مدت هیچکس منو نشناسه.",
    "همه میگن میگذره، ولی نمیگن چجوری میگذره.",
    "یه وقتایی باید بذاری بره، حتی اگه هنوز دوسش داری.",
    "من از اون آدمایی نیستم که زود فراموش کنن.",
    "چشام خسته‌ان از بس به در خیره موندن.",
    "غمگین ترین قسمت داستان اینه که عادت کردم به نبودنت.",
    "کاش میشد به عقب برگشت و هیچوقت بعضیا رو نمیدیدیم.",
    "بعضی شبا دلم میخواد هیچ صبحی نیاد.",
    "دارم یاد میگیرم بدون تو ادامه بدم، ولی هنوز بلد نیستم.",
    "حالم بده ولی به کسی نمیگم، چون کسی نمیفهمه.",
    "یادته میگفتی همیشه میمونی؟",
    "این روزا بیشتر با خودم حرف میزنم تا با بقیه.",
    "دلم برای خودِ قدیمم تنگ شده.",
    "چقدر زود دیر میشه...",
    "از یه جایی به بعد فقط تحمل میکنی، زندگی نمیکنی.",
    "خسته‌ام از این همه بغضِ نگفته.",
    "کاش یکی بود میفهمید بی‌حرفی یعنی چی.",
    "شب بخیر به کسی که هیچوقت شب بخیرم نگفت.",
    "ما تموم شدیم ولی خاطره‌هامون نه.",
    # --- دسته دوم: روزمره‌تر و طبیعی‌تر ---
    "یه حسی میگه همه‌چیز دیر شده.",
    "امشبم مثل دیروز گذشت.",
    "کسی حالم رو نپرسید، منم نگفتم 🖤",
    "چراغا خاموش، آهنگ پخش، فکرا روشن.",
    "یه جایی وسط روز، بی‌دلیل دلتنگ شدم.",
    "حرف زیاد داشتم؛ پس ندادم.",
    "دیشب خوابم نبرد، فکرا سنگین بودن.",
    "گاهی فقط یه آهنگ حالتو می‌فهمه.",
    "ادامه می‌دم، ولی نه مثل قبل.",
    "دلم یه بارونِ ساکت می‌خواد.",
    "همه‌چی سر جاشه، جز من.",
    "بعضی روزا فقط می‌گذرن؛ زندگی نمی‌شن.",
    "صبح شد، ولی نه برام.",
    "به دیشبم پیام دادم؛ خونده نشد.",
    "ساعت سه‌ی شب و یه آهنگ تکراری.",
    "بغضمو قورت دادم، رد شد.",
    "هنوز منتظرم، نمیدونم چی.",
    "مردم می‌رن؛ عادت دارم.",
    "خنده‌هام امروز اجاره‌ای بودن.",
    "خیلی وقته کسی نپرسیده خوبی؟",
    "دلم برای روزای ساده تنگ شده.",
    "یه نفس عمیق و ادامه.",
    "هیچی نشد، مثل همیشه.",
    "آدم گمشه‌ی خودشه بعضی روزا.",
    "کاش زودتر می‌فهمیدم.",
    "باشه، اشکالی نداره.",
]

# خط‌های کوتاهی که گاهی ته کپشن آهنگ می‌آد
MUSIC_LINES = [
    "🎧 صداشو زیاد کن.",
    "این یکی برای نیمه‌شب‌ست.",
    "یه گوشه بنشین و فقط گوش بده.",
    "پلی بشه 🖤",
    "هر هرکی حالته، این آهنگ می‌فهمه.",
    "تکرارش کن، لازم داری.",
    "وقتی همه خوابن، این پخش بشه.",
    "بذارش رو ریپیت.",
    "یه آهنگ از طرف من برای این شبِ سرد.",
    "قشنگه، نه؟",
]

HASHTAGS = ["#غمگین", "#دپ", "#دلتنگی", "#شب_بخیر", "#تنهایی"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("silent_ruins_bot")


# ---------------------------------------------------------------------------
# Health server (برای هاست‌هایی که پورت می‌خوان مثل Render)
# ---------------------------------------------------------------------------
def _run_health_server():
    port = int(os.environ.get("PORT", "10000"))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Silent Ruins bot is alive".encode("utf-8"))

        def log_message(self, format, *args):
            pass

    try:
        HTTPServer(("0.0.0.0", port), Handler).serve_forever()
    except Exception as e:
        logger.warning(f"Health server failed: {e}")


# ---------------------------------------------------------------------------
# ذخیره‌سازی
# ---------------------------------------------------------------------------
def load_library():
    if LIBRARY_FILE.exists():
        try:
            data = json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}
    data.setdefault("tracks", [])
    data.setdefault("unplayed", [])
    data.setdefault("stickers", [])
    return data


def save_library(data):
    LIBRARY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"is_paused": False, "post_count": 0, "last_query": None}


def save_state(patch):
    state = load_state()
    state.update(patch)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_admin(update: Update) -> bool:
    return bool(update.effective_user) and update.effective_user.id in ADMIN_IDS


# ---------------------------------------------------------------------------
# کپشن پست اصلی — بدون تکرار تا اتمام همه
# ---------------------------------------------------------------------------
def pick_caption_line():
    state = load_state()
    used = set(state.get("caption_used", []))
    all_idx = list(range(len(PERSIAN_SAD_CAPTIONS)))
    remaining = [i for i in all_idx if i not in used]
    if not remaining:
        used = set()
        remaining = all_idx
    idx = random.choice(remaining)
    used.add(idx)
    save_state({"caption_used": sorted(used)})
    return PERSIAN_SAD_CAPTIONS[idx]


def build_caption():
    parts = [pick_caption_line()]
    if random.random() < 0.30:  # گاهی هشتگ، که طبیعی‌تر بشه
        parts.append(" ".join(random.sample(HASHTAGS, k=random.randint(1, 2))))
    if SHOW_CHANNEL_TAG and isinstance(CHANNEL_ID, str) and CHANNEL_ID.startswith("@"):
        parts.append(CHANNEL_ID)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# استیکر: کتابخونه (پیوی) + پک عمومی اختیاری
# ---------------------------------------------------------------------------
def _pack_stickers():
    return load_state().get("pack_stickers", [])


def sticker_pool():
    lib = load_library()
    return [s["file_id"] for s in lib["stickers"]] + _pack_stickers()


def remove_sticker(file_id):
    lib = load_library()
    if any(s["file_id"] == file_id for s in lib["stickers"]):
        lib["stickers"] = [s for s in lib["stickers"] if s["file_id"] != file_id]
        save_library(lib)
    pack = [f for f in _pack_stickers() if f != file_id]
    save_state({"pack_stickers": pack})


async def send_random_sticker(context, chat_id, reply_to=None):
    pool = sticker_pool()
    if not pool:
        return None
    tried = set()
    for _ in range(3):
        remaining = [f for f in pool if f not in tried]
        if not remaining:
            return None
        fid = random.choice(remaining)
        tried.add(fid)
        try:
            return await context.bot.send_sticker(
                chat_id=chat_id, sticker=fid, reply_to_message_id=reply_to
            )
        except Exception as e:
            logger.warning(f"sticker send failed, removing: {e}")
            remove_sticker(fid)
    return None


async def refresh_sticker_pack(context: ContextTypes.DEFAULT_TYPE):
    """File_idهای یه پک عمومی رو یه بار می‌گیره و کش می‌کنه."""
    if not STICKER_SET:
        return
    try:
        s = await context.bot.get_sticker_set(STICKER_SET)
        ids = [st.file_id for st in s.stickers]
        save_state({"pack_stickers": ids})
        logger.info(f"Loaded {len(ids)} stickers from pack '{STICKER_SET}'")
    except Exception as e:
        logger.warning(f"Could not load sticker pack '{STICKER_SET}': {e}")


# ---------------------------------------------------------------------------
# آهنگ: کتابخونه‌ی بدون تکرار + کپشن خواننده/ترک
# ---------------------------------------------------------------------------
def get_next_track(peek=False):
    """آهنگ بعدی چرخه‌ی بدون‌تکرار. peek=True فقط نگاه می‌کنه (برای پیش‌نمایش)."""
    lib = load_library()
    if not lib["tracks"]:
        return None
    if peek:
        return random.choice(lib["tracks"])

    if not lib["unplayed"]:
        lib["unplayed"] = [t["file_id"] for t in lib["tracks"]]
        random.shuffle(lib["unplayed"])

    next_file_id = lib["unplayed"].pop(0)
    save_library(lib)
    for t in lib["tracks"]:
        if t["file_id"] == next_file_id:
            return t
    return {"file_id": next_file_id, "title": "بدون‌نام"}


def build_audio_caption(track):
    title = (track.get("title") or "").strip() or "بدون‌نام"
    performer = (track.get("performer") or "").strip()
    lines = []
    if performer:
        lines.append(f"🎤 {performer}")
    lines.append(f"🎵 {title}")
    if random.random() < 0.45:
        lines.append("")
        lines.append(random.choice(MUSIC_LINES))
    return "\n".join(lines)


async def send_track(context, chat_id, track, reply_to=None):
    caption = build_audio_caption(track)
    file_path = track.get("file_path")
    # اگه فایل روی دیسک هست → دوباره آپلود می‌کنیم که title/performer هم ست بشن
    if file_path and Path(file_path).exists():
        with open(file_path, "rb") as f:
            return await context.bot.send_audio(
                chat_id=chat_id,
                audio=f,
                caption=caption,
                title=(track.get("title") or None),
                performer=(track.get("performer") or None),
                reply_to_message_id=reply_to,
            )
    return await context.bot.send_audio(
        chat_id=chat_id,
        audio=track["file_id"],
        caption=caption,
        reply_to_message_id=reply_to,
    )


def delete_track_by_number(n):
    """حذف آهنگ شماره‌ی n (۱-مبنا). خروجی: دیکشنری آهنگ یا None"""
    lib = load_library()
    if n < 1 or n > len(lib["tracks"]):
        return None
    removed = lib["tracks"].pop(n - 1)
    lib["unplayed"] = [f for f in lib["unplayed"] if f != removed["file_id"]]
    save_library(lib)
    # فایل دیسکی رو هم پاک کن (اگه هست)
    fp = removed.get("file_path")
    if fp:
        try:
            Path(fp).unlink(missing_ok=True)
        except Exception:
            pass
    return removed


# ---------------------------------------------------------------------------
# Pexels (فقط حالت SEND_PHOTOS)
# ---------------------------------------------------------------------------
def fetch_pexels_photo():
    for attempt in range(5):
        query = random.choice(SAD_QUERIES)
        page = random.randint(1, 10)
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                params={
                    "query": query, "per_page": 30, "page": page,
                    "orientation": "portrait", "size": "large",
                },
                headers={"Authorization": PEXELS_API_KEY},
                timeout=20,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            if not photos:
                continue
            photo = random.choice(photos)
            src = photo.get("src", {})
            url = src.get("large2x") or src.get("large") or src.get("original")
            save_state({"last_query": query})
            return url, photo.get("photographer", "Pexels"), query
        except requests.RequestException as e:
            logger.warning(f"Pexels attempt {attempt+1} failed ('{query}'): {e}")
            time_module.sleep(1)
    raise RuntimeError("نتونستم از Pexels عکس بگیرم — همه تلاش‌ها شکست خورد")


# ---------------------------------------------------------------------------
# هسته‌ی انتشار
# ---------------------------------------------------------------------------
async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text)
        except Exception:
            pass


async def publish_post(context, chat_id, consume_music=True):
    """ست کامل پست: متن (+عکس اگه SEND_PHOTOS فعاله) + استیکر + آهنگ.
    خروجی: دیکشنری وضعیت."""
    result = {"posted": False, "music": False, "sticker": False}

    caption = build_caption()
    if SEND_PHOTOS:
        url, photographer, query = await asyncio.to_thread(fetch_pexels_photo)
        full_caption = f"{caption}\n\n📷 {photographer} / Pexels"
        main_msg = await context.bot.send_photo(chat_id=chat_id, photo=url, caption=full_caption)
    else:
        main_msg = await context.bot.send_message(chat_id=chat_id, text=caption)
    result["posted"] = True

    if await send_random_sticker(context, chat_id, reply_to=main_msg.message_id):
        result["sticker"] = True

    track = get_next_track(peek=not consume_music)
    if track:
        await send_track(context, chat_id, track, reply_to=main_msg.message_id)
        result["music"] = True

    return result


async def post_combined_job(context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    if state.get("is_paused"):
        logger.info("Posting is paused, skipping job")
        return False
    try:
        result = await publish_post(context, CHANNEL_ID)
        save_state({"post_count": state.get("post_count", 0) + 1})
        logger.info(f"Post published: {result}")
        if not result["music"] and random.random() < 0.15:
            await notify_admins(
                context,
                "🎵 کتابخونه‌ی آهنگ خالیه! MP3 تو پیوی برام بفرست تا به پست‌ها اضافه بشه.",
            )
        return result
    except Exception as e:
        logger.exception("Post job failed")
        await notify_admins(
            context,
            f"⚠️ پست خودکار خطا داد: {e}\n(چک کن ربات ادمین چنل باشه)",
        )
        return False


# جاب‌های قدیمی سازگاری
async def post_photo_only_job(context: ContextTypes.DEFAULT_TYPE):
    if load_state().get("is_paused"):
        return
    if not PEXELS_API_KEY:
        await notify_admins(context, "برای پست عکس PEXELS_API_KEY لازمه.")
        return
    try:
        url, photographer, query = await asyncio.to_thread(fetch_pexels_photo)
        caption = f"{build_caption()}\n\n📷 {photographer} / Pexels"
        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=url, caption=caption)
        save_state({"post_count": load_state().get("post_count", 0) + 1})
    except Exception as e:
        logger.exception("post_photo_only_job failed")
        await notify_admins(context, f"⚠️ خطا در پست عکس: {e}")


async def post_music_only_job(context: ContextTypes.DEFAULT_TYPE):
    if load_state().get("is_paused"):
        return
    track = get_next_track()
    if not track:
        await notify_admins(context, "🎵 کتابخونه‌ی آهنگ خالیه.")
        return
    try:
        await send_track(context, CHANNEL_ID, track)
    except Exception as e:
        logger.exception("post_music_only_job failed")
        await notify_admins(context, f"⚠️ خطا در پست آهنگ: {e}")


# ---------------------------------------------------------------------------
# دستورات
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text(
            "سلام 🥀\nاین ربات شخصیه و دستوراتش فقط برای ادمینه."
        )
        return
    mode = "📸 عکس + متن" if SEND_PHOTOS else "📝 متن ساده"
    await update.message.reply_text(
        "سلام! Silent Ruins 🥀 روشنه.\n\n"
        f"حالت پست: {mode} + 🎭 استیکر + 🎧 آهنگ\n"
        f"چنل: {CHANNEL_ID}\n\n"
        "📋 دستورات:\n"
        "/post — پست فوری کامل\n"
        "/preview — پیش‌نمایش پست، فقط برای خودت (بدون انتشار و بدون سوختن نوبت آهنگ)\n"
        "/songs — لیست آهنگ‌ها\n"
        "/del <شماره> — حذف یه آهنگ\n"
        "/stickers — وضعیت کتابخونه‌ی استیکر\n"
        "/pause — توقف پست خودکار\n"
        "/resume — ادامه\n"
        "/stats — آمار کامل\n"
        "/id — آیدی عددی خودت\n\n"
        "➕ افزودن آهنگ: فایل MP3 رو همینجا بفرست (اسم خواننده و ترک از خود فایل خونده می‌شه)\n"
        "➕ افزودن استیکر: استیکر رو همینجا بفرست\n\n"
        f"⏰ پست‌های خودکار: {', '.join(POST_TIMES) if POST_INTERVAL_HOURS is None else f'هر {POST_INTERVAL_HOURS} ساعت'} ({TIMEZONE_STR})"
    )


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        await update.message.reply_text(f"🆔 آیدی عددی تو: {update.effective_user.id}")


async def post_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    m = await update.message.reply_text("⏳ دارم پست رو آماده می‌کنم...")
    result = await post_combined_job(context)
    if result and result.get("posted"):
        bits = []
        if SEND_PHOTOS:
            bits.append("عکس")
        else:
            bits.append("متن")
        if result["sticker"]:
            bits.append("استیکر")
        bits.append("آهنگ" if result["music"] else "❌ آهنگ نبود")
        await m.edit_text(f"✅ پست شد ({' + '.join(bits)})")
    else:
        await m.edit_text("❌ پست نشد — جزئیات خطا رو همینجا برات فرستادم. چک کن ربات ادمین چنل باشه.")


async def preview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(
        "👁 پیش‌نمایش پست بعدی (هیچی تو چنل نمی‌ره و نوبت آهنگ هم نمی‌سوزه):"
    )
    try:
        result = await publish_post(context, update.effective_chat.id, consume_music=False)
        if not result["music"]:
            await update.message.reply_text("🎵 کتابخونه‌ی آهنگ خالیه — MP3 بفرست تا تو پست‌ها باشه.")
        if not result["sticker"]:
            await update.message.reply_text("🎭 استیکری نداری — تو پیوی استیکر بفرست یا STICKER_SET ست کن.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا تو پیش‌نمایش: {e}")


async def photo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await post_photo_only_job(context)


async def music_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await post_music_only_job(context)


async def pause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    save_state({"is_paused": True})
    await update.message.reply_text("⏸ پست‌های خودکار متوقف شدن. ادامه: /resume")


async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    save_state({"is_paused": False})
    await update.message.reply_text("▶️ پست‌های خودکار دوباره فعال شد.")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    lib = load_library()
    state = load_state()
    mode = "📸 عکس + متن" if SEND_PHOTOS else "📝 متن ساده"
    lines = [
        "📊 آمار Silent Ruins 🥀",
        "",
        f"📢 چنل: {CHANNEL_ID}",
        f"🧩 حالت پست: {mode} + استیکر + آهنگ",
        f"⏯ وضعیت: {'⏸ متوقف' if state.get('is_paused') else '▶️ فعال'}",
        f"📮 پست‌های منتشرشده: {state.get('post_count', 0)}",
        f"📝 کپشن‌ها: {len(state.get('caption_used', []))}/{len(PERSIAN_SAD_CAPTIONS)} استفاده‌شده",
        "",
        f"🎵 آهنگ‌ها: {len(lib['tracks'])} (تو چرخه: {len(lib['unplayed'])})",
        f"🎭 استیکرها: {len(lib['stickers'])} داخل کتابخونه + {len(_pack_stickers())} از پک",
    ]
    if POST_INTERVAL_HOURS:
        lines.append(f"⏰ زمان‌بندی: هر {POST_INTERVAL_HOURS} ساعت")
    else:
        lines.append(f"⏰ زمان‌بندی: {', '.join(POST_TIMES)} ({TIMEZONE_STR})")
    try:
        jobs = [j for j in context.application.job_queue.jobs() if j.next_t]
        if jobs:
            nxt = min(j.next_t for j in jobs).astimezone(TIMEZONE)
            lines.append(f"⏭ پست بعدی: {nxt.strftime('%Y-%m-%d %H:%M')}")
    except Exception:
        pass
    await update.message.reply_text("\n".join(lines))


async def songs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    lib = load_library()
    if not lib["tracks"]:
        await update.message.reply_text("🎵 کتابخونه خالیه. یه فایل MP3 برام بفرست.")
        return
    total = len(lib["tracks"])
    start_idx = max(0, total - 30)
    lines = ["🎵 آهنگ‌های کتابخونه:\n"]
    for i in range(start_idx, total):
        t = lib["tracks"][i]
        performer = f" — {t['performer']}" if t.get("performer") else ""
        lines.append(f"{i+1}. {(t.get('title') or 'بدون‌نام')[:40]}{performer}")
    if start_idx > 0:
        lines.append(f"\n… {start_idx} تای اول نمایش داده نشدن")
    lines.append("\nبرای حذف: /del شماره")
    await update.message.reply_text("\n".join(lines))


async def del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("فرمت: /del شماره (شماره‌ها رو با /songs ببین)")
        return
    removed = delete_track_by_number(int(context.args[0]))
    if removed:
        await update.message.reply_text(f"🗑 «{removed.get('title') or 'بدون‌نام'}» حذف شد.")
    else:
        await update.message.reply_text("❌ این شماره تو کتابخونه نیست.")


async def stickers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    lib = load_library()
    await update.message.reply_text(
        f"🎭 کتابخونه‌ی استیکر:\n\n"
        f"• فرستاده‌شده توسط تو: {len(lib['stickers'])}\n"
        f"• از پک {STICKER_SET or '—'}: {len(_pack_stickers())}\n\n"
        "برای اضافه کردن، استیکر رو همینجا (پیوی) بفرست.\n"
        "برای پک عمومی، متغیر STICKER_SET رو به اسم پک ست کن."
    )


async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    state = load_state()
    lib = load_library()
    await update.message.reply_text(
        f"🎛 پنل مدیریت Silent Ruins 🥀\n\n"
        f"📢 چنل: {CHANNEL_ID}\n"
        f"وضعیت: {'⏸ متوقف' if state.get('is_paused') else '▶️ فعال'}\n"
        f"پست‌ها: {state.get('post_count', 0)} | آهنگ‌ها: {len(lib['tracks'])} | استیکرها: {len(lib['stickers']) + len(_pack_stickers())}\n\n"
        f"/post پست فوری\n"
        f"/preview پیش‌نمایش (فقط برای خودت)\n"
        f"/songs لیست آهنگ‌ها | /del حذف\n"
        f"/stickers وضعیت استیکرها\n"
        f"/pause /resume کنترل خودکار\n"
        f"/stats آمار کامل"
    )


# ---------------------------------------------------------------------------
# دریافت آهنگ و استیکر در پیوی
# ---------------------------------------------------------------------------
async def receive_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    msg = update.message
    media = None
    title = None
    performer = None
    ext = "mp3"

    if msg.audio:
        media = msg.audio
        title = msg.audio.title or msg.audio.file_name
        performer = msg.audio.performer
        if msg.audio.file_name and "." in msg.audio.file_name:
            ext = msg.audio.file_name.rsplit(".", 1)[-1]
    elif msg.document and (
        (msg.document.mime_type and "audio" in msg.document.mime_type)
        or (msg.document.file_name and msg.document.file_name.lower().endswith(
            (".mp3", ".m4a", ".ogg", ".flac", ".wav")))
    ):
        media = msg.document
        title = msg.document.file_name
        if "." in (title or ""):
            ext = title.rsplit(".", 1)[-1]
    elif msg.voice:
        media = msg.voice
        title = f"voice_{msg.voice.file_id[:8]}"
        ext = "ogg"
    else:
        return

    # کپشن به صورت «خواننده - ترک» هم پشتیبانی می‌شه
    if msg.caption and "-" in msg.caption and not performer:
        parts = [p.strip() for p in msg.caption.split("-", 1)]
        if parts[0]:
            performer = parts[0]
        if len(parts) > 1 and parts[1]:
            title = parts[1]

    title = (title or "بدون‌نام").strip()
    try:
        safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_", ".")).strip()[:80]
        safe_title = safe_title or f"track_{int(time_module.time())}"
        if not safe_title.lower().endswith(f".{ext}"):
            safe_title = f"{safe_title.rsplit('.', 1)[0]}.{ext}"
        dest_path = MUSIC_DIR / safe_title
        counter = 1
        base = dest_path.stem
        while dest_path.exists():
            dest_path = MUSIC_DIR / f"{base}_{counter}.{ext}"
            counter += 1

        tg_file = await context.bot.get_file(media.file_id)
        await tg_file.download_to_drive(custom_path=str(dest_path))

        lib = load_library()
        lib["tracks"].append({
            "file_id": media.file_id,
            "title": title,
            "performer": performer,
            "file_path": str(dest_path),
            "added_at": int(time_module.time()),
        })
        lib["unplayed"].append(media.file_id)
        save_library(lib)

        pr_line = f"🎤 {performer}\n" if performer else ""
        await update.message.reply_text(
            f"✅ ذخیره شد!\n{pr_line}🎵 {title}\n📚 کل کتابخونه: {len(lib['tracks'])} آهنگ"
        )
        logger.info(f"Saved track: {performer} - {title} -> {dest_path}")
    except Exception as e:
        logger.exception("Failed to save audio")
        await update.message.reply_text(f"❌ خطا در ذخیره آهنگ: {e}")


async def receive_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    st = update.message.sticker
    if not st:
        return
    lib = load_library()
    if any(s["file_id"] == st.file_id for s in lib["stickers"]):
        await update.message.reply_text("🎭 این استیکر رو از قبل دارم.")
        return
    lib["stickers"].append({"file_id": st.file_id, "emoji": st.emoji or ""})
    save_library(lib)
    await update.message.reply_text(
        f"✅ استیکر اضافه شد {st.emoji or ''} (مجموع: {len(lib['stickers'])})"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    threading.Thread(target=_run_health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("post", post_cmd))
    app.add_handler(CommandHandler("preview", preview_cmd))
    app.add_handler(CommandHandler("photo", photo_cmd))
    app.add_handler(CommandHandler("music", music_cmd))
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("status", stats_cmd))  # legacy
    app.add_handler(CommandHandler("songs", songs_cmd))
    app.add_handler(CommandHandler(["del", "delete"], del_cmd))
    app.add_handler(CommandHandler("stickers", stickers_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.AUDIO | filters.VOICE | filters.Document.ALL),
            receive_audio,
        )
    )
    app.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & filters.Sticker.ALL, receive_sticker)
    )

    jq = app.job_queue
    if jq is None:
        raise RuntimeError("job-queue نصب نیست: pip install 'python-telegram-bot[job-queue]'")

    if POST_INTERVAL_HOURS:
        jq.run_repeating(post_combined_job, interval=int(POST_INTERVAL_HOURS * 3600), first=30)
        logger.info(f"Scheduled repeating post every {POST_INTERVAL_HOURS}h")
    else:
        for t in POST_TIMES:
            try:
                h, m = map(int, t.split(":"))
                jq.run_daily(post_combined_job, time=dtime(hour=h, minute=m, tzinfo=TIMEZONE), name=f"post_{t}")
            except ValueError:
                logger.warning(f"Invalid POST_TIME '{t}'")
        for t in MUSIC_TIMES:
            try:
                h, m = map(int, t.split(":"))
                jq.run_daily(post_music_only_job, time=dtime(hour=h, minute=m, tzinfo=TIMEZONE), name=f"music_{t}")
            except ValueError:
                logger.warning(f"Invalid MUSIC_TIME '{t}'")

    if STICKER_SET:
        jq.run_once(refresh_sticker_pack, 3)

    logger.info(
        f"Silent Ruins 🥀 started | channel={CHANNEL_ID} | mode={'photos' if SEND_PHOTOS else 'text-only'} | "
        f"times={POST_TIMES} | interval={POST_INTERVAL_HOURS} | stickers_set={STICKER_SET or '-'}"
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
