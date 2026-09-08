"""
SilentRuins Bot 🥀 — Pro Edition
--------------------------------
ربات چنل‌های دپ/غمگین — هر پست یک «ستِ هم‌حس»:

    📸 عکس دارک و تک‌نفره  ←  کپشن فارسی سنگین + ایموجی مرتبط  ←  🎧 آهنگ مرتبط

- ۶ حس/موضوع: بارون، شب، تنهایی، دلتنگی، خستگی، ویرونه — عکس و متن از یک حس انتخاب می‌شن
- ایموجی ته هر کپشن، مرتبط با متنش (از استخر ایموجی همون حس)
- عکس‌ها دارک: سرچ با فیلتر رنگ مشکی + انتخاب تاریک‌ترین نتیجه بر اساس رنگ میانگین
- آهنگ‌ها هم حس‌دارن: موقع ارسال MP3 تو کپشن بنویس rain/شب/بارون/… تا وصل بشه
- امضای آخر هر پست: — silent ruins 🥀
- پنل مدیریت شیشه‌ای (دکمه‌ای) با /panel
- بدون تکرار: نه آهنگ تکراری، نه کپشن تکراری (تا اتمام دور)
- عکس خاموش هم می‌شه: SEND_PHOTOS=false → فقط متن + آهنگ
"""

import asyncio
import json
import logging
import os
import random
import threading
import time as time_module
from datetime import datetime, time as dtime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from database import Database
from content_engine import choose_mood, quality_score, remember_post, is_duplicate

import requests
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN تنظیم نشده — توی .env یا Variables هاست بذارش")


def _env_flag(name, default=False):
    return os.getenv(name, "true" if default else "false").strip().lower() in (
        "1", "true", "yes", "on",
    )


SEND_PHOTOS = _env_flag("SEND_PHOTOS", True)
PHOTO_CREDIT = _env_flag("PHOTO_CREDIT", False)

PEXELS_API_KEY = (
    os.getenv("PEXELS_API_KEY")
    or os.getenv("PIXEL_API_KEY")
    or os.getenv("UNSPLASH_ACCESS_KEY")
)
PHOTO_MODE = SEND_PHOTOS and bool(PEXELS_API_KEY)
if SEND_PHOTOS and not PEXELS_API_KEY:
    logging.warning("⚠️ SEND_PHOTOS روشنه ولی PEXELS_API_KEY نیست — فعلاً فقط متن پست می‌شه")

_admin_raw = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_USER_ID") or ""
ADMIN_IDS = set()
for part in str(_admin_raw).split(","):
    part = part.strip()
    if part.lstrip("-").isdigit():
        ADMIN_IDS.add(int(part))
if not ADMIN_IDS:
    logging.warning("⚠️ ADMIN_IDS تنظیم نشده — ربات به دستورات ادمین جواب نمی‌ده")

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

POST_TIMES_RAW = os.getenv("POST_TIMES") or os.getenv("PHOTO_TIMES") or "10:00,16:00,22:00,02:00"
POST_TIMES = [t.strip() for t in POST_TIMES_RAW.split(",") if t.strip()]
MUSIC_TIMES_RAW = os.getenv("MUSIC_TIMES", "")
MUSIC_TIMES = [t.strip() for t in MUSIC_TIMES_RAW.split(",") if t.strip()]

QUALITY_THRESHOLD = int(os.getenv("QUALITY_THRESHOLD", "85"))
MAX_CANDIDATES = max(3, int(os.getenv("MAX_CANDIDATES", "8")))

POST_INTERVAL_HOURS = os.getenv("POST_INTERVAL_HOURS")
try:
    POST_INTERVAL_HOURS = float(POST_INTERVAL_HOURS) if POST_INTERVAL_HOURS else None
except ValueError:
    POST_INTERVAL_HOURS = None

DATA_DIR = Path(os.getenv("DATA_DIR", ".")).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)
LIBRARY_FILE = DATA_DIR / "library.json"
STATE_FILE = DATA_DIR / "state.json"
DB_FILE = DATA_DIR / "silentruins.db"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
DB = Database(str(DB_FILE))
MUSIC_DIR = DATA_DIR / "music"
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# محتوا — حس‌محور
# ---------------------------------------------------------------------------
SIGNATURE = "— silent ruins 🥀"

