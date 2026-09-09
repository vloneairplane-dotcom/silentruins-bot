"""SilentRuins Bot v6 🥀
Direct production runtime with a persistent editorial mood queue.
Preview and Auto Post share one six-mood rotation; package retries never consume it.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
import time
import zipfile
import hashlib
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from content_engine import MOODS, SIGNATURE, choose_caption, choose_music, image_score, quality_score, normalize
from database import Database

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("silentruins")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", os.getenv("ADMIN_USER_ID", "")).split(",") if x.strip().lstrip("-").isdigit()}
CHANNEL_RAW = os.getenv("CHANNEL", os.getenv("CHANNEL_ID", ""))
if not CHANNEL_RAW:
    raise RuntimeError("CHANNEL is missing")
CHANNEL_ID = int(CHANNEL_RAW) if CHANNEL_RAW.lstrip("-").isdigit() else CHANNEL_RAW

TZ_NAME = os.getenv("TIMEZONE", "Asia/Tehran")
try:
    TZ = ZoneInfo(TZ_NAME)
except Exception:
    TZ = ZoneInfo("Asia/Tehran")

VOLUME_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
DATA_DIR = Path(os.getenv("DATA_DIR") or VOLUME_DIR or ("/data" if os.getenv("RAILWAY_ENVIRONMENT") else "./data")).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
LIBRARY_FILE = DATA_DIR / "library.json"
STATE_FILE = DATA_DIR / "state.json"
DB_FILE = DATA_DIR / "silentruins.db"
DB = Database(str(DB_FILE))

PEXELS_KEY = os.getenv("PEXELS_API_KEY") or os.getenv("PIXEL_API_KEY")
SEND_PHOTOS = os.getenv("SEND_PHOTOS", "true").lower() in {"1", "true", "yes", "on"}
PHOTO_CREDIT = os.getenv("PHOTO_CREDIT", "false").lower() in {"1", "true", "yes", "on"}
QUALITY_THRESHOLD = int(os.getenv("QUALITY_THRESHOLD", "82"))
MAX_ATTEMPTS = int(os.getenv("MAX_CANDIDATES", "8"))
MUSIC_COOLDOWN = int(os.getenv("MUSIC_COOLDOWN_POSTS", "8"))
POST_TIMES = [x.strip() for x in os.getenv("POST_TIMES", "10:00,16:00,22:00,02:00").split(",") if x.strip()]
POST_INTERVAL = os.getenv("POST_INTERVAL_HOURS")
try:
    POST_INTERVAL = float(POST_INTERVAL) if POST_INTERVAL else None
except ValueError:
    POST_INTERVAL = None

ROTATION = ("rain", "love", "night", "lonely", "tired", "ruins")
DEFAULT_LIBRARY = {"tracks": [], "unplayed": []}
DEFAULT_STATE = {
    "paused": False,
    "recent_moods": [],
    "recent_track_ids": [],
    "recent_caption_hashes": [],
    "recent_images": [],
    "preview_track_ids": [],
    "preview_moods": [],
    "preview_caption_hashes": [],
    "mood_queue": list(ROTATION),
    "mood_queue_version": 2,
    "last_post_at": 0,
}


def _read_json(path: Path, default: dict) -> dict:
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else default.copy()
    except Exception:
        log.exception("Cannot read %s", path)
    return default.copy()


def _write_json(path: Path, value: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_library():
    lib = _read_json(LIBRARY_FILE, DEFAULT_LIBRARY)
    lib.setdefault("tracks", [])
    lib.setdefault("unplayed", [])
    tracks = []
    ids = []
    for t in lib["tracks"]:
        if not isinstance(t, dict) or not t.get("file_id"):
            continue
        t.setdefault("title", "Unknown")
        t.setdefault("performer", "Unknown")
        t.setdefault("mood", "lonely")
        t.setdefault("added_at", int(time.time()))
        tracks.append(t)
        ids.append(t["file_id"])
    lib["tracks"] = tracks
    lib["unplayed"] = [x for x in lib.get("unplayed", []) if x in ids]
    return lib


def save_library(lib):
    _write_json(LIBRARY_FILE, lib)


def _next_queue_after(last: str | None) -> list[str]:
    if last in ROTATION:
        i = (ROTATION.index(last) + 1) % len(ROTATION)
        return list(ROTATION[i:]) or list(ROTATION)
    return list(ROTATION)


def load_state():
    s = _read_json(STATE_FILE, DEFAULT_STATE)
    for k, v in DEFAULT_STATE.items():
        s.setdefault(k, v.copy() if isinstance(v, list) else v)

    raw = s.get("mood_queue", [])
    q = [m for m in raw if m in ROTATION] if isinstance(raw, list) else []
    unique = list(dict.fromkeys(q))
    # A v2 queue is intentionally allowed to contain only the remaining moods.
    # The previous check incorrectly required all six moods on every load, which
    # reset the queue after every consumed mood and broke deterministic rotation.
    if s.get("mood_queue_version") != 2 or len(unique) != len(q):
        history = list(s.get("recent_moods", [])) + list(s.get("preview_moods", []))
        last = next((m for m in reversed(history) if m in ROTATION), None)
        q = _next_queue_after(last)
        s["mood_queue_version"] = 2
    else:
        q = unique
    if not q:
        q = list(ROTATION)
    s["mood_queue"] = q
    return s


def save_state(s):
    _write_json(STATE_FILE, s)


def _peek_mood(state: dict) -> str:
    queue = [m for m in state.get("mood_queue", []) if m in ROTATION]
    return queue[0] if queue else ROTATION[0]


def _advance_mood(state: dict, mood: str):
    queue = [m for m in state.get("mood_queue", []) if m in ROTATION]
    if queue and queue[0] == mood:
        queue.pop(0)
    elif mood in queue:
        queue.remove(mood)
    if not queue:
        queue = list(ROTATION)
    state["mood_queue"] = queue
    state["mood_queue_version"] = 2


def choose_mood(state, hour=None):
    return _peek_mood(state)


def is_admin(update: Update):
    return bool(update.effective_user and update.effective_user.id in ADMIN_IDS)


def sync_tracks():
    for t in load_library()["tracks"]:
        DB.track_upsert(t)


def _luminance(hex_color: str | None) -> float:
    if not hex_color:
        return 62.0
    try:
        h = hex_color.lstrip("#")
        r, g, b = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 * 100
    except Exception:
        return 62.0


def _pexels(query: str) -> list[dict]:
    if not PEXELS_KEY or not SEND_PHOTOS:
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_KEY},
            params={"query": query, "per_page": 15, "orientation": "portrait"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("photos", [])
    except Exception as e:
        log.warning("Pexels failed: %s", e)
        return []


def _photo_candidates(mood: str, state: dict) -> list[dict]:
    blocked = set(state.get("recent_images", [])[-12:])
    result = []
    seen = set(blocked)
    queries = list(MOODS.get(mood, {}).get("visual_queries", []))
    random.shuffle(queries)
    for query in queries[:3]:
        for p in _pexels(query):
            src = p.get("src") or {}
            url = src.get("large2x") or src.get("large") or src.get("original")
            if not url or url in seen:
                continue
            seen.add(url)
            p["url"] = url
            p["alt"] = p.get("alt") or ""
            result.append(p)
    random.shuffle(result)
    return result


def _download_photo(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.content
    except Exception as e:
        log.warning("Photo download failed: %s", e)
        return None


def _caption_hash(text: str) -> str:
    return hashlib.sha1(normalize(text).encode("utf-8")).hexdigest()


def _track_key(track: dict) -> str:
    return str(track.get("id") or track.get("file_id") or "")


def _track_allowed(track: dict, state: dict, preview: bool) -> bool:
    key = _track_key(track)
    recent = state.get("preview_track_ids", []) if preview else state.get("recent_track_ids", [])
    return key not in recent[-MUSIC_COOLDOWN:]


def _score_package(mood: str, caption: str, track: dict | None, photo: dict | None) -> dict:
    score = quality_score(mood, caption, track, photo)
    return score


def build_package(preview=False):
    state = load_state()
    mood = choose_mood(state)
    library = load_library()
    candidates = _photo_candidates(mood, state) if SEND_PHOTOS else [None]
    if not candidates:
        candidates = [None]
    best = None
    for _ in range(max(1, MAX_ATTEMPTS)):
        photo = random.choice(candidates)
        caption = choose_caption(mood, state.get("recent_caption_hashes", []) + state.get("preview_caption_hashes", []))
        track = choose_music(mood, library.get("tracks", []), state, preview=preview)
        if track and not _track_allowed(track, state, preview):
            allowed = [t for t in library.get("tracks", []) if _track_allowed(t, state, preview)]
            if allowed:
                track = random.choice(allowed)
        quality = _score_package(mood, caption, track, photo)
        quality["mood"] = mood
        quality["caption"] = caption
        quality["track"] = track
        quality["photo"] = photo
        if best is None or quality.get("overall", 0) > best.get("overall", 0):
            best = quality
        if quality.get("overall", 0) >= QUALITY_THRESHOLD:
            break
    return best


def _caption_text(package: dict) -> str:
    return f"{package['caption']}\n\n{SIGNATURE}\n\n🌗 حس این پست: {MOODS[package['mood']]['label']} {MOODS[package['mood']]['emoji']}\n⭐ کیفیت: {int(package['overall'])}/100\n📝 متن: {int(package['text'])} | 🖼 عکس: {int(package['image'])} | 🎧 آهنگ: {int(package['music'])} | 🔗 هماهنگی: {int(package['coherence'])}"


async def _send_package(bot_app, package: dict, chat_id):
    photo = package.get("photo")
    if photo and photo.get("url"):
        data = _download_photo(photo["url"])
        if data:
            await bot_app.send_photo(chat_id=chat_id, photo=io.BytesIO(data), caption=_caption_text(package))
        else:
            await bot_app.send_message(chat_id=chat_id, text=_caption_text(package))
    else:
        await bot_app.send_message(chat_id=chat_id, text=_caption_text(package))
    track = package.get("track")
    if track and track.get("file_id"):
        await bot_app.send_audio(chat_id=chat_id, audio=track["file_id"], title=track.get("title"), performer=track.get("performer"))


def commit_package(package: dict):
    state = load_state()
    mood = package.get("mood")
    _advance_mood(state, mood)
    state.setdefault("recent_moods", []).append(mood)
    state["recent_moods"] = state["recent_moods"][-12:]
    track = package.get("track")
    if track:
        key = _track_key(track)
        state.setdefault("recent_track_ids", []).append(key)
        state["recent_track_ids"] = state["recent_track_ids"][-MUSIC_COOLDOWN:]
    caption = package.get("caption") or ""
    state.setdefault("recent_caption_hashes", []).append(_caption_hash(caption))
    state["recent_caption_hashes"] = state["recent_caption_hashes"][-30:]
    photo = package.get("photo")
    if photo and photo.get("url"):
        state.setdefault("recent_images", []).append(photo["url"])
        state["recent_images"] = state["recent_images"][-12:]
    state["last_post_at"] = int(time.time())
    save_state(state)
    DB.record_post(mood, caption, _track_key(track) if track else "", photo.get("url") if photo else "", package.get("overall", 0), "success", "")


async def post_once(app):
    state = load_state()
    if state.get("paused"):
        return False
    package = build_package(preview=False)
    if not package or package.get("overall", 0) < QUALITY_THRESHOLD:
        if package:
            DB.record_post(package.get("mood", ""), package.get("caption", ""), _track_key(package.get("track")), package.get("photo", {}).get("url", "") if package.get("photo") else "", package.get("overall", 0), "failed", "quality gate")
        return False
    try:
        await _send_package(app.bot, package, CHANNEL_ID)
        commit_package(package)
        return True
    except Exception as e:
        log.exception("Post failed: %s", e)
        DB.record_post(package.get("mood", ""), package.get("caption", ""), _track_key(package.get("track")), package.get("photo", {}).get("url", "") if package.get("photo") else "", package.get("overall", 0), "failed", str(e))
        return False


async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    package = build_package(preview=True)
    if not package:
        text = "❌ نتوانستم پکیج Preview بسازم."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text)
        else:
            await update.message.reply_text(text)
        return
    if package.get("overall", 0) < max(72, QUALITY_THRESHOLD - 10):
        text = f"❌ کیفیت کافی نیست: {int(package.get('overall', 0))}/100"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text)
        else:
            await update.message.reply_text(text)
        return
    target = update.callback_query.message if update.callback_query else update.message
    try:
        await _send_package(target.get_bot() if hasattr(target, "get_bot") else context.bot, package, target.chat_id)
    except Exception:
        if update.callback_query:
            await update.callback_query.answer()
        raise
    state = load_state()
    _advance_mood(state, package.get("mood"))
    state.setdefault("preview_moods", []).append(package.get("mood"))
    state["preview_moods"] = state["preview_moods"][-30:]
    track = package.get("track")
    if track:
        state.setdefault("preview_track_ids", []).append(_track_key(track))
        state["preview_track_ids"] = state["preview_track_ids"][-MUSIC_COOLDOWN:]
    state.setdefault("preview_caption_hashes", []).append(_caption_hash(package.get("caption", "")))
    state["preview_caption_hashes"] = state["preview_caption_hashes"][-30:]
    save_state(state)
    if update.callback_query:
        await update.callback_query.answer("Preview ارسال شد")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        await update.message.reply_text("🥀 SilentRuins is online. /panel")
    else:
        await update.message.reply_text("🥀 SilentRuins")


async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    kb = [
        [InlineKeyboardButton("👁 Preview", callback_data="preview"), InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("🎵 Songs", callback_data="songs"), InlineKeyboardButton("🕒 Schedule", callback_data="schedule")],
        [InlineKeyboardButton("⏸ Pause", callback_data="pause"), InlineKeyboardButton("▶️ Resume", callback_data="resume")],
        [InlineKeyboardButton("💾 Backup", callback_data="backup")],
    ]
    await update.message.reply_text("🥀 SilentRuins Control Panel", reply_markup=InlineKeyboardMarkup(kb))


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    s = DB.summary()
    await update.message.reply_text(f"📊 Posts: {s['posts']}\n❌ Failed: {s['failed']}\n📅 Today: {s['today']}\n⭐ Avg quality: {s['avg_quality']}\n🎵 Tracks: {s['tracks']}")


async def songs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    tracks = load_library()["tracks"]
    await update.message.reply_text(f"🎵 Songs: {len(tracks)}")


async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await update.message.reply_text("🕒 " + (", ".join(POST_TIMES) if POST_TIMES else f"every {POST_INTERVAL}h"))


async def jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    names = [j.name for j in context.job_queue.jobs()]
    await update.message.reply_text("🕒 Jobs:\n" + ("\n".join(names) if names else "none"))


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    s = load_state(); s["paused"] = True; save_state(s)
    await update.message.reply_text("⏸ Paused")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    s = load_state(); s["paused"] = False; save_state(s)
    await update.message.reply_text("▶️ Resumed")


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    s = DB.summary()
    await update.message.reply_text(json.dumps(s, ensure_ascii=False, indent=2))


async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    s = load_state()
    await update.message.reply_text(f"🌗 Next mood: {MOODS[_peek_mood(s)]['label']}\nQueue: {', '.join(s.get('mood_queue', []))}")


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    stamp = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"silentruins_{stamp}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for p in (LIBRARY_FILE, STATE_FILE, DB_FILE):
            if p.exists(): z.write(p, arcname=p.name)
    await update.message.reply_document(document=str(target), caption="💾 Backup ready")


async def find_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    q = normalize(" ".join(context.args)) if context.args else ""
    tracks = load_library()["tracks"]
    hits = [t for t in tracks if q in normalize(t.get("title", "") + " " + t.get("performer", ""))]
    if not hits:
        await update.message.reply_text("❌ پیدا نشد")
        return
    await update.message.reply_text("🎵\n" + "\n".join(f"{i+1}. {t.get('title')} — {t.get('performer')}" for i, t in enumerate(hits[:20])))


async def del_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not context.args: return
    key = context.args[0]
    lib = load_library(); before = len(lib["tracks"])
    lib["tracks"] = [t for t in lib["tracks"] if _track_key(t) != key]
    save_library(lib); sync_tracks()
    await update.message.reply_text("🗑 Deleted" if len(lib["tracks"]) < before else "❌ Not found")


async def music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await songs(update, context)


async def ingest_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not update.message: return
    audio = update.message.audio
    voice = update.message.voice
    doc = update.message.document
    media = audio or voice or doc
    if not media: return
    file = await media.get_file()
    data = await file.download_as_bytearray()
    name = getattr(media, "file_name", None) or getattr(audio, "title", None) or "track"
    performer = getattr(audio, "performer", None) or "Unknown"
    mood_name = context.user_data.get("pending_mood", "lonely")
    track_id = hashlib.sha1(f"{time.time()}:{name}".encode()).hexdigest()[:10]
    lib = load_library()
    track = {"id": track_id, "file_id": media.file_id, "title": name, "performer": performer, "mood": mood_name, "added_at": int(time.time())}
    lib["tracks"].append(track)
    save_library(lib); DB.track_upsert(track)
    await update.message.reply_text(f"🎵 Added: {name}\nMood: {MOODS.get(mood_name, {}).get('label', mood_name)}")


async def set_pending_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not context.args: return
    value = context.args[0].lower()
    if value not in ROTATION: return
    context.user_data["pending_mood"] = value
    await update.message.reply_text(f"🌗 Next uploaded song mood: {MOODS[value]['label']}")


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await update.message.reply_text(f"🟢 DATA_DIR: {DATA_DIR}\nVolume: {'YES' if VOLUME_DIR else 'NO'}\nSongs: {len(load_library()['tracks'])}")


async def main_async():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("preview", preview))
    app.add_handler(CommandHandler("post", lambda u,c: post_once(c.application)))
    app.add_handler(CommandHandler("panel", panel))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("songs", songs))
    app.add_handler(CommandHandler("music", music))
    app.add_handler(CommandHandler("findsong", find_song))
    app.add_handler(CommandHandler("del", del_song))
    app.add_handler(CommandHandler("mood", mood))
    app.add_handler(CommandHandler("schedule", schedule_cmd))
    app.add_handler(CommandHandler("jobs", jobs))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("health", health))
    app.add_handler(CommandHandler("setmood", set_pending_mood))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, ingest_music))

    async def scheduled(context: ContextTypes.DEFAULT_TYPE):
        await post_once(context.application)

    if POST_INTERVAL:
        app.job_queue.run_repeating(scheduled, interval=POST_INTERVAL * 3600, first=30, name="auto")
    else:
        for raw in POST_TIMES:
            try:
                hh, mm = [int(x) for x in raw.split(":")]
                app.job_queue.run_daily(scheduled, time=dtime(hh, mm, tzinfo=TZ), name=f"auto_{raw}")
            except Exception:
                log.warning("Bad POST_TIMES entry: %s", raw)

    sync_tracks()
    log.info("SilentRuins v6 started | data=%s | songs=%d | rotation=%s", DATA_DIR, len(load_library()["tracks"]), ROTATION)
    await app.run_polling(close_loop=False)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
