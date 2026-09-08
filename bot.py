"""
SilentRuins Bot 🥀 — Pro Edition
--------------------------------
ربات چنل‌های دپ/غمگین — هر پست یک «ستِ هم‌حس»:

    📸 عکس غمگین Pexels  ←  کپشن فارسی مرتبط با عکس  ←  🎭 استیکر  ←  🎧 آهنگ مرتبط

- ۶ حس/موضوع: بارون، شب، تنهایی، دلتنگی، خستگی، ویرونه — عکس و متن از یک حس انتخاب می‌شن
- آهنگ‌ها هم حس‌دارن: موقع ارسال MP3 تو کپشن بنویس rain/شب/بارون/… تا به همون حس وصل بشه
- امضای آخر هر پست: — silent ruins 🥀
- پنل مدیریت شیشه‌ای (دکمه‌ای) با /panel
- بدون تکرار: نه آهنگ تکراری، نه کپشن تکراری (تا اتمام دور)
- عکس خاموش هم می‌شه: SEND_PHOTOS=false → فقط متن + استیکر + آهنگ
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


# عکس‌دار بودن پست‌ها (پیش‌فرض روشن)
SEND_PHOTOS = _env_flag("SEND_PHOTOS", True)
# اسم عکاس ته کپشن (پیش‌فرض خاموش — کپشن ساده می‌مونه)
PHOTO_CREDIT = _env_flag("PHOTO_CREDIT", False)

PEXELS_API_KEY = (
    os.getenv("PEXELS_API_KEY")
    or os.getenv("PIXEL_API_KEY")
    or os.getenv("UNSPLASH_ACCESS_KEY")
)
PHOTO_MODE = SEND_PHOTOS and bool(PEXELS_API_KEY)
if SEND_PHOTOS and not PEXELS_API_KEY:
    logging.warning("⚠️ SEND_PHOTOS روشنه ولی PEXELS_API_KEY نیست — فعلاً فقط متن پست می‌شه")

STICKER_SET = (os.getenv("STICKER_SET") or "").strip()

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

POST_INTERVAL_HOURS = os.getenv("POST_INTERVAL_HOURS")
try:
    POST_INTERVAL_HOURS = float(POST_INTERVAL_HOURS) if POST_INTERVAL_HOURS else None
except ValueError:
    POST_INTERVAL_HOURS = None

DATA_DIR = Path(os.getenv("DATA_DIR", ".")).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)
LIBRARY_FILE = DATA_DIR / "library.json"
STATE_FILE = DATA_DIR / "state.json"
MUSIC_DIR = DATA_DIR / "music"
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# محتوا — حس‌محور: عکس و متن از یک حس، آهنگ هم اگه تگ خورد از همون حس
# ---------------------------------------------------------------------------
SIGNATURE = "— silent ruins 🥀"

MOODS = {
    "rain": {
        "fa": "بارون",
        "emoji": "🌧",
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

# برای تگ کردن آهنگ‌ها تو کپشن MP3 (فارسی، انگلیسی یا فینگلیش)
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
    return {"is_paused": False, "post_count": 0}


def save_state(patch):
    state = load_state()
    state.update(patch)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_admin(update: Update) -> bool:
    return bool(update.effective_user) and update.effective_user.id in ADMIN_IDS


# ---------------------------------------------------------------------------
# کپشن — از همان حسِ عکس، بدون تکرار (per-mood)
# ---------------------------------------------------------------------------
def pick_caption(mood):
    pool = MOODS[mood]["captions"]
    state = load_state()
    used_map = state.get("caption_used", {})
    if not isinstance(used_map, dict):  # سازگاری با فرمت قدیمی
        used_map = {}
    used = set(used_map.get(mood, []))
    remaining = [i for i in range(len(pool)) if i not in used]
    if not remaining:
        used = set()
        remaining = list(range(len(pool)))
    idx = random.choice(remaining)
    used.add(idx)
    used_map[mood] = sorted(used)
    save_state({"caption_used": used_map})
    return pool[idx]


def build_main_caption(mood):
    return f"{pick_caption(mood)}\n\n{SIGNATURE}"


# ---------------------------------------------------------------------------
# استیکر
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
    save_state({"pack_stickers": [f for f in _pack_stickers() if f != file_id]})


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
# آهنگ — چرخه‌ی بدون تکرار + اولویتِ آهنگِ هم‌حس با عکس
# ---------------------------------------------------------------------------
def get_next_track(mood=None, peek=False):
    lib = load_library()
    if not lib["tracks"]:
        return None

    if peek:
        # برای پیش‌نمایش: چیزی مصرف نمی‌شه
        if mood:
            same_mood = [t for t in lib["tracks"] if t.get("mood") == mood]
            if same_mood:
                return random.choice(same_mood)
        return random.choice(lib["tracks"])

    if not lib["unplayed"]:
        lib["unplayed"] = [t["file_id"] for t in lib["tracks"]]
        random.shuffle(lib["unplayed"])

    # اولویت با آهنگِ هم‌حس عکس (بدون شکستن قانون عدم تکرار)
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
    fp = removed.get("file_path")
    if fp:
        try:
            Path(fp).unlink(missing_ok=True)
        except Exception:
            pass
    return removed


# ---------------------------------------------------------------------------
# Pexels — کوئری از همان حس
# ---------------------------------------------------------------------------
def _luminance(hex_color):
    """روشنایی رنگ میانگین عکس (۰=تاریک، ۲۵۵=روشن)."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    except Exception:
        return 128


