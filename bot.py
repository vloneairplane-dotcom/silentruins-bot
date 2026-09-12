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
import sys
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
GATE_MAX_REJECTIONS = int(os.getenv("GATE_MAX_REJECTIONS", "2"))
GATE_EMERGENCY_FLOOR = int(os.getenv("GATE_EMERGENCY_FLOOR", str(QUALITY_THRESHOLD - 12)))
CAPTION_EMOJI = os.getenv("CAPTION_EMOJI", "true").strip().lower() in {"1", "true", "yes", "on"}
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
    "gate_rejects": 0,
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
    if s.get("mood_queue_version") != 2 or len(unique) != len(q) or set(unique) != set(ROTATION):
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
        r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": PEXELS_KEY}, params={"query": query, "per_page": 15, "orientation": "portrait"}, timeout=15)
        r.raise_for_status()
        return r.json().get("photos", [])
    except Exception as e:
        log.warning("Pexels failed: %s", e)
        return []


def _photo_candidates(mood: str, state: dict) -> list[dict]:
    recent = set(state.get("recent_images", [])[-10:])
    queries = MOODS[mood]["queries"][:]
    random.shuffle(queries)
    photos = []
    seen = set(recent)
    for q in queries[:3]:
        for p in _pexels(q):
            src = p.get("src") or {}
            url = src.get("large2x") or src.get("large")
            if not url or url in seen:
                continue
            seen.add(url)
            photos.append({"url": url, "query": q, "alt": p.get("alt", ""), "luminance": _luminance(p.get("avg_color")), "width": p.get("width", 0), "height": p.get("height", 0)})
        if len(photos) >= 12:
            break
    return photos


def _pick_photo(photos: list[dict], mood: str) -> dict | None:
    if not photos:
        return None
    ranked = sorted(photos, key=lambda p: image_score(p, mood), reverse=True)
    return random.choice(ranked[:min(5, len(ranked))])


def _select_track(lib: dict, mood: str, state: dict, preview: bool = False):
    return choose_music(lib["tracks"], mood, state.get("recent_track_ids", []), state.get("preview_track_ids", []) if preview else [])


def build_package(preview=False) -> dict | None:
    state = load_state(); lib = load_library(); mood = choose_mood(state); best = None
    # عکس‌ها فقط یک‌بار در هر build از Pexels گرفته می‌شن (نه در هر تلاش) تا سهمیه هدر نره
    photos_pool = _photo_candidates(mood, state) if SEND_PHOTOS else []
    for _ in range(max(1, MAX_ATTEMPTS)):
        caption = choose_caption(mood, state.get("recent_caption_hashes", []) + state.get("preview_caption_hashes", [])[-25:])
        track = _select_track(lib, mood, state, preview=preview)
        photo = _pick_photo(photos_pool, mood)
        score = quality_score(mood, caption, track, photo)
        package = {"mood": mood, "caption": caption, "track": track, "photo": photo, "score": score}
        if best is None or score["overall"] > best["score"]["overall"]: best = package
        if score["overall"] >= QUALITY_THRESHOLD: break
    return best


def _audio_caption(track: dict) -> str:
    return f"🎧 {track.get('performer') or 'Unknown'} — {track.get('title') or 'Unknown'}\n\n{SIGNATURE}"


def _final_caption(package: dict) -> str:
    """کپشن نهایی پست: متن + ایموجی مرتبط با حس (قابل خاموش شدن با CAPTION_EMOJI=false) + امضا"""
    caption = package["caption"]
    if CAPTION_EMOJI:
        emojis = MOODS[package["mood"]].get("emojis") or [MOODS[package["mood"]]["emoji"]]
        caption = f"{caption} {random.choice(emojis)}"
    return f"{caption}\n\n{SIGNATURE}"


async def send_package(context: ContextTypes.DEFAULT_TYPE, package: dict, preview=False):
    caption = _final_caption(package); photo = package.get("photo"); track = package.get("track")
    if photo:
        try:
            data = requests.get(photo["url"], timeout=20).content; bio = io.BytesIO(data); bio.name = "silentruins.jpg"; photo_msg = await context.bot.send_photo(CHANNEL_ID, photo=bio, caption=caption)
        except Exception:
            log.exception("Photo send failed"); photo_msg = await context.bot.send_message(CHANNEL_ID, caption=caption)
    else:
        photo_msg = await context.bot.send_message(CHANNEL_ID, caption=caption)
    if track:
        await context.bot.send_audio(CHANNEL_ID, audio=track["file_id"], caption=_audio_caption(track), title=track.get("title"), performer=track.get("performer"))
    return photo_msg


