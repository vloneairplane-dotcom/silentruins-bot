"""
Silent Ruins Telegram Bot 🥀
----------------------------
Auto-posts mood-matched photos (via Unsplash) and admin-supplied music
to a Telegram channel, on a schedule, plus a few admin commands.
"""

import json
import logging
import os
import random
import threading
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
# Config (all from environment variables — see .env.example)
# ---------------------------------------------------------------------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_USER_ID = int(os.environ["ADMIN_USER_ID"])
UNSPLASH_ACCESS_KEY = os.environ["UNSPLASH_ACCESS_KEY"]

_raw_channel = os.environ["CHANNEL_ID"]
CHANNEL_ID = _raw_channel if _raw_channel.startswith("@") else int(_raw_channel)

TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Baku"))
PHOTO_TIMES = [t.strip() for t in os.environ.get("PHOTO_TIMES", "10:00,22:00").split(",") if t.strip()]
MUSIC_TIMES = [t.strip() for t in os.environ.get("MUSIC_TIMES", "16:00").split(",") if t.strip()]

LIBRARY_FILE = Path("library.json")
STATE_FILE = Path("state.json")

# Search terms used to pull mood-matched photos from Unsplash, grouped into
# categories. The category is what gets matched against a track's mood tag
# (see receive_audio) so the music posted later can fit the last photo.
MOOD_CATEGORIES = {
    "rain": [
        "rain on window at night", "night rain city street",
        "black and white rain", "stormy sea cliff",
    ],
    "ruins": [
        "abandoned ruins", "ancient castle ruins",
        "abandoned cathedral", "ruined monastery",
    ],
    "forest": [
        "foggy forest", "misty mountains",
        "moody autumn forest", "solitude nature dusk",
    ],
    "gothic": [
        "gothic architecture", "dark academia aesthetic",
        "empty gothic hallway", "old library candlelight",
        "candle shadows dark room",
    ],
    "melancholy": [
        "melancholic landscape", "withered roses",
        "moonlit graveyard", "lonely lighthouse fog",
    ],
}
MOOD_TAGS = list(MOOD_CATEGORIES.keys())

# Short "heavy" opening lines for photo captions. Edit/extend freely.
MOOD_QUOTES = [
    "some memories sound like rain. 🖤",
    "we are all ghosts of who we used to be. 🖤",
    "silence has its own kind of noise. 🖤",
    "the ruins remember what we forgot. 🖤",
    "even the moon gets tired of shining. 🖤",
    "some nights ask questions the morning can't answer. 🖤",
    "grief is just love with nowhere to go. 🖤",
    "the fog doesn't hide things, it holds them. 🖤",
    "old walls keep the softest secrets. 🖤",
    "we bury feelings in places that still ache. 🖤",
    "every ruin was once someone's home. 🖤",
    "the quiet ones carry the loudest storms. 🖤",
    "some roses wilt before they're picked. 🖤",
    "distance is just silence wearing miles. 🖤",
    "the past doesn't knock, it just walks in. 🖤",
    "some scars are just maps of who survived. 🖤",
    "the dark isn't empty, it's just honest. 🖤",
    "we save the saddest songs for the emptiest rooms. 🖤",
    "even shadows need somewhere to rest. 🖤",
    "some doors close so quietly you don't hear it happen. 🖤",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("silent_ruins_bot")


# ---------------------------------------------------------------------------
# Tiny health-check HTTP server
# ---------------------------------------------------------------------------
# Some free hosts (e.g. Render's free tier) only give a free instance to
# "Web Service" processes, which must bind to a port and answer HTTP
# requests. This thread satisfies that requirement while the real bot logic
# runs as a normal Telegram polling loop on the main thread. Harmless (and
# unnecessary) if you run the bot on your own machine or a VPS.
def _run_health_server():
    port = int(os.environ.get("PORT", "10000"))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Silent Ruins bot is alive.")

        def log_message(self, format, *args):  # silence default request logs
            pass

    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


# ---------------------------------------------------------------------------
# Local "library" storage (music track file_ids + simple no-repeat shuffle)
# ---------------------------------------------------------------------------
def load_library():
    if LIBRARY_FILE.exists():
        return json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
    return {"tracks": [], "unplayed": []}


def save_library(data):
    LIBRARY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(data):
    state = load_state()
    state.update(data)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_admin(update: Update) -> bool:
    return bool(update.effective_user) and update.effective_user.id == ADMIN_USER_ID


# ---------------------------------------------------------------------------
# Unsplash
# ---------------------------------------------------------------------------
def fetch_random_photo():
    """Pick a mood category + keyword, search Unsplash biased toward dark/black
    toned results for a moodier, higher-quality look, and return
    (photo_url, caption, mood_category)."""
    category = random.choice(MOOD_TAGS)
    query = random.choice(MOOD_CATEGORIES[category])

    photo = None
    for page in (random.randint(1, 3), 1):
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query": query,
                "color": "black",  # biases results toward a dark/moody palette
                "orientation": "portrait",
                "per_page": 30,
                "page": page,
            },
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            photo = random.choice(results)
            break

    if photo is None:
        # Fallback if that mood/page combo had no results.
        resp = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": query, "orientation": "portrait"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=15,
        )
        resp.raise_for_status()
        photo = resp.json()

    # Unsplash API guidelines require pinging the download endpoint whenever
    # a photo is actually used, and crediting the photographer + Unsplash.
    try:
        requests.get(
            photo["links"]["download_location"],
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10,
        )
    except requests.RequestException:
        logger.warning("Could not ping Unsplash download endpoint")

    quote = random.choice(MOOD_QUOTES)
    photographer = photo["user"]["name"]
    photographer_link = photo["user"]["links"]["html"] + "?utm_source=silent_ruins_bot&utm_medium=referral"
    photo_url = photo["urls"]["full"]  # higher resolution than "regular"
    caption = f"{quote}\n\n📷 {photographer} / Unsplash\n{photographer_link}"
    return photo_url, caption, category


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------
async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        await context.bot.send_message(chat_id=ADMIN_USER_ID, text=text)
    except Exception:
        logger.exception("Failed to notify admin")