def _pick_dark_photo(photos):
    """از بین نتایج، قشنگ‌ترینِ تاریک‌ها (فضای دارک مینیمال)."""
    scored = [(_luminance(p.get("avg_color") or "#808080"), p) for p in photos]
    very_dark = [p for lum, p in scored if lum < 55]
    if very_dark:
        return random.choice(very_dark)
    # اگه هیچ‌کدوم خیلی تاریک نبودن، نیمه‌ی تاریک‌تر لیست
    darkest_half = sorted(scored, key=lambda x: x[0])[: max(1, len(scored) // 2)]
    return random.choice(darkest_half)[1]


def fetch_pexels_photo(mood):
    queries = MOODS[mood]["queries"]
    # تلاش‌ها: اول با فیلتر رنگ مشکی (عکس‌های دارک)، بعد بدون فیلتر
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
            params["color"] = color  # فقط نتایج با غلبه‌ی رنگ تیره
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
            photo = _pick_dark_photo(photos)
            src = photo.get("src", {})
            url = src.get("large2x") or src.get("large") or src.get("original")
            save_state({"last_query": query})
            return url, photo.get("photographer", "Pexels"), query
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
    """ست کامل پست: عکس/متن (هم‌حس) + استیکر + آهنگ (ترجیحاً هم‌حس)."""
    result = {"posted": False, "music": False, "sticker": False, "mood": None}

    mood = random.choice(list(MOODS.keys()))
    result["mood"] = mood
    caption = build_main_caption(mood)

    if PHOTO_MODE:
        url, photographer, query = await asyncio.to_thread(fetch_pexels_photo, mood)
        if PHOTO_CREDIT:
            caption = f"{caption}\n📷 {photographer}"
        main_msg = await context.bot.send_photo(chat_id=chat_id, photo=url, caption=caption)
    else:
        main_msg = await context.bot.send_message(chat_id=chat_id, text=caption)
    result["posted"] = True

    if await send_random_sticker(context, chat_id, reply_to=main_msg.message_id):
        result["sticker"] = True

    track = get_next_track(mood=mood, peek=not consume_music)
    if track:
        await send_track(context, chat_id, track, reply_to=main_msg.message_id)
        result["music"] = True

    if consume_music:
        save_state({"last_mood": mood})
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
        await notify_admins(context, f"⚠️ پست خودکار خطا داد: {e}\n(چک کن ربات ادمین چنل باشه)")
        return False


def _post_result_text(result):
    if not result or not result.get("posted"):
        return "❌ پست نشد — چک کن ربات ادمین چنل باشه."
    mood = result["mood"]
    mood_fa = f"{MOODS[mood]['fa']} {MOODS[mood]['emoji']}" if mood else "؟"
    bits = ["عکس" if PHOTO_MODE else "متن"]
    if result["sticker"]:
        bits.append("استیکر")
    bits.append("آهنگ" if result["music"] else "بدون آهنگ (کتابخونه خالیه)")
    return f"✅ پست شد — حس: {mood_fa}\n{' + '.join(bits)}"


# جاب‌های سازگاری قدیمی
async def post_photo_only_job(context: ContextTypes.DEFAULT_TYPE):
    if load_state().get("is_paused"):
        return
    if not PEXELS_API_KEY:
        await notify_admins(context, "برای پست عکس PEXELS_API_KEY لازمه.")
        return
    mood = random.choice(list(MOODS.keys()))
    try:
        url, photographer, query = await asyncio.to_thread(fetch_pexels_photo, mood)
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
        f"🧩 حالت: {'📸 عکس + متن' if PHOTO_MODE else '📝 متن ساده'} + 🎭 + 🎧",
        f"🌗 آخرین حس: {MOODS[last_mood]['fa']} {MOODS[last_mood]['emoji']}" if last_mood else "",
        f"🎵 آهنگ‌ها: {len(lib['tracks'])} (حس‌دار: {tagged}؛ تو چرخه: {len(lib['unplayed'])})",
        f"🎭 استیکرها: {len(lib['stickers']) + len(_pack_stickers())}",
    ]
    lines = [l for l in lines if l]
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


def _stickers_text():
    lib = load_library()
    return (
        "🎭 کتابخونه‌ی استیکر:\n\n"
        f"• فرستاده‌شده توسط تو: {len(lib['stickers'])}\n"
        f"• از پک {STICKER_SET or '—'}: {len(_pack_stickers())}\n\n"
        "استیکر رو همینجا بفرست تا اضافه بشه؛ یا STICKER_SET رو به اسم یه پک عمومی ست کن."
    )


_MOODS_FA = "، ".join(m["fa"] + " " + m["emoji"] for m in MOODS.values())

HELP_TEXT = (
    "سلام! Silent Ruins 🥀\n\n"
    "هر پست یه ستِ هم‌حسه: عکس دپ ← کپشن مرتبط ← استیکر ← آهنگ مرتبط\n"
    f"حس‌ها: {_MOODS_FA}\n\n"
    "➕ آهنگ: MP3 رو اینجا بفرست (می‌تونی موقع ارسال تو کپشن حسش رو هم بنویسی: "
    "بارون / شب / تنهایی / دلتنگی / خستگی / ویرونه)\n"
    "➕ استیکر: استیکر رو همینجا بفرست\n\n"
    "دستورات:\n"
    "/panel — پنل شیشه‌ای مدیریت 🎛\n"
    "/post پست فوری • /preview پیش‌نمایش\n"
    "/songs آهنگ‌ها • /del حذف • /stickers استیکرها\n"
    "/pause توقف • /resume ادامه • /stats آمار • /id آیدی"
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
        f"🎵 {len(lib['tracks'])} آهنگ  •  🎭 {len(lib['stickers']) + len(_pack_stickers())} استیکر\n"
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
            InlineKeyboardButton("🎭 استیکر", callback_data="p:stickers"),
        ],
        [
            InlineKeyboardButton(
                "▶️ ادامه‌ی پست خودکار" if paused else "⏸ توقف پست خودکار",
                callback_data="p:resume" if paused else "p:pause",
            )
        ],
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
    elif data == "p:stickers":
        await q.answer()
        await q.message.reply_text(_stickers_text())
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
        await update.message.reply_text(f"🌗 حس این پست: {MOODS[mood]['fa']} {MOODS[mood]['emoji']}")
        if not result["music"]:
            await update.message.reply_text("🎵 کتابخونه‌ی آهنگ خالیه — MP3 بفرست.")
        if not result["sticker"]:
            await update.message.reply_text("🎭 استیکری نداری — بفرست یا STICKER_SET ست کن.")
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


async def stickers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(_stickers_text())


# ---------------------------------------------------------------------------
# دریافت آهنگ و استیکر
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

    # کپشن «خواننده - ترک»
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
    app.add_handler(CommandHandler("photo_now", photo_cmd))  # legacy
    app.add_handler(CommandHandler("music", music_cmd))
    app.add_handler(CommandHandler("music_now", music_cmd))  # legacy
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("status", stats_cmd))  # legacy
    app.add_handler(CommandHandler("songs", songs_cmd))
    app.add_handler(CommandHandler(["del", "delete"], del_cmd))
    app.add_handler(CommandHandler("stickers", stickers_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))
    app.add_handler(CallbackQueryHandler(panel_callback, pattern=r"^p:"))

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
        f"Silent Ruins 🥀 started | channel={CHANNEL_ID} | mode={'photos' if PHOTO_MODE else 'text-only'} | "
        f"times={POST_TIMES} | sticker_set={STICKER_SET or '-'}"
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