MOODS = {
    "rain": {
        "fa": "بارون",
        "emoji": "🌧",
        "emojis": ["🌧", "☔", "🖤"],
        "queries": [
            "rain window night dark", "rainy street night reflection",
            "person rain night silhouette", "rain drops glass dark",
            "woman window rain dark", "alone rain night lights",
        ],
        "captions": [
            "بارون از آسمون نمیاد که زمین رو تمیز کنه؛ میاد که یادش بندازه.",
            "پشت شیشه نشستی و بارون؛ این وقتا کی قراره حالتو بپرسه؟",
            "یه بارونی بزن که هم شهر صاف بشه، هم حساب من.",
            "بارون سرای اوناس که نمی‌دونن چرا دلشون گرفته.",
            "تو بارونا فقط اونا خیس نمی‌شن که جایی برن؛ ما همون تو خونه غرقیم.",
            "صدای بارون یه جور حرف زدنه؛ فقط من بلدم ترجمه‌ش کنم.",
            "مگه میشه بارون بیاد و آدم هیچ‌کسی رو یادش نیاد؟",
            "زیر بارون راه رفتن، یه جور گریه‌ی بی‌صداست.",
        ],
    },
    "night": {
        "fa": "شب",
        "emoji": "🌃",
        "emojis": ["🌙", "🌃", "🖤"],
        "queries": [
            "silhouette man night lights", "city night dark minimal",
            "dark sky moon silhouette", "woman dark room window night",
            "empty road night lone figure", "night neon alley alone",
        ],
        "captions": [
            "شب که می‌شه، آدم با خودش رورو می‌شه؛ و خودش بدترین قراره.",
            "امشبم مثل دیشب: یه سقف، یه آهنگ، هزارتا فکر.",
            "نیمه‌شبا همه‌چیز صادق‌تره؛ حتی تنهایی.",
            "ماه که می‌ره، بغض‌ها پخش می‌شن.",
            "شب طولانی‌ترین جوابِ سوالای بی‌جوابه.",
            "ساعت سه‌ی شب و یه آهنگ تکراری.",
            "خواب برای اوناست که دار می‌شن از بیداری.",
            "تو تاریکی همه‌ی رنگا یه‌شکلن.",
            "بعضی ستاره‌ها هیچوقت نمی‌رسن به آسمون بعضی‌ها.",
        ],
    },
    "lonely": {
        "fa": "تنهایی",
        "emoji": "🚶",
        "emojis": ["🚶", "🌫", "🖤"],
        "queries": [
            "man silhouette alone dark", "person sitting alone night",
            "woman alone window silhouette", "lone bench night fog",
            "figure walking darkness", "single person dark minimal",
        ],
        "captions": [
            "بلد بودن آدم‌ها خیلی مهم‌تر از دوست داشتنشونه.",
            "تنها نشستن با خودت یه قراره؛ قراری که هیچ‌کی لغوش نمی‌کنه.",
            "تنهایی بد نیست؛ بده وقتی که نمی‌تونی به هیچ‌کس بگی خستی.",
            "تو جمع پر بحث، فقط خودت شنونده‌ی خودتی.",
            "تنهایی یه مهارته؛ بعضی‌هامون زودتر یاد گرفتیم.",
            "سفره‌ی تک‌نفره همیشه زودتر پهن و جمع می‌شه.",
            "تو شلوغی هم وقتی کسیو نداری، صدات دور می‌ره.",
            "همه رفتن و دنیا ادامه داشت؛ منم بی‌صدا موندم.",
        ],
    },
    "love": {
        "fa": "دلتنگی",
        "emoji": "🥀",
        "emojis": ["🥀", "💔", "🖤"],
        "queries": [
            "withered rose dark background", "old photograph dark aesthetic",
            "letter candle dark room", "empty bed night dark",
            "single red rose black", "silhouette couple distance night",
        ],
        "captions": [
            "تابستون فصل عجیبیه؛ همیشه یا یه آدم مهم میاد تو زندگیت، یا یه آدم مهم از زندگیت می‌ره.",
            "همیشه اون آدمی که برای من نبودی، برا بقیه بودی.",
            "رفتن کار اونا بود، یاد کردن کار ما.",
            "یکی می‌ره و دنیا ادامه داره؛ این ظالم‌ترین بخش قصه‌ست.",
            "بعضی آدما می‌رن ولی صداشون می‌مونه.",
            "دلتنگی یعنی نه میشه برگردوندت، نه میشه ردت کرد.",
            "قبلنا فاصله یعنی کیلومتر؛ حالا یعنی اونی که هست و نیست.",
            "همه می‌رسن به وقتی که باید فراموش کنن؛ بعضی‌هامون نه.",
        ],
    },
    "tired": {
        "fa": "خستگی",
        "emoji": "🕯",
        "emojis": ["🕯", "🌫", "🖤"],
        "queries": [
            "tired eyes close up dark", "smoke night silhouette man",
            "candle flame dark room", "person hood alone dark",
            "broken mirror silhouette", "silhouette head down dark",
        ],
        "captions": [
            "ترسناک‌ترین اتفاقی که می‌تونه برای یه نفر بیوفته «بی‌تفاوت» شدنه.",
            "همه‌چیز به وقتش قشنگه؛ هیچ‌چیزی بعدا قشنگ نیس.",
            "حجم چیزایی که باید می‌گفتم و نگفتم، از خود من بیشتره.",
            "خستگی که مال دل باشه، با یه خواب رد نمی‌شه.",
            "بعضی روزا همون بیدار شدن، بزرگ‌ترین کار روزه.",
            "یه جا به بعد فقط تحمل می‌کنی؛ زندگی نمی‌کنی.",
            "بغض‌های انباشته رو آخرش یه آهنگ تخلیه می‌کنه.",
            "آدم وقتی از خودش می‌ره کنار، دیگه همه‌چی بی‌صداست.",
        ],
    },
    "ruins": {
        "fa": "ویرونه",
        "emoji": "🏚",
        "emojis": ["🏚", "🍂", "🌫"],
        "queries": [
            "abandoned house night fog", "dark forest lone tree",
            "old ruins moonlight", "misty valley dark",
            "gothic window dark", "dead tree dark sky",
        ],
        "captions": [
            "نگران اومدن پاییز باشم؟ مگه تو باغ ما گلی باقی‌مونده؟ لاله‌های وطن توی زمستون از دست رفتن.",
            "هر دیوار لق یه روزی بهار دیده.",
            "روزگار از خونه‌های قدیمی رد می‌شه و هیچیو باهاش نمی‌بره.",
            "تو مه هیچی معلوم نی؛ درست مثل بعضی آدما که همین‌جور رفتن.",
            "هر خرابه‌ای یه روزی خونه‌ی کسی بوده.",
            "پاییز مواظب گلا نیست؛ مواظب آدما هم نیستیم.",
            "جایی که چراغا خاموشن، خاطره‌ها چراغ خودشون می‌شن.",
            "سکوت این باغ یه زمانی شکوفه بوده.",
        ],
    },
}

