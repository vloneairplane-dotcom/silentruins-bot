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

# Search terms used to pull mood-matched photos from Unsplash.
# Feel free to edit/extend this list to steer the channel's visual mood.
MOOD_KEYWORDS = [
    "abandoned ruins", "foggy forest", "gothic architecture", "misty mountains",
    "old library candlelight", "rain on window at night", "melancholic landscape",
    "dark academia aesthetic", "ancient castle ruins", "moody autumn forest",
    "lonely lighthouse fog", "abandoned cathedral", "night rain city street",
    "withered roses", "moonlit graveyard", "empty gothic hallway",
    "solitude nature dusk", "ruined monastery", "stormy sea cliff",
    "candle shadows dark room", "black and white rain",
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


def is_admin(update: Update) -> bool:
    return bool(update.effective_user) and update.effective_user.id == ADMIN_USER_ID


# ---------------------------------------------------------------------------
# Unsplash
# ---------------------------------------------------------------------------
def fetch_random_photo():
    query = random.choice(MOOD_KEYWORDS)
    resp = requests.get(
        "https://api.unsplash.com/photos/random",
        params={"query": query, "orientation": "portrait"},
        headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    # Unsplash API guidelines require pinging the download endpoint whenever
    # a photo is actually used, and crediting the photographer + Unsplash.
    try:
        requests.get(
            data["links"]["download_location"],
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10,
        )
    except requests.RequestException:
        logger.warning("Could not ping Unsplash download endpoint")

    photographer = data["user"]["name"]
    photographer_link = data["user"]["links"]["html"] + "?utm_source=silent_ruins_bot&utm_medium=referral"
    photo_url = data["urls"]["regular"]
    caption = f"📷 {photographer} / Unsplash\n{photographer_link}"
    return photo_url, caption


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
        url, caption = fetch_random_photo()
        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=url, caption=caption)
        logger.info("Posted photo")
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

    file_id = library["unplayed"].pop(0)
    save_library(library)

    try:
        await context.bot.send_audio(chat_id=CHANNEL_ID, audio=file_id)
        logger.info("Posted music")
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
        "برای اضافه کردن آهنگ، کافیه فایل صوتی رو همینجا (پیوی) برام بفرستی."
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

    library = load_library()
    title = getattr(audio, "title", None) or "بدون‌نام"
    library["tracks"].append({"file_id": audio.file_id, "title": title})
    save_library(library)
    await update.message.reply_text(f"✅ «{title}» اضافه شد. (مجموع کتابخونه: {len(library['tracks'])})")


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
