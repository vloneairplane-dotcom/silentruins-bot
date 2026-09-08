"""
SilentRuins Bot 🥀 — Pexels Edition
Auto-posts sad/dep aesthetic photos from Pexels + Persian sad captions + music to a Telegram channel.
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
# Config — supports both new and legacy env names
# ---------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in .env")

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY") or os.getenv("PIXEL_API_KEY") or os.getenv("UNSPLASH_ACCESS_KEY")
if not PEXELS_API_KEY:
    raise RuntimeError("PEXELS_API_KEY is missing. Get one at https://www.pexels.com/api/")

# Admins: support ADMIN_IDS (comma) or ADMIN_USER_ID (single)
_admin_raw = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_USER_ID") or ""
ADMIN_IDS = set()
if _admin_raw:
    for part in str(_admin_raw).split(","):
        part = part.strip()
        if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
            try:
                ADMIN_IDS.add(int(part))
            except:
                pass
if not ADMIN_IDS:
    logging.warning("No ADMIN_IDS set — bot will not respond to admin commands")

# Channel: support CHANNEL or CHANNEL_ID
_raw_channel = os.getenv("CHANNEL") or os.getenv("CHANNEL_ID") or ""
if not _raw_channel:
    raise RuntimeError("CHANNEL is missing (e.g. @songsandscars or -100123...)")
CHANNEL_ID = _raw_channel if _raw_channel.startswith("@") else int(_raw_channel) if _raw_channel.lstrip("-").isdigit() else _raw_channel

TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Tehran")
try:
    TIMEZONE = ZoneInfo(TIMEZONE_STR)
except Exception:
    TIMEZONE = ZoneInfo("Asia/Tehran")

# Posting schedule
# You can set either:
# - POST_TIMES=10:00,16:00,22:00,02:00  (combined photo+text+music posts)
# - Or legacy PHOTO_TIMES and MUSIC_TIMES separately
# - Or POST_INTERVAL_HOURS=3 for every 3 hours
POST_TIMES_RAW = os.getenv("POST_TIMES") or os.getenv("PHOTO_TIMES") or "10:00,16:00,22:00,02:00"
POST_TIMES = [t.strip() for t in POST_TIMES_RAW.split(",") if t.strip()]
MUSIC_TIMES_RAW = os.getenv("MUSIC_TIMES", "")
MUSIC_TIMES = [t.strip() for t in MUSIC_TIMES_RAW.split(",") if t.strip()]

POST_INTERVAL_HOURS = os.getenv("POST_INTERVAL_HOURS")
try:
    POST_INTERVAL_HOURS = float(POST_INTERVAL_HOURS) if POST_INTERVAL_HOURS else None
except:
    POST_INTERVAL_HOURS = None

# اگه DATA_DIR ست بشه (مثلاً /data روی Railway با Volume)، کتابخونه آهنگ و
# وضعیت ربات اونجا ذخیره می‌شن و بعد از ری‌استارت/دیپلوی پاک نمی‌شن.
DATA_DIR = Path(os.getenv("DATA_DIR", ".")).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)
LIBRARY_FILE = DATA_DIR / "library.json"
STATE_FILE = DATA_DIR / "state.json"
MUSIC_DIR = DATA_DIR / "music"
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Sad / Dep content
# ---------------------------------------------------------------------------
SAD_QUERIES = [
    "sad aesthetic",
    "depression dark aesthetic",
    "lonely girl night window",
    "sad boy alone dark",
    "melancholy portrait",
    "dark moody aesthetic",
    "broken heart aesthetic",
    "alone in dark room",
    "crying in rain aesthetic",
    "rainy night alone",
    "empty room depression",
    "sad eyes close up",
    "foggy lonely road night",
    "withered roses dark",
    "black and white sadness",
    "gothic melancholy",
    "abandoned room dark",
    "loneliness aesthetic",
    "sad girl black and white",
    "dark forest loneliness",
    "cigarette smoke sad night",
    "empty bed sadness",
    "window rain night sad",
    "depressed aesthetic girl",
    "moody dark portrait",
]

# Persian sad/dep captions — heavy, short, channel-friendly
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
]

# Hashtags to add optionally
HASHTAGS = ["#غمگین", "#دپ", "#دلتنگی", "#شب_بخیر", "#تنهایی"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("silent_ruins_bot")

# ---------------------------------------------------------------------------
# Health server (for Render etc.)
# ---------------------------------------------------------------------------
def _run_health_server():
    port = int(os.environ.get("PORT", "10000"))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Silent Ruins bot (Pexels) is alive".encode("utf-8"))

        def log_message(self, format, *args):
            pass

    try:
        HTTPServer(("0.0.0.0", port), Handler).serve_forever()
    except Exception as e:
        logger.warning(f"Health server failed: {e}")


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------
def load_library():
    if LIBRARY_FILE.exists():
        try:
            return json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {"tracks": [], "unplayed": []}


def save_library(data):
    LIBRARY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {"is_paused": False, "post_count": 0, "last_query": None}


def save_state(data):
    state = load_state()
    state.update(data)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_admin(update: Update) -> bool:
    if not update.effective_user:
        return False
    if not ADMIN_IDS:
        return False
    return update.effective_user.id in ADMIN_IDS


# ---------------------------------------------------------------------------
# Pexels
# ---------------------------------------------------------------------------
def fetch_pexels_photo():
    """
    Fetch a random sad/dep photo from Pexels.
    Returns: (photo_url, photographer_name, photographer_url, query_used)
    """
    # Try 3 different random queries/pages for resilience
    for attempt in range(5):
        query = random.choice(SAD_QUERIES)
        page = random.randint(1, 10)
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                params={
                    "query": query,
                    "per_page": 30,
                    "page": page,
                    "orientation": "portrait",
                    "size": "large",
                },
                headers={"Authorization": PEXELS_API_KEY},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            photos = data.get("photos", [])
            if not photos:
                continue

            # Prefer darker / higher quality photos randomly
            photo = random.choice(photos)
            # Use large2x or original
            src = photo.get("src", {})
            url = src.get("large2x") or src.get("large") or src.get("original")
            photographer = photo.get("photographer", "Pexels")
            photographer_url = photo.get("photographer_url", "https://pexels.com")
            photo_url_page = photo.get("url", "")

            save_state({"last_query": query})
            return url, photographer, photographer_url, query, photo_url_page

        except requests.RequestException as e:
            logger.warning(f"Pexels attempt {attempt+1} failed for query '{query}': {e}")
            time_module.sleep(1)
            continue

    raise RuntimeError("نتونستم از Pexels عکس بگیرم — همه تلاش‌ها شکست خورد")


def build_caption() -> str:
    """Build a Persian sad caption with hashtags and channel mention."""
    base = random.choice(PERSIAN_SAD_CAPTIONS)
    # 70% add hashtags
    tags = ""
    if random.random() < 0.7:
        chosen_tags = random.sample(HASHTAGS, k=random.randint(1, 2))
        tags = "\n" + " ".join(chosen_tags)

    # Always mention channel if it's @username
    channel_tag = ""
    if isinstance(CHANNEL_ID, str) and CHANNEL_ID.startswith("@"):
        channel_tag = f"\n{CHANNEL_ID}"

    return f"{base}{tags}{channel_tag}"


# ---------------------------------------------------------------------------
# Music handling
# ---------------------------------------------------------------------------
def get_next_track():
    """Get next track file_id using no-repeat shuffle logic. Returns track dict or None."""
    lib = load_library()
    if not lib["tracks"]:
        return None

    if not lib["unplayed"]:
        lib["unplayed"] = [t["file_id"] for t in lib["tracks"]]
        random.shuffle(lib["unplayed"])
        save_library(lib)

    if not lib["unplayed"]:
        return None

    next_file_id = lib["unplayed"].pop(0)
    save_library(lib)

    # Find full track info
    for t in lib["tracks"]:
        if t["file_id"] == next_file_id:
            return t
    # Fallback if metadata missing
    return {"file_id": next_file_id, "title": "Unknown"}


# ---------------------------------------------------------------------------
# Core posting job — photo + caption + music
# ---------------------------------------------------------------------------
async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str):
    if not ADMIN_IDS:
        return
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text)
        except Exception:
            pass


async def post_combined_job(context: ContextTypes.DEFAULT_TYPE):
    """The main job: post sad photo with Persian caption, then music as a reply
    to the photo post. Returns "no_music" / "music" on success, False on failure."""
    state = load_state()
    if state.get("is_paused"):
        logger.info("Posting is paused, skipping job")
        return False

    try:
        # 1. Fetch photo (in a thread so the bot stays responsive meanwhile)
        photo_url, photographer, photographer_url, query, pexels_page = await asyncio.to_thread(
            fetch_pexels_photo
        )
        caption = build_caption()
        full_caption = f"{caption}\n\n📷 {photographer} / Pexels"

        # 2. Send photo to channel
        photo_msg = await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo_url, caption=full_caption)
        logger.info(f"Posted photo query='{query}' photographer={photographer}")

        result = "no_music"
        # 3. Try to send music as a reply to the photo → photo+text+music stay together
        track = get_next_track()
        if track:
            try:
                # If we have local file path and file exists, send as file, else send by file_id
                file_path = track.get("file_path")
                if file_path and Path(file_path).exists():
                    with open(file_path, "rb") as f:
                        await context.bot.send_audio(
                            chat_id=CHANNEL_ID,
                            audio=f,
                            caption=f"🎧 {track.get('title','')} \n{random.choice(PERSIAN_SAD_CAPTIONS)}",
                            title=track.get("title"),
                            reply_to_message_id=photo_msg.message_id,
                        )
                else:
                    await context.bot.send_audio(
                        chat_id=CHANNEL_ID,
                        audio=track["file_id"],
                        caption=f"🎧 {track.get('title','')} \n{random.choice(PERSIAN_SAD_CAPTIONS)}",
                        reply_to_message_id=photo_msg.message_id,
                    )
                logger.info(f"Posted music: {track.get('title')}")
                result = "music"
            except Exception as e:
                logger.exception("Failed to post music")
                await notify_admins(context, f"⚠️ عکس پست شد ولی موزیک خطا داد: {e}\nTrack: {track.get('title')}")
        else:
            logger.info("No music tracks available, only photo posted")
            # Notify admin only occasionally (not every time)
            if random.random() < 0.15:
                await notify_admins(context, "🎵 کتابخونه موزیک خالیه. یه آهنگ MP3 تو پیوی برام بفرست تا به پست‌ها اضافه بشه.")

        # Update stats
        save_state({"post_count": state.get("post_count", 0) + 1})
        return result

    except Exception as e:
        logger.exception("Failed in post_combined_job")
        await notify_admins(context, f"⚠️ خطا در پست خودکار: {e}\n\n(چک کن ربات ادمین چنل باشه و کلید Pexels سالم باشه)")
        return False


# Separate legacy jobs for backward compat
async def post_photo_only_job(context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    if state.get("is_paused"):
        return
    try:
        photo_url, photographer, photographer_url, query, pexels_page = await asyncio.to_thread(
            fetch_pexels_photo
        )
        caption = build_caption()
        full_caption = f"{caption}\n\n📷 {photographer} / Pexels"
        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo_url, caption=full_caption)
        save_state({"post_count": state.get("post_count", 0) + 1, "last_query": query})
    except Exception as e:
        logger.exception("post_photo_only_job failed")
        await notify_admins(context, f"⚠️ خطا در پست عکس: {e}")


async def post_music_only_job(context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    if state.get("is_paused"):
        return
    track = get_next_track()
    if not track:
        await notify_admins(context, "🎵 کتابخونه موزیک خالیه.")
        return
    try:
        file_path = track.get("file_path")
        if file_path and Path(file_path).exists():
            with open(file_path, "rb") as f:
                await context.bot.send_audio(
                    chat_id=CHANNEL_ID,
                    audio=f,
                    caption=f"🎧 {track.get('title','')} \n{random.choice(PERSIAN_SAD_CAPTIONS)}",
                    title=track.get("title"),
                )
        else:
            await context.bot.send_audio(chat_id=CHANNEL_ID, audio=track["file_id"])
    except Exception as e:
        logger.exception("post_music_only_job failed")
        await notify_admins(context, f"⚠️ خطا در پست موزیک: {e}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        # For non-admins, just show id
        await update.message.reply_text(
            f"سلام 🥀\n"
            f"این ربات برای چنل {CHANNEL_ID} ساخته شده.\n"
            f"آیدی شما: {update.effective_user.id}\n"
            f"برای دسترسی ادمین، آیدیت رو به صاحب ربات بده."
        )
        return

    await update.message.reply_text(
        "سلام! ربات Silent Ruins 🥀 (Pexels Edition) روشنه.\n\n"
        "📸 ربات خودکار از Pexels عکس غمگین و دپ میگیره و با متن فارسی + آهنگ میذاره تو چنل.\n\n"
        "دستورات ادمین:\n"
        "/post — همین الان یه پست (عکس + متن + آهنگ) بذار\n"
        "/photo — فقط عکس دپ بذار\n"
        "/music — فقط آهنگ بذار\n"
        "/pause — پست خودکار رو متوقف کن\n"
        "/resume — پست خودکار رو دوباره فعال کن\n"
        "/stats — وضعیت ربات و کتابخونه\n"
        "/songs — لیست آهنگ‌ها\n"
        "/panel — پنل مدیریت\n"
        "/id — آیدی خودت و چت\n\n"
        "برای اضافه کردن آهنگ:\n"
        "کافیه فایل MP3 رو همینجا (پیوی ربات) برام بفرستی. ذخیره میشه تو پوشه music/ و خودکار تو پست‌ها استفاده میشه.\n\n"
        f"چنل: {CHANNEL_ID}\n"
        f"زمان‌بندی: {', '.join(POST_TIMES) if POST_INTERVAL_HOURS is None else f'هر {POST_INTERVAL_HOURS} ساعت'}\n"
        f"وضعیت: {'⏸️ متوقف' if load_state().get('is_paused') else '▶️ فعال'}"
    )


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else "نامشخص"
    user_id = update.effective_user.id if update.effective_user else "نامشخص"
    await update.message.reply_text(f"👤 آیدی شما: {user_id}\n💬 آیدی چت: {chat_id}\n📢 چنل: {CHANNEL_ID}")


async def post_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("⏳ دارم از Pexels عکس غمگین میگیرم و پست میکنم...")
    result = await post_combined_job(context)
    if result == "music":
        await update.message.reply_text("✅ عکس + متن + آهنگ تو چنل پست شد!")
    elif result == "no_music":
        await update.message.reply_text("✅ عکس پست شد، ولی کتابخونه آهنگ خالیه — MP3 برام بفرست تا پست‌های بعدی آهنگ هم داشته باشن.")
    else:
        await update.message.reply_text("❌ پست نشد. خطا رو تو پیوی ربات (همینجا) برات فرستادم.")


async def photo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("⏳ در حال گرفتن عکس از Pexels...")
    await post_photo_only_job(context)


async def music_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await post_music_only_job(context)


async def pause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    save_state({"is_paused": True})
    await update.message.reply_text("⏸️ پست خودکار متوقف شد. با /resume دوباره فعال میشه.")


async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    save_state({"is_paused": False})
    await update.message.reply_text("▶️ پست خودکار فعال شد.")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    lib = load_library()
    state = load_state()
    await update.message.reply_text(
        f"📊 آمار ربات Silent Ruins 🥀\n\n"
        f"📢 چنل: {CHANNEL_ID}\n"
        f"⏰ زمان‌بندی: {', '.join(POST_TIMES) if POST_INTERVAL_HOURS is None else f'هر {POST_INTERVAL_HOURS} ساعت'}\n"
        f"🌍 تایم‌زون: {TIMEZONE_STR}\n"
        f"⏸️ وضعیت: {'متوقف' if state.get('is_paused') else 'فعال'}\n"
        f"📮 تعداد پست‌ها: {state.get('post_count',0)}\n"
        f"🔍 آخرین جستجو: {state.get('last_query','-')}\n\n"
        f"🎵 کل آهنگ‌ها: {len(lib['tracks'])}\n"
        f"🔄 باقی‌مونده تو چرخه: {len(lib['unplayed'])}\n"
        f"📁 پوشه موزیک: {len(list(MUSIC_DIR.glob('*')))} فایل\n\n"
        f"🔑 Pexels API: {'✅ ست شده' if PEXELS_API_KEY else '❌ نیست'}"
    )


async def songs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    lib = load_library()
    if not lib["tracks"]:
        await update.message.reply_text("🎵 کتابخونه خالیه. یه فایل MP3 برام بفرست.")
        return
    lines = []
    for i, t in enumerate(lib["tracks"][-20:], 1):  # last 20
        title = t.get("title", "بدون نام")[:40]
        lines.append(f"{i}. {title}")
    text = "🎵 لیست آهنگ‌ها (20 تای آخر):\n\n" + "\n".join(lines)
    if len(lib["tracks"]) > 20:
        text += f"\n\n... و {len(lib['tracks'])-20} تای دیگه (کل: {len(lib['tracks'])})"
    await update.message.reply_text(text)


async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    state = load_state()
    lib = load_library()
    await update.message.reply_text(
        f"🎛 پنل مدیریت Silent Ruins 🥀\n\n"
        f"📢 چنل: {CHANNEL_ID}\n"
        f"👑 ادمین‌ها: {', '.join(map(str, ADMIN_IDS))}\n"
        f"وضعیت: {'⏸️ متوقف' if state.get('is_paused') else '▶️ فعال'}\n"
        f"پست‌ها: {state.get('post_count',0)} | آهنگ‌ها: {len(lib['tracks'])}\n\n"
        f"دستورات سریع:\n"
        f"/post - پست فوری (عکس+متن+آهنگ)\n"
        f"/photo - فقط عکس\n"
        f"/music - فقط آهنگ\n"
        f"/pause - توقف\n"
        f"/resume - ادامه\n"
        f"/stats - آمار کامل\n"
        f"/songs - لیست آهنگ‌ها\n\n"
        f"برای افزودن آهنگ جدید، فقط فایل MP3 رو اینجا بفرست."
    )


async def receive_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    # Support audio, voice, and document (mp3)
    msg = update.message
    audio_file = None
    file_id = None
    title = None
    ext = "mp3"

    if msg.audio:
        audio_file = msg.audio
        file_id = audio_file.file_id
        title = audio_file.title or audio_file.file_name or "بدون‌نام"
    elif msg.document and msg.document.mime_type and "audio" in msg.document.mime_type:
        audio_file = msg.document
        file_id = audio_file.file_id
        title = audio_file.file_name or "بدون‌نام"
        if "." in title:
            ext = title.split(".")[-1]
    elif msg.document and msg.document.file_name and msg.document.file_name.lower().endswith((".mp3", ".m4a", ".ogg", ".flac", ".wav")):
        audio_file = msg.document
        file_id = audio_file.file_id
        title = audio_file.file_name or "بدون‌نام"
        if "." in title:
            ext = title.split(".")[-1]
    elif msg.voice:
        audio_file = msg.voice
        file_id = audio_file.file_id
        title = f"voice_{audio_file.file_id[:8]}"
        ext = "ogg"
    else:
        return

    try:
        # Download file
        safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_", ".")).strip()[:80]
        if not safe_title:
            safe_title = f"track_{int(time_module.time())}"
        # Ensure extension
        if not safe_title.lower().endswith(f".{ext}"):
            # remove existing ext if any
            if "." in safe_title:
                safe_title = safe_title.rsplit(".", 1)[0]
            safe_title = f"{safe_title}.{ext}"

        dest_path = MUSIC_DIR / safe_title
        # Avoid overwrite
        counter = 1
        base = dest_path.stem
        while dest_path.exists():
            dest_path = MUSIC_DIR / f"{base}_{counter}.{ext}"
            counter += 1

        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(custom_path=str(dest_path))

        # Save to library
        lib = load_library()
        lib["tracks"].append(
            {
                "file_id": file_id,
                "title": title,
                "file_path": str(dest_path),
                "added_at": int(time_module.time()),
            }
        )
        # Add to unplayed queue
        lib["unplayed"].append(file_id)
        save_library(lib)

        await update.message.reply_text(
            f"✅ «{title}» ذخیره شد!\n"
            f"📁 {dest_path.name}\n"
            f"🎵 کل کتابخونه: {len(lib['tracks'])} آهنگ\n"
            f"الان تو پست‌های خودکار استفاده میشه."
        )
        logger.info(f"Saved new track: {title} -> {dest_path}")

    except Exception as e:
        logger.exception("Failed to save audio")
        await update.message.reply_text(f"❌ خطا در ذخیره آهنگ: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    threading.Thread(target=_run_health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands — new names + legacy compat
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("post", post_cmd))
    app.add_handler(CommandHandler("photo", photo_cmd))
    app.add_handler(CommandHandler("photo_now", photo_cmd))  # legacy
    app.add_handler(CommandHandler("music", music_cmd))
    app.add_handler(CommandHandler("music_now", music_cmd))  # legacy
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("status", stats_cmd))  # legacy
    app.add_handler(CommandHandler("songs", songs_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))

    # Audio receiving
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.AUDIO | filters.VOICE | filters.Document.AUDIO | filters.Document.ALL),
            receive_audio,
        )
    )

    # Scheduling
    jq = app.job_queue
    if POST_INTERVAL_HOURS:
        interval_seconds = int(POST_INTERVAL_HOURS * 3600)
        jq.run_repeating(post_combined_job, interval=interval_seconds, first=30)
        logger.info(f"Scheduled repeating post every {POST_INTERVAL_HOURS}h")
    else:
        # Combined posts
        for t in POST_TIMES:
            try:
                h, m = map(int, t.split(":"))
                jq.run_daily(post_combined_job, time=dtime(hour=h, minute=m, tzinfo=TIMEZONE), name=f"combined_{t}")
            except Exception as e:
                logger.warning(f"Invalid POST_TIME '{t}': {e}")

        # Legacy separate music times if set
        for t in MUSIC_TIMES:
            try:
                h, m = map(int, t.split(":"))
                jq.run_daily(post_music_only_job, time=dtime(hour=h, minute=m, tzinfo=TIMEZONE), name=f"music_{t}")
            except Exception as e:
                logger.warning(f"Invalid MUSIC_TIME '{t}': {e}")

    logger.info(
        f"Silent Ruins Pexels bot started. Channel={CHANNEL_ID} | Admins={ADMIN_IDS} | "
        f"Times={POST_TIMES} | Interval={POST_INTERVAL_HOURS} | TZ={TIMEZONE_STR}"
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