def commit_package(package: dict):
    state = load_state(); track = package.get("track"); photo = package.get("photo"); mood = package["mood"]
    state["recent_moods"] = (state.get("recent_moods", []) + [mood])[-6:]
    state["recent_track_ids"] = (state.get("recent_track_ids", []) + [track["file_id"] if track else ""])[-MUSIC_COOLDOWN:]
    state["recent_images"] = (state.get("recent_images", []) + [photo["url"] if photo else ""])[-12:]
    h = hashlib.sha256(normalize(package["caption"]).encode()).hexdigest(); state["recent_caption_hashes"] = (state.get("recent_caption_hashes", []) + [h])[-25:]
    _advance_mood(state, mood); state["last_post_at"] = int(time.time()); save_state(state)
    lib = load_library()
    if track:
        lib["unplayed"] = [x for x in lib.get("unplayed", []) if x != track["file_id"]]
        if not lib["unplayed"]: lib["unplayed"] = [t["file_id"] for t in lib["tracks"] if t["file_id"] not in state["recent_track_ids"]] or [t["file_id"] for t in lib["tracks"]]
        save_library(lib); DB.track_played(track["file_id"])
    DB.post_success(mood, package["caption"], track.get("file_id") if track else None, photo.get("url") if photo else None, package["score"]["overall"])


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str):
    for aid in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=aid, text=text)
        except Exception:
            pass


async def _commit_publish(context: ContextTypes.DEFAULT_TYPE, package: dict):
    await send_package(context, package)
    commit_package(package)
    state = load_state()
    state["gate_rejects"] = 0
    save_state(state)
    log.info("Published mood=%s quality=%s", package["mood"], package["score"]["overall"])


async def post_once(context: ContextTypes.DEFAULT_TYPE, force=False):
    if load_state().get("paused") and not force: return
    package = None
    try:
        package = build_package(False)
        if not package: return
        sc = package["score"]
        if force or sc["overall"] >= QUALITY_THRESHOLD:
            await _commit_publish(context, package)
            return

        # رد کیفیت: شمارش پیاپی + نوتیفای ادمین + fallback اضطراری (دیگه ساکت نمی‌مونیم)
        state = load_state()
        rejects = int(state.get("gate_rejects", 0)) + 1
        state["gate_rejects"] = rejects
        save_state(state)
        log.warning("Package rejected (rejects=%s): quality=%s", rejects, sc["overall"])

        detail = (
            f"🌗 {MOODS[package['mood']]['fa']} | 📝 {sc['text']} | 🖼 {sc['image']} | "
            f"🎧 {sc['music']} | 🔗 {sc['coherence']} | ⭐ {sc['overall']}/{QUALITY_THRESHOLD}"
        )
        if rejects >= GATE_MAX_REJECTIONS:
            if sc["overall"] >= GATE_EMERGENCY_FLOOR:
                await _commit_publish(context, package)
                await notify_admins(
                    context,
                    f"🆘 پست خودکار {rejects} بار پشت‌سر رد شده بود؛ این دور با کف اضطراری منتشر شد.\n{detail}\n"
                    "برای بهتر شدن کیفیت، MP3 جدید با حس متنوع اضافه کن.",
                )
            else:
                await notify_admins(
                    context,
                    f"⚠️ پست خودکار {rejects} بار پشت‌سر رد شده و این دور حتی به کف اضطراری ({GATE_EMERGENCY_FLOOR}) هم نرسید؛ چیزی منتشر نشد.\n{detail}\n"
                    "پیشنهاد: کتابخانه‌ی آهنگ رو گسترش بده یا QUALITY_THRESHOLD رو تنظیم کن.",
                )
    except Exception as e:
        log.exception("Publish failed"); DB.post_failed(package.get("mood") if package else None, package.get("caption", "") if package else "", e)