# کلیدواژه‌های تشخیص حس آهنگ (فارسی، انگلیسی، فینگلیش)
MOOD_ALIASES = {
    "rain": ["rain", "بارون", "باران", "barun", "baran", "baroon"],
    "night": ["night", "شب", "shab"],
    "lonely": ["lonely", "تنها", "tanha", "tanhai"],
    "love": ["love", "دلتنگ", "عشق", "خاطره", "deltang", "eshgh", "khatere"],
    "tired": ["tired", "خسته", "خستگ", "khaste", "khasste"],
    "ruins": ["ruins", "ویرونه", "خرابه", "جنگل", "مه", "virane", "kharabe", "jangal"],
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("silent_ruins_bot")


# ---------------------------------------------------------------------------
# Health server (برای هاست‌هایی مثل Render)
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
    data = {}
    if LIBRARY_FILE.exists():
        try:
            data = json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data.setdefault("tracks", [])
    data.setdefault("unplayed", [])
    return data


def save_library(data):
    LIBRARY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for track in data.get("tracks", []):
        try:
            DB.track_upsert(track)
        except Exception:
            logger.exception("Failed to sync track to database")


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"is_paused": False, "post_count": 0}


def save_state(patch):
    state = load_state()
    state.update(patch)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_admin(update: Update) -> bool:
    return bool(update.effective_user) and update.effective_user.id in ADMIN_IDS


# ---------------------------------------------------------------------------
# کپشن — متن هم‌حس + ایموجی مرتبط، بدون تکرار
# ---------------------------------------------------------------------------
def choose_caption(mood, state=None):
    """Peek a caption without mutating state; publish commits the chosen caption once."""
    pool = MOODS[mood]["captions"]
    state = state or load_state()
    used_map = state.get("caption_used", {})
    if not isinstance(used_map, dict):
        used_map = {}
    used = set(used_map.get(mood, []))
    remaining = [i for i in range(len(pool)) if i not in used]
    if not remaining:
        remaining = list(range(len(pool)))
    idx = random.choice(remaining)
    return idx, pool[idx]


def commit_caption(mood, idx):
    state = load_state()
    used_map = state.get("caption_used", {})
    if not isinstance(used_map, dict):
        used_map = {}
    used = set(used_map.get(mood, []))
    used.add(int(idx))
    pool_len = len(MOODS[mood]["captions"])
    # Start a new caption cycle after all captions have been used.
    if len(used) >= pool_len:
        used = set()
    used_map[mood] = sorted(used)
    save_state({"caption_used": used_map})


def pick_caption(mood):
    idx, text = choose_caption(mood)
    commit_caption(mood, idx)
    return text


def build_main_caption(mood, state=None, peek=True):
    """Build caption; by default do not mutate state until a post is committed."""
    if peek:
        idx, text = choose_caption(mood, state)
        return f"{text} {random.choice(MOODS[mood]['emojis'])}\n\n{SIGNATURE}", idx
    text = pick_caption(mood)
    return f"{text} {random.choice(MOODS[mood]['emojis'])}\n\n{SIGNATURE}", None


# ---------------------------------------------------------------------------
# آهنگ — چرخه‌ی بدون تکرار + اولویت آهنگ هم‌حس با عکس
# ---------------------------------------------------------------------------
def get_next_track(mood=None, peek=False):
    lib = load_library()
    if not lib["tracks"]:
        return None

    if peek:
        if mood:
            same_mood = [t for t in lib["tracks"] if t.get("mood") == mood]
            if same_mood:
                return random.choice(same_mood)
        return random.choice(lib["tracks"])

    if not lib["unplayed"]:
        lib["unplayed"] = [t["file_id"] for t in lib["tracks"]]
        random.shuffle(lib["unplayed"])

    chosen = lib["unplayed"][0]
    if mood:
        mood_by_id = {t["file_id"]: t.get("mood") for t in lib["tracks"]}
        for fid in lib["unplayed"]:
            if mood_by_id.get(fid) == mood:
                chosen = fid
                break

    lib["unplayed"].remove(chosen)
    save_library(lib)
    for t in lib["tracks"]:
        if t["file_id"] == chosen:
            return t
    return {"file_id": chosen, "title": "بدون‌نام"}


def consume_track(track):
    """Consume exactly one selected track from the current no-repeat cycle."""
    if not track:
        return
    lib = load_library()
    fid = track.get("file_id")
    if not fid:
        return
    if fid not in [t.get("file_id") for t in lib.get("tracks", [])]:
        return
    if not lib.get("unplayed"):
        lib["unplayed"] = [t["file_id"] for t in lib["tracks"]]
        random.shuffle(lib["unplayed"])
    if fid in lib["unplayed"]:
        lib["unplayed"].remove(fid)
    save_library(lib)