async def post_photo_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        url, caption, category = fetch_random_photo()
        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=url, caption=caption)
        save_state({"last_photo_mood": category})
        logger.info("Posted photo (mood=%s)", category)
    except Exception as e:
        logger.exception("Failed to post photo")
        await notify_admin(context, f"⚠️ خطا در پست عکس: {e}")


async def post_music_job(context: ContextTypes.DEFAULT_TYPE):
    library = load_library()
    if not library["tracks"]:
        await notify_admin(context, "🎵 کتابخونه موزیک خالیه. یه فایل صوتی تو پیوی برام بفرست تا اضافه بشه.")
        return

    if not library["unplayed"]:
        library["unplayed"] = [t["file_id"] for t in library["tracks"]]
        random.shuffle(library["unplayed"])

    # Prefer a track tagged with the same mood as the last posted photo,
    # without breaking the "everyone plays once before a repeat" rule.
    target_mood = load_state().get("last_photo_mood")
    mood_by_id = {t["file_id"]: t.get("mood") for t in library["tracks"]}
    chosen_index = 0
    if target_mood:
        for i, fid in enumerate(library["unplayed"]):
            if mood_by_id.get(fid) == target_mood:
                chosen_index = i
                break

    file_id = library["unplayed"].pop(chosen_index)
    save_library(library)

    try:
        await context.bot.send_audio(chat_id=CHANNEL_ID, audio=file_id)
        logger.info("Posted music (target mood=%s)", target_mood)
    except Exception as e:
        logger.exception("Failed to post music")
        await notify_admin(context, f"⚠️ خطا در پست موزیک: {e}")


# ---------------------------------------------------------------------------
# Commands (admin-only — silently ignored for everyone else)
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(
        "سلام! ربات Silent Ruins 🥀 روشنه.\n\n"
        "دستورات:\n"
        "/photo_now — همین الان یه عکس متناسب با حال‌وهوای چنل پست کن\n"
        "/music_now — همین الان یه آهنگ از کتابخونه پست کن\n"
        "/status — وضعیت کتابخونه موزیک\n\n"
        "برای اضافه کردن آهنگ، کافیه فایل صوتی رو همینجا (پیوی) برام بفرستی.\n"
        "اگه موقع فرستادنش تو کپشن یکی از این کلمه‌ها رو بنویسی، آهنگ به همون "
        "حال‌وهوا تگ می‌شه و بیشتر وقت‌ها بعد از عکس‌های همون حس پخش می‌شه:\n"
        f"{', '.join(MOOD_TAGS)}"
    )


async def photo_now_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("در حال گرفتن عکس از Unsplash...")
    await post_photo_job(context)


async def music_now_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await post_music_job(context)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    library = load_library()
    await update.message.reply_text(
        f"🎵 تعداد کل آهنگ‌ها: {len(library['tracks'])}\n"
        f"🔄 باقی‌مونده تو چرخهٔ فعلی: {len(library['unplayed'])}"
    )


async def receive_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    audio = update.message.audio or update.message.voice
    if not audio:
        return

    caption_text = (update.message.caption or "").lower()
    mood = next((tag for tag in MOOD_TAGS if tag in caption_text), None)

    library = load_library()
    title = getattr(audio, "title", None) or "بدون‌نام"
    library["tracks"].append({"file_id": audio.file_id, "title": title, "mood": mood})
    save_library(library)

    mood_note = f" (حال‌وهوا: {mood})" if mood else " (بدون حال‌وهوای خاص)"
    await update.message.reply_text(
        f"✅ «{title}» اضافه شد{mood_note}. (مجموع کتابخونه: {len(library['tracks'])})"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    threading.Thread(target=_run_health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("photo_now", photo_now_cmd))
    app.add_handler(CommandHandler("music_now", music_now_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & (filters.AUDIO | filters.VOICE), receive_audio)
    )

    jq = app.job_queue
    for t in PHOTO_TIMES:
        h, m = map(int, t.split(":"))
        jq.run_daily(post_photo_job, time=dtime(hour=h, minute=m, tzinfo=TIMEZONE))
    for t in MUSIC_TIMES:
        h, m = map(int, t.split(":"))
        jq.run_daily(post_music_job, time=dtime(hour=h, minute=m, tzinfo=TIMEZONE))

    logger.info("Silent Ruins bot started. Photo times: %s | Music times: %s", PHOTO_TIMES, MUSIC_TIMES)
    app.run_polling()


if __name__ == "__main__":
    main()