async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیش‌نمایش ادمین: با تشخیص کامل، بدون ضعیف کردن استاندارد پست خودکار."""
    if not is_admin(update): return
    target = update.callback_query.message if getattr(update, "callback_query", None) else update.message
    package = build_package(True)
    if not package:
        await target.reply_text("❌ Preview نتوانست هیچ پکیج قابل‌بررسی بسازد."); return
    sc = package["score"]
    if sc["image"] < 68 or sc["music"] < 68 or sc["overall"] < 75:
        await target.reply_text(
            "⚠️ بهترین گزینه‌ی این دور هنوز ضعیف بود.\n"
            f"🌗 حس: {MOODS[package['mood']]['fa']}\n"
            f"📝 متن: {sc['text']} | 🖼 عکس: {sc['image']} | 🎧 آهنگ: {sc['music']} | 🔗 هماهنگی: {sc['coherence']}\n"
            f"⭐ کلی: {sc['overall']}/100\n"
            "این فقط Preview بود و استاندارد پست خودکار همچنان حفظه."
        )
        return
    detail = (
        f"🌗 حس این پست: {MOODS[package['mood']]['fa']} {MOODS[package['mood']]['emoji']}\n"
        f"⭐ کیفیت: {sc['overall']}/100\n"
        f"📝 متن: {sc['text']} | 🖼 عکس: {sc['image']} | 🎧 آهنگ: {sc['music']} | 🔗 هماهنگی: {sc['coherence']}"
    )
    caption = f"{_final_caption(package)}\n\n{detail}"
    photo = package.get("photo")
    try:
        if photo:
            response = requests.get(photo["url"], timeout=20)
            response.raise_for_status()
            bio = io.BytesIO(response.content); bio.name = "preview.jpg"
            await target.reply_photo(photo=bio, caption=caption)
        else:
            await target.reply_text(caption)
        track = package.get("track")
        if track:
            await target.reply_audio(audio=track["file_id"], caption=_audio_caption(track), title=track.get("title"), performer=track.get("performer"))
    except Exception as exc:
        log.exception("Preview send failed")
        await target.reply_text(f"❌ ارسال Preview شکست خورد: {exc}")
        return
    state = load_state(); mood = package["mood"]
    state["preview_moods"] = (state.get("preview_moods", []) + [mood])[-12:]
    if package.get("track"):
        state["preview_track_ids"] = (state.get("preview_track_ids", []) + [package["track"]["file_id"]])[-25:]
    h = hashlib.sha256(normalize(package["caption"]).encode()).hexdigest()
    state["preview_caption_hashes"] = (state.get("preview_caption_hashes", []) + [h])[-25:]
    _advance_mood(state, mood); save_state(state)


async def manual_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await post_once(context, force=True); await update.message.reply_text("✅ پست ساخته و ارسال شد.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("🥀 SilentRuins v6\nبرای دریافت Preview: /preview\nبرای پنل مدیریت: /panel")


async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    kb = [[InlineKeyboardButton("👁 Preview", callback_data="preview"), InlineKeyboardButton("🚀 Post", callback_data="post")], [InlineKeyboardButton("⏸ Pause", callback_data="pause"), InlineKeyboardButton("▶️ Resume", callback_data="resume")], [InlineKeyboardButton("📊 Stats", callback_data="stats"), InlineKeyboardButton("🎵 Songs", callback_data="songs")], [InlineKeyboardButton("🕐 Schedule", callback_data="schedule"), InlineKeyboardButton("💾 Backup", callback_data="backup")]]
    await update.message.reply_text("🥀 SilentRuins Control", reply_markup=InlineKeyboardMarkup(kb))


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پنل شیشه‌ای: همه‌ی دکمه‌ها (+ aliasهای رایج) با پیام واضح، هیچ دکمه‌ی بی‌جوابی."""
    q = update.callback_query
    if not q or not is_admin(update):
        if q: await q.answer("فقط ادمینه 🥀", show_alert=True)
        return
    data = (q.data or "").strip().lower()
    await q.answer()
    target = q.message
    action = data
    for prefix in ("panel_", "menu_", "sr_"):
        if action.startswith(prefix):
            action = action[len(prefix):]
            break
    aliases = {
        "preview_post": "preview", "preview_now": "preview",
        "post_now": "post", "publish": "post",
        "stop": "pause", "start": "resume",
        "report": "stats", "statistics": "stats",
        "music": "songs", "library": "songs",
        "times": "schedule", "backup_now": "backup",
    }
    action = aliases.get(action, action)
    try:
        if action == "preview":
            await preview(update, context)
        elif action == "post":
            await post_once(context, True)
            await target.reply_text("✅ دستور Post اجرا شد.")
        elif action == "pause":
            s = load_state(); s["paused"] = True; save_state(s)
            await target.reply_text("⏸ زمان‌بندی متوقف شد.")
        elif action == "resume":
            s = load_state(); s["paused"] = False; save_state(s)
            await target.reply_text("▶️ زمان‌بندی فعال شد.")
        elif action == "stats":
            x = DB.summary()
            await target.reply_text(
                "📊 SilentRuins\n"
                f"پست موفق: {x['posts']}\n"
                f"خطا: {x['failed']}\n"
                f"۲۴ ساعت اخیر: {x['today']}\n"
                f"میانگین کیفیت: {x['avg_quality']}/100\n"
                f"آهنگ‌ها: {x['tracks']}"
            )
        elif action == "songs":
            tracks = load_library()["tracks"]
            if not tracks:
                await target.reply_text("🎵 کتابخانه خالی است.")
            else:
                lines = [f"🎵 Music Library: {len(tracks)} آهنگ"]
                for i, track in enumerate(tracks[-50:], 1):
                    mood = MOODS.get(track.get("mood"), {}).get("fa", track.get("mood", "?"))
                    lines.append(f"{i}. {track.get('performer', '?')} — {track.get('title', '?')} [{mood}]")
                await target.reply_text("\n".join(lines))
        elif action == "schedule":
            s = load_state(); status = "⏸ متوقف" if s.get("paused") else "▶️ فعال"
            await target.reply_text(f"🕐 Schedule: {', '.join(POST_TIMES)}\n🌍 {TZ_NAME}\n{status}\nThreshold: {QUALITY_THRESHOLD}")
        elif action == "backup":
            stamp = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
            path = BACKUP_DIR / f"silentruins_{stamp}.zip"
            save_library(load_library()); save_state(load_state())
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for p in (LIBRARY_FILE, STATE_FILE, DB_FILE):
                    if p.exists(): z.write(p, p.name)
            with path.open("rb") as f:
                await target.reply_document(f, filename=path.name, caption="💾 SilentRuins backup")
        else:
            await target.reply_text(f"⚠️ دکمه ناشناخته است: {data}")
    except Exception as exc:
        log.exception("Panel callback failed: %s", data)
        await target.reply_text(f"❌ اجرای دکمه {data} با خطا مواجه شد: {exc}")