def build_audio_caption(track):
    title = (track.get("title") or "").strip() or "بدون‌نام"
    performer = (track.get("performer") or "").strip()
    lines = []
    if performer:
        lines.append(f"🎤 {performer}")
    lines.append(f"🎵 {title}")
    lines.append("")
    lines.append(SIGNATURE)
    return "\n".join(lines)


async def send_track(context, chat_id, track, reply_to=None):
    caption = build_audio_caption(track)
    try:
        DB.track_played(track.get("file_id"))
    except Exception:
        pass
    file_path = track.get("file_path")
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
    lib = load_library()
    if n < 1 or n > len(lib["tracks"]):
        return None
    removed = lib["tracks"].pop(n - 1)
    lib["unplayed"] = [f for f in lib["unplayed"] if f != removed["file_id"]]
    save_library(lib)
    try:
        DB.track_deleted(removed.get("file_id"))
    except Exception:
        pass
    fp = removed.get("file_path")
    if fp:
        try:
            Path(fp).unlink(missing_ok=True)
        except Exception:
            pass
    return removed


# ---------------------------------------------------------------------------
# Pexels — دارک: فیلتر رنگ مشکی + انتخاب تاریک‌ترین‌ها
# ---------------------------------------------------------------------------
def _luminance(hex_color):
    """روشنایی رنگ میانگین عکس (۰=تاریک، ۲۵۵=روشن)."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    except Exception:
        return 128


def _pick_dark_photo(photos, excluded_urls=None):
    """از بین نتایج، تاریک‌ترین‌ها انتخاب می‌شن (فضای دارک مینیمال)."""
    excluded_urls = set(excluded_urls or [])
    fresh = [p for p in photos if p.get("src", {}).get("large2x") not in excluded_urls and p.get("src", {}).get("large") not in excluded_urls and p.get("src", {}).get("original") not in excluded_urls]
    if fresh:
        photos = fresh
    scored = [(_luminance(p.get("avg_color") or "#808080"), p) for p in photos]
    very_dark = [p for lum, p in scored if lum < 55]
    if very_dark:
        return random.choice(very_dark)
    darkest_half = sorted(scored, key=lambda x: x[0])[: max(1, len(scored) // 2)]
    return random.choice(darkest_half)[1]


def fetch_pexels_photo(mood, state=None):
    queries = MOODS[mood]["queries"]
    plans = [
        (random.choice(queries), "black", random.randint(1, 8)),
        (random.choice(queries), "black", 1),
        (random.choice(queries), None, random.randint(1, 8)),
        (random.choice(queries), "black", random.randint(1, 8)),
        ("dark moody aesthetic", "black", random.randint(1, 5)),
        ("dark night silhouette", None, 1),
    ]
    for query, color, page in plans:
        params = {
            "query": query, "per_page": 30, "page": page,
            "orientation": "portrait", "size": "large",
        }
        if color:
            params["color"] = color
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                params=params,
                headers={"Authorization": PEXELS_API_KEY},
                timeout=20,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            if not photos:
                continue
            photo = _pick_dark_photo(photos, (state or {}).get("recent_image_urls", []))
            src = photo.get("src", {})
            url = src.get("large2x") or src.get("large") or src.get("original")
            save_state({"last_query": query})
            return url, photo.get("photographer", "Pexels"), query, photo
        except requests.RequestException as e:
            logger.warning(f"Pexels attempt failed ('{query}' p{page}): {e}")
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
    """Build and publish a coherent SilentRuins set with mood, matching, anti-repeat and quality scoring."""
    state = load_state()
    result = {"posted": False, "music": False, "mood": None, "quality": None}

    best = None
    for _ in range(MAX_CANDIDATES):
        mood = choose_mood(MOODS, state, datetime.now(TIMEZONE).hour)
        caption, caption_idx = build_main_caption(mood, state=state, peek=True)
        photo_meta = None
        url = None
        photographer = None
        query = None
        if PHOTO_MODE:
            try:
                url, photographer, query, photo = await asyncio.to_thread(fetch_pexels_photo, mood, state)
                photo_meta = {
                    "query": query,
                    "alt": photo.get("alt", ""),
                    "luminance": _luminance(photo.get("avg_color") or "#808080"),
                }
            except Exception as exc:
                logger.warning("Photo candidate failed: %s", exc)
        track = get_next_track(mood=mood, peek=True)
        score = quality_score(mood, caption, track, photo_meta, MOODS, MOOD_ALIASES)
        duplicate = is_duplicate(state, mood, caption, track, url)
        candidate = {
            "overall": score["overall"],
            "mood": mood,
            "caption": caption,
            "caption_idx": caption_idx,
            "track": track,
            "url": url,
            "photographer": photographer,
            "score": score,
            "duplicate": duplicate,
        }
        if not duplicate and (best is None or candidate["overall"] > best["overall"]):
            best = candidate
        if best and best["overall"] >= QUALITY_THRESHOLD:
            break

    if best is None:
        raise RuntimeError("نتونستم یک ترکیب تازه و غیرتکراری بسازم")

    # A quality threshold is a real publishing gate, not just a target.
    # Never publish a weak candidate in production. Preview can still show it.
    if consume_music and best["overall"] < QUALITY_THRESHOLD:
        raise RuntimeError(
            f"هیچ ترکیب باکیفیتی پیدا نشد (بهترین امتیاز: {best['overall']}/100، حداقل: {QUALITY_THRESHOLD}/100)"
        )

    mood = best["mood"]
    caption = best["caption"]
    caption_idx = best["caption_idx"]
    track = best["track"]
    url = best["url"]
    photographer = best["photographer"]
    score = best["score"]

    # Preview mode never commits library/state changes.
    if url:
        photo_credit = f"\n📷 {photographer}" if PHOTO_CREDIT else ""
        main_msg = await context.bot.send_photo(chat_id=chat_id, photo=url, caption=caption + photo_credit)
    else:
        main_msg = await context.bot.send_message(chat_id=chat_id, text=caption)

    result["posted"] = True
    result["quality"] = score
    result["mood"] = mood

    if track:
        await send_track(context, chat_id, track, reply_to=main_msg.message_id)
        result["music"] = True

    if consume_music:
        if caption_idx is not None:
            commit_caption(mood, caption_idx)
        if track:
            consume_track(track)
        state = remember_post(state, mood, caption, track, url, score)
        state["last_mood"] = mood
        save_state(state)
        try:
            DB.event("quality_score", str({"mood": mood, **score}))
            DB.post_start(mood, caption, track.get("file_id") if track else None)
        except Exception:
            logger.exception("Failed to write post analytics")
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
        if not result["music"] and random.random() < 0.2:
            await notify_admins(
                context,
                "🎵 کتابخونه‌ی آهنگ خالیه! MP3 تو پیوی برام بفرست تا به پست‌ها اضافه بشه.",
            )
        return result
    except Exception as e:
        logger.exception("Post job failed")
        try:
            DB.post_failed(None, None, e)
            DB.event("post_failed", str(e))
        except Exception:
            pass
        await notify_admins(context, f"⚠️ پست خودکار خطا داد: {e}\n(چک کن ربات ادمین چنل باشه)")
        return False


def _post_result_text(result):
    if not result or not result.get("posted"):
        return "❌ پست نشد — چک کن ربات ادمین چنل باشه."
    mood = result["mood"]
    mood_fa = f"{MOODS[mood]['fa']} {MOODS[mood]['emoji']}" if mood else "؟"
    bits = ["عکس" if PHOTO_MODE else "متن"]
    bits.append("آهنگ" if result["music"] else "بدون آهنگ (کتابخونه خالیه)")
    quality = result.get("quality") or {}
    quality_line = f"\n⭐ کیفیت ست: {quality.get('overall', "?")}/100" if quality else ""
    return f"✅ پست شد — حس: {mood_fa}\n{' + '.join(bits)}{quality_line}"


# جاب‌های سازگاری قدیمی
async def post_photo_only_job(context: ContextTypes.DEFAULT_TYPE):
    if load_state().get("is_paused"):
        return
    if not PEXELS_API_KEY:
        await notify_admins(context, "برای پست عکس PEXELS_API_KEY لازمه.")
        return
    mood = random.choice(list(MOODS.keys()))
    try:
        url, photographer, query, _photo = await asyncio.to_thread(fetch_pexels_photo, mood, load_state())
        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=url, caption=build_main_caption(mood))
        save_state({"post_count": load_state().get("post_count", 0) + 1, "last_mood": mood})
    except Exception as e:
        logger.exception("post_photo_only_job failed")
        await notify_admins(context, f"⚠️ خطا در پست عکس: {e}")


async def post_music_only_job(context: ContextTypes.DEFAULT_TYPE):
    if load_state().get("is_paused"):
        return
    track = get_next_track(mood=load_state().get("last_mood"))
    if not track:
        await notify_admins(context, "🎵 کتابخونه‌ی آهنگ خالیه.")
        return
    try:
        await send_track(context, CHANNEL_ID, track)
    except Exception as e:
        logger.exception("post_music_only_job failed")
        await notify_admins(context, f"⚠️ خطا در پست آهنگ: {e}")


# ---------------------------------------------------------------------------
# متن‌ها (مشترک دستورات و پنل)
# ---------------------------------------------------------------------------
def _stats_text(context=None):
    lib = load_library()
    state = load_state()
    tagged = len([t for t in lib["tracks"] if t.get("mood")])
    last_mood = state.get("last_mood")
    lines = [
        "📊 آمار Silent Ruins 🥀",
        "",
        f"📢 چنل: {CHANNEL_ID}",
        f"⏯ وضعیت: {'⏸ متوقف' if state.get('is_paused') else '▶️ فعال'}",
        f"📮 پست‌ها: {state.get('post_count', 0)}",
        f"🧩 حالت: {'📸 عکس + متن' if PHOTO_MODE else '📝 متن ساده'} + 🎧",
    ]
    if last_mood:
        lines.append(f"🌗 آخرین حس: {MOODS[last_mood]['fa']} {MOODS[last_mood]['emoji']}")
    qscore = state.get("last_quality_score") or {}
    if qscore:
        lines.append(f"⭐ کیفیت آخرین ست: {qscore.get('overall', "?")}/100  · متن {qscore.get('text', "?")} · عکس {qscore.get('image', "?")} · آهنگ {qscore.get('music', "?")}")
    lines.append(f"🎵 آهنگ‌ها: {len(lib['tracks'])} (حس‌دار: {tagged}؛ تو چرخه: {len(lib['unplayed'])})")
    try:
        a = DB.summary()
        lines.append(f"📈 ۲۴ ساعت اخیر: {a['today']} پست موفق • خطا: {a['failed']}")
        if a["moods"]:
            lines.append("🌗 حس‌های پرتکرار: " + "، ".join(f"{MOODS.get(x['mood'], {}).get('fa', x['mood'])} ({x['c']})" for x in a["moods"][:3]))
    except Exception:
        pass
    if POST_INTERVAL_HOURS:
        lines.append(f"⏰ هر {POST_INTERVAL_HOURS} ساعت")
    else:
        lines.append(f"⏰ {', '.join(POST_TIMES)} ({TIMEZONE_STR})")
    if context is not None:
        try:
            jobs = [j for j in context.application.job_queue.jobs() if j.next_t]
            if jobs:
                nxt = min(j.next_t for j in jobs).astimezone(TIMEZONE)
                lines.append(f"⏭ پست بعدی: {nxt.strftime('%Y-%m-%d %H:%M')}")
        except Exception:
            pass
    return "\n".join(lines)


def _songs_text():
    lib = load_library()
    if not lib["tracks"]:
        return "🎵 کتابخونه خالیه. یه MP3 برام بفرست 🥀"
    total = len(lib["tracks"])
    start_idx = max(0, total - 30)
    lines = ["🎵 آهنگ‌های کتابخونه:\n"]
    for i in range(start_idx, total):
        t = lib["tracks"][i]
        performer = f" — {t['performer']}" if t.get("performer") else ""
        mood = f" [{MOODS[t['mood']]['fa']}]" if t.get("mood") in MOODS else ""
        lines.append(f"{i+1}. {(t.get('title') or 'بدون‌نام')[:35]}{performer}{mood}")
    if start_idx > 0:
        lines.append(f"\n… {start_idx} تای اول نمایش داده نشدن")
    lines.append("\nحذف: /del شماره")
    return "\n".join(lines)


_MOODS_FA = "، ".join(m["fa"] + " " + m["emoji"] for m in MOODS.values())

HELP_TEXT = (
    "سلام! Silent Ruins 🥀\n\n"
    "هر پست یه ستِ هم‌حسه: عکس دپ ← کپشن سنگین + ایموجی مرتبط ← آهنگ هم‌حس\n"
    f"حس‌ها: {_MOODS_FA}\n\n"
    "➕ آهنگ: MP3 رو همینجا بفرست (می‌تونی موقع ارسال تو کپشن حسش رو هم بنویسی: "
    "بارون / شب / تنهایی / دلتنگی / خستگی / ویرونه)\n\n"
    "دستورات:\n"
    "/panel — پنل شیشه‌ای مدیریت 🎛\n"
    "/post پست فوری • /preview پیش‌نمایش\n"
    "/songs آهنگ‌ها • /findsong جستجوی آهنگ • /del حذف آهنگ\n"
    "/pause توقف • /resume ادامه • /stats آمار • /report گزارش\n"
    "/schedule زمان‌بندی یک پست • /jobs زمان‌های فعال • /backup بکاپ • /id آیدی\n"
    "/mood وضعیت حس/امتیاز آخرین ست"
)


# ---------------------------------------------------------------------------
# پنل شیشه‌ای
# ---------------------------------------------------------------------------
def _panel_text():
    state = load_state()
    lib = load_library()
    return (
        "🎛 پنل مدیریت Silent Ruins 🥀\n"
        "— — — — — — — — —\n"
        f"📢 {CHANNEL_ID}\n"
        f"{'⏸ متوقفه' if state.get('is_paused') else '▶️ فعاله'}  •  📮 {state.get('post_count', 0)} پست\n"
        f"🎵 {len(lib['tracks'])} آهنگ\n"
        "— — — — — — — — —"
    )


def _panel_markup():
    paused = load_state().get("is_paused")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🥀 پست فوری", callback_data="p:post")],
        [InlineKeyboardButton("👁 پیش‌نمایش", callback_data="p:preview")],
        [
            InlineKeyboardButton("📊 آمار", callback_data="p:stats"),
            InlineKeyboardButton("🎵 آهنگ‌ها", callback_data="p:songs"),
        ],
        [
            InlineKeyboardButton(
                "▶️ ادامه‌ی پست خودکار" if paused else "⏸ توقف پست خودکار",
                callback_data="p:resume" if paused else "p:pause",
            )
        ],
        [
            InlineKeyboardButton("📈 گزارش", callback_data="p:report"),
            InlineKeyboardButton("⏰ Jobها", callback_data="p:jobs"),
        ],
        [InlineKeyboardButton("💾 بکاپ", callback_data="p:backup")],
    ])


async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(_panel_text(), reply_markup=_panel_markup())


async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.from_user or q.from_user.id not in ADMIN_IDS:
        if q:
            await q.answer("فقط ادمینه 🥀", show_alert=True)
        return
    data = q.data or ""

    if data in ("p:pause", "p:resume"):
        save_state({"is_paused": data == "p:pause"})
        await q.answer("⏸ متوقف شد" if data == "p:pause" else "▶️ فعال شد")
        try:
            await q.edit_message_text(_panel_text(), reply_markup=_panel_markup())
        except Exception:
            pass
    elif data == "p:stats":
        await q.answer()
        await q.message.reply_text(_stats_text(context))
    elif data == "p:songs":
        await q.answer()
        await q.message.reply_text(_songs_text())
    elif data == "p:preview":
        await q.answer("👁 داره ساخته می‌شه…")
        try:
            result = await publish_post(context, q.message.chat_id, consume_music=False)
            if not result["music"]:
                await q.message.reply_text("🎵 کتابخونه‌ی آهنگ خالیه — MP3 بفرست.")
        except Exception as e:
            await q.message.reply_text(f"❌ خطا تو پیش‌نمایش: {e}")
    elif data == "p:post":
        await q.answer("⏳ در حال انتشار…")
        result = await post_combined_job(context)
        await q.message.reply_text(_post_result_text(result))
    elif data == "p:report":
        await q.answer()
        a = DB.summary()
        text = (
            f"📊 گزارش\n📮 موفق: {a['posts']}\n"
            f"📈 ۲۴ ساعت: {a['today']}\n"
            f"❌ خطا: {a['failed']}\n"
            f"🎵 آهنگ: {a['tracks']}"
        )
        await q.message.reply_text(text)
    elif data == "p:jobs":
        await q.answer()
        jobs = context.job_queue.jobs()
        lines = ["⏰ Jobهای فعال:"] + [
            f"• {j.name or 'بدون‌نام'} → {j.next_t.astimezone(TIMEZONE).strftime('%Y-%m-%d %H:%M') if j.next_t else '؟'}"
            for j in jobs
        ]
        await q.message.reply_text("\n".join(lines) if jobs else "📭 هیچ Job فعالی وجود نداره.")
    elif data == "p:backup":
        await q.answer("💾 در حال ساخت بکاپ…")
        stamp = datetime.now(TIMEZONE).strftime("%Y%m%d_%H%M%S")
        target = BACKUP_DIR / f"silentruins_backup_{stamp}.zip"
        import zipfile
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for f in [LIBRARY_FILE, STATE_FILE, DB_FILE]:
                if f.exists():
                    z.write(f, arcname=f.name)
        DB.event("backup_created", str(target))
        with target.open("rb") as f:
            await q.message.reply_document(document=f, filename=target.name, caption="💾 بکاپ آماده شد.")


# ---------------------------------------------------------------------------
# دستورات
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("این ربات شخصیه 🥀")
        return
    await update.message.reply_text(HELP_TEXT)


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        await update.message.reply_text(f"🆔 آیدی عددی تو: {update.effective_user.id}")


async def post_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    m = await update.message.reply_text("⏳ در حال آماده‌سازی پست…")
    result = await post_combined_job(context)
    await m.edit_text(_post_result_text(result))


async def preview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("👁 پیش‌نمایش (تو چنل نمی‌ره، نوبت آهنگ هم نمی‌سوزه):")
    try:
        result = await publish_post(context, update.effective_chat.id, consume_music=False)
        mood = result["mood"]
        quality = result.get("quality") or {}
        await update.message.reply_text(
            f"🌗 حس این پست: {MOODS[mood]['fa']} {MOODS[mood]['emoji']}\n"
            f"⭐ کیفیت: {quality.get('overall', '?')}/100"
        )
        if not result["music"]:
            await update.message.reply_text("🎵 کتابخونه‌ی آهنگ خالیه — MP3 بفرست.")
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
    await update.message.reply_text("▶️ پست‌های خودکار فعال شد.")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(_stats_text(context))


async def songs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(_songs_text())


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


# ---------------------------------------------------------------------------
# قابلیت‌های مدیریتی v3 — زمان‌بندی پویا، جستجو، بکاپ و گزارش
# ---------------------------------------------------------------------------
def _parse_schedule(value):
    """Parse YYYY-MM-DD HH:MM or HH:MM into timezone-aware datetime."""
    value = " ".join(value.strip().split())
    fmts = ["%Y-%m-%d %H:%M", "%H:%M"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == "%H:%M":
                now = datetime.now(TIMEZONE)
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
                if dt <= now:
                    dt += timedelta(days=1)
            return dt.replace(tzinfo=TIMEZONE)
        except ValueError:
            continue
    return None


async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("فرمت: /schedule 23:30\nیا: /schedule 2026-09-09 23:30")
        return
    raw = " ".join(context.args)
    when = _parse_schedule(raw)
    if not when:
        await update.message.reply_text("❌ زمان نامعتبره. مثال: /schedule 23:30")
        return
    if when <= datetime.now(TIMEZONE):
        await update.message.reply_text("❌ این زمان گذشته است.")
        return
    context.job_queue.run_once(post_combined_job, when, name=f"once_{int(when.timestamp())}")
    DB.event("schedule_created", when.isoformat())
    await update.message.reply_text(f"⏰ پست زمان‌بندی شد برای {when.strftime('%Y-%m-%d %H:%M')} ({TIMEZONE_STR})")


async def jobs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    jobs = context.job_queue.jobs()
    if not jobs:
        await update.message.reply_text("📭 هیچ Job فعالی وجود نداره.")
        return
    lines = ["⏰ Jobهای فعال:"]
    for j in jobs:
        nxt = j.next_t.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M") if j.next_t else "؟"
        lines.append(f"• {j.name or 'بدون‌نام'} → {nxt}")
    await update.message.reply_text("\n".join(lines))


async def find_song_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    q = " ".join(context.args).strip().lower()
    if not q:
        await update.message.reply_text("فرمت: /findsong کلمه")
        return
    lib = load_library()
    hits = [t for t in lib["tracks"] if q in (t.get("title") or "").lower() or q in (t.get("performer") or "").lower() or q in (t.get("mood") or "").lower()]
    if not hits:
        await update.message.reply_text("🔎 چیزی پیدا نشد.")
        return
    lines = [f"🔎 {len(hits)} نتیجه:"]
    for t in hits[:30]:
        mood = MOODS.get(t.get("mood"), {}).get("fa", "بدون حس")
        lines.append(f"• {t.get('title') or 'بدون‌نام'} — {t.get('performer') or 'ناشناخته'} [{mood}]")
    await update.message.reply_text("\n".join(lines))


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    a = DB.summary()
    lines = ["📊 گزارش SilentRuins v2", "", f"📮 کل پست موفق: {a['posts']}", f"📈 پست موفق ۲۴ ساعت اخیر: {a['today']}", f"❌ پست ناموفق: {a['failed']}", f"🎵 آهنگ‌ها: {a['tracks']}"]
    if a["top_tracks"]:
        lines += ["", "🔥 آهنگ‌های پرتکرار:"]
        lines += [f"• {x['title'] or 'بدون‌نام'} — {x['play_count']} بار" for x in a["top_tracks"]]
    await update.message.reply_text("\n".join(lines))


async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    stamp = datetime.now(TIMEZONE).strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"silentruins_backup_{stamp}.zip"
    import zipfile
    files_to_backup = [LIBRARY_FILE, STATE_FILE, DB_FILE]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files_to_backup:
            if f.exists():
                z.write(f, arcname=f.name)
    DB.event("backup_created", str(target))
    with target.open("rb") as f:
        await update.message.reply_document(document=f, filename=target.name, caption="💾 بکاپ آماده شد.")


# ---------------------------------------------------------------------------
# دریافت آهنگ
# ---------------------------------------------------------------------------
def _detect_mood(text):
    text = (text or "").lower()
    for key, aliases in MOOD_ALIASES.items():
        if any(a in text for a in aliases):
            return key
    return None


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

    caption_text = msg.caption or ""
    mood = _detect_mood(caption_text)

    if caption_text and "-" in caption_text and not performer:
        parts = [p.strip() for p in caption_text.split("-", 1)]
        if parts[0] and not _detect_mood(parts[0]):
            performer = parts[0]
        if len(parts) > 1 and parts[1] and not _detect_mood(parts[1]):
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
            "mood": mood,
            "file_path": str(dest_path),
            "added_at": int(time_module.time()),
        })
        lib["unplayed"].append(media.file_id)
        save_library(lib)

        pr_line = f"🎤 {performer}\n" if performer else ""
        mood_line = f"🌗 حس: {MOODS[mood]['fa']} {MOODS[mood]['emoji']}\n" if mood else ""
        await update.message.reply_text(
            f"✅ ذخیره شد!\n{pr_line}🎵 {title}\n{mood_line}📚 {len(lib['tracks'])} آهنگ"
        )
        logger.info(f"Saved track: {performer} - {title} (mood={mood}) -> {dest_path}")
    except Exception as e:
        logger.exception("Failed to save audio")
        await update.message.reply_text(f"❌ خطا در ذخیره آهنگ: {e}")


async def mood_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    state = load_state()
    recent = state.get("recent_moods", []) or []
    score = state.get("last_quality_score") or {}
    lines = ["🌗 Mood Engine", "", f"آخرین حس: {MOODS.get(state.get('last_mood'), {}).get('fa', '—')}"]
    lines.append(f"چرخش اخیر: {' → '.join(MOODS[m]['fa'] for m in recent if m in MOODS) or '—'}")
    if score:
        lines += ["", f"⭐ امتیاز آخرین ست: {score.get('overall', '?')}/100", f"متن: {score.get('text', '?')}/100", f"عکس: {score.get('image', '?')}/100", f"آهنگ: {score.get('music', '?')}/100"]
    await update.message.reply_text("\n".join(lines))


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
    app.add_handler(CommandHandler("photo_now", photo_cmd))  # legacy
    app.add_handler(CommandHandler("music", music_cmd))
    app.add_handler(CommandHandler("music_now", music_cmd))  # legacy
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("schedule", schedule_cmd))
    app.add_handler(CommandHandler("jobs", jobs_cmd))
    app.add_handler(CommandHandler("findsong", find_song_cmd))
    app.add_handler(CommandHandler("status", stats_cmd))  # legacy
    app.add_handler(CommandHandler("songs", songs_cmd))
    app.add_handler(CommandHandler(["del", "delete"], del_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))
    app.add_handler(CommandHandler("mood", mood_cmd))
    app.add_handler(CallbackQueryHandler(panel_callback, pattern=r"^p:"))

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.AUDIO | filters.VOICE | filters.Document.ALL),
            receive_audio,
        )
    )

    jq = app.job_queue
    if jq is None:
        raise RuntimeError("job-queue نصب نیست: pip install 'python-telegram-bot[job-queue]'")

    if POST_INTERVAL_HOURS:
        jq.run_repeating(post_combined_job, interval=int(POST_INTERVAL_HOURS * 3600), first=30)
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

    logger.info(
        f"Silent Ruins 🥀 started | channel={CHANNEL_ID} | mode={'photos' if PHOTO_MODE else 'text-only'} | "
        f"times={POST_TIMES}"
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