async def add_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not update.message or not update.message.audio: return
    a=update.message.audio; lib=load_library(); mood=(context.user_data.get("pending_mood") or "lonely")
    track={"file_id":a.file_id,"title":a.title or "Unknown","performer":a.performer or "Unknown","mood":mood,"added_at":int(time.time())}; existing={t["file_id"] for t in lib["tracks"]}
    if track["file_id"] not in existing:
        lib["tracks"].append(track); lib["unplayed"].append(track["file_id"]); save_library(lib); DB.track_upsert(track); await update.message.reply_text(f"🎵 اضافه شد: {track['performer']} — {track['title']}\nحس: {MOODS.get(mood,{}).get('fa',mood)}")
    else: await update.message.reply_text("ℹ️ این آهنگ قبلاً اضافه شده.")


async def music_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    mood=(context.args[0].lower() if context.args else "lonely")
    if mood not in MOODS: mood="lonely"
    context.user_data["pending_mood"]=mood; await update.message.reply_text(f"🎵 آهنگ بعدی را بفرست. حس انتخاب‌شده: {MOODS[mood]['fa']} {MOODS[mood]['emoji']}")


async def songs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    tracks=load_library()["tracks"]
    if not tracks: await update.message.reply_text("🎵 کتابخانه خالی است."); return
    lines=[f"🎵 Music Library: {len(tracks)} آهنگ"]+[f"{i+1}. {t.get('performer','?')} — {t.get('title','?')} [{MOODS.get(t.get('mood'),{}).get('fa',t.get('mood'))}]" for i,t in enumerate(tracks[-50:])]
    await update.message.reply_text("\n".join(lines))


async def find_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    query=normalize(" ".join(context.args)); tracks=load_library()["tracks"]; hits=[t for t in tracks if query in normalize(f"{t.get('title')} {t.get('performer')} {t.get('mood')}")]
    await update.message.reply_text("\n".join([f"🎵 {t.get('performer')} — {t.get('title')}" for t in hits[:20]]) or "پیدا نشد.")


async def mood_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if not context.args or context.args[0] not in MOODS: await update.message.reply_text("حس‌ها: " + ", ".join(MOODS)); return
    context.user_data["pending_mood"]=context.args[0]; await update.message.reply_text(f"حس بعدی: {MOODS[context.args[0]]['fa']}")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    s=load_state(); s["paused"]=True; save_state(s); await update.message.reply_text("⏸ زمان‌بندی متوقف شد.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    s=load_state(); s["paused"]=False; save_state(s); await update.message.reply_text("▶️ زمان‌بندی فعال شد.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    x=DB.summary(); await update.message.reply_text(f"📊 SilentRuins\nپست موفق: {x['posts']}\nخطا: {x['failed']}\n۲۴ ساعت اخیر: {x['today']}\nمیانگین کیفیت: {x['avg_quality']}/100\nآهنگ‌ها: {x['tracks']}")


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE): await stats(update, context)


async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    s=load_state(); status="⏸ متوقف" if s.get("paused") else "▶️ فعال"; await update.message.reply_text(f"🕐 Schedule: {', '.join(POST_TIMES)}\n🌍 {TZ_NAME}\n{status}\nThreshold: {QUALITY_THRESHOLD}")


async def jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    jobs=context.job_queue.jobs(); await update.message.reply_text("\n".join([f"• {j.name}" for j in jobs]) or "هیچ job فعالی نیست.")


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    stamp=datetime.now(TZ).strftime("%Y%m%d_%H%M%S"); target=BACKUP_DIR/f"silentruins_{stamp}.zip"; lib=load_library(); state=load_state(); save_library(lib); save_state(state)
    with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as z:
        for p in (LIBRARY_FILE,STATE_FILE,DB_FILE):
            if p.exists(): z.write(p,p.name)
    with target.open("rb") as f: await update.message.reply_document(f,filename=target.name,caption="💾 SilentRuins backup")


async def delete_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("مثال: /del 3"); return
    idx=int(context.args[0])-1; lib=load_library()
    if idx<0 or idx>=len(lib["tracks"]): await update.message.reply_text("شماره نامعتبر."); return
    track=lib["tracks"].pop(idx); lib["unplayed"]=[x for x in lib["unplayed"] if x!=track["file_id"]]; save_library(lib); DB.track_delete(track["file_id"]); await update.message.reply_text(f"🗑 حذف شد: {track.get('title')}")


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    lib=load_library(); await update.message.reply_text(f"🟢 Healthy\nDATA_DIR: {DATA_DIR}\nVolume: {VOLUME_DIR or 'not detected'}\nSongs: {len(lib['tracks'])}")


async def scheduled_job(context: ContextTypes.DEFAULT_TYPE): await post_once(context)


def install_schedule(app: Application):
    jq=app.job_queue
    if POST_INTERVAL: jq.run_repeating(scheduled_job,interval=POST_INTERVAL*3600,first=30,name="silentruins-interval")
    else:
        for raw in POST_TIMES:
            try: h,m=map(int,raw.split(":",1)); jq.run_daily(scheduled_job,time=dtime(h,m,tzinfo=TZ),name=f"silentruins-{raw}")
            except Exception: log.warning("Bad POST_TIMES value: %s",raw)


async def post_init(app: Application):
    sync_tracks(); install_schedule(app); log.info("SilentRuins v6 online | data=%s | songs=%s | mood_queue=%s",DATA_DIR,len(load_library()["tracks"]),load_state().get("mood_queue"))


def main():
    app=Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("preview",preview)); app.add_handler(CommandHandler("post",manual_post)); app.add_handler(CommandHandler("panel",panel)); app.add_handler(CommandHandler("pause",pause)); app.add_handler(CommandHandler("resume",resume)); app.add_handler(CommandHandler("stats",stats)); app.add_handler(CommandHandler("report",report)); app.add_handler(CommandHandler("songs",songs)); app.add_handler(CommandHandler("music",music_cmd)); app.add_handler(CommandHandler("findsong",find_song)); app.add_handler(CommandHandler("mood",mood_cmd)); app.add_handler(CommandHandler("schedule",schedule_cmd)); app.add_handler(CommandHandler("jobs",jobs)); app.add_handler(CommandHandler("backup",backup)); app.add_handler(CommandHandler("del",delete_song)); app.add_handler(CommandHandler("health",health)); app.add_handler(CallbackQueryHandler(callback)); app.add_handler(MessageHandler(filters.AUDIO,add_audio))
    app.run_polling(drop_pending_updates=True,allowed_updates=Update.ALL_TYPES)


def _apply_intelligence():
    """لایه‌های هوش (Music/Coherence) رو مستقیم به همین ماژول وصل می‌کنه تا
    رفتار `python bot.py` و `python panel_runtime.py` یکسان بشه."""
    global MAX_ATTEMPTS
    try:
        import music_intelligence
        import coherence_intelligence
        music_intelligence.apply(sys.modules[__name__])
        coherence_intelligence.apply(sys.modules[__name__])
        MAX_ATTEMPTS = max(MAX_ATTEMPTS, 24)
    except Exception:
        log.exception("Intelligence layers failed to apply")


_apply_intelligence()


if __name__ == "__main__": main()
