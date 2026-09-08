"""SilentRuins Bot v5 🥀
A clean rebuild: one editorial pipeline, persistent state, safe scheduling,
and predictable admin controls.
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
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from content_engine import MOODS, SIGNATURE, choose_caption, choose_mood, choose_music, image_score, quality_score, music_score, normalize
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
SEND_PHOTOS = os.getenv("SEND_PHOTOS", "true").lower() in {"1","true","yes","on"}
PHOTO_CREDIT = os.getenv("PHOTO_CREDIT", "false").lower() in {"1","true","yes","on"}
QUALITY_THRESHOLD = int(os.getenv("QUALITY_THRESHOLD", "82"))
MAX_ATTEMPTS = int(os.getenv("MAX_CANDIDATES", "8"))
MUSIC_COOLDOWN = int(os.getenv("MUSIC_COOLDOWN_POSTS", "8"))
POST_TIMES = [x.strip() for x in os.getenv("POST_TIMES", "10:00,16:00,22:00,02:00").split(",") if x.strip()]
POST_INTERVAL = os.getenv("POST_INTERVAL_HOURS")
try: POST_INTERVAL = float(POST_INTERVAL) if POST_INTERVAL else None
except ValueError: POST_INTERVAL = None

DEFAULT_LIBRARY = {"tracks": [], "unplayed": []}
DEFAULT_STATE = {"paused": False, "recent_moods": [], "recent_track_ids": [], "recent_caption_hashes": [], "recent_images": [], "preview_track_ids": [], "last_post_at": 0}


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
    lib.setdefault("tracks", []); lib.setdefault("unplayed", [])
    tracks=[]; ids=[]
    for t in lib["tracks"]:
        if not isinstance(t, dict) or not t.get("file_id"): continue
        t.setdefault("title", "Unknown"); t.setdefault("performer", "Unknown"); t.setdefault("mood", "lonely")
        t.setdefault("added_at", int(time.time()))
        tracks.append(t); ids.append(t["file_id"])
    lib["tracks"] = tracks
    lib["unplayed"] = [x for x in lib.get("unplayed", []) if x in ids]
    return lib


def save_library(lib): _write_json(LIBRARY_FILE, lib)

def load_state():
    s=_read_json(STATE_FILE, DEFAULT_STATE)
    for k,v in DEFAULT_STATE.items(): s.setdefault(k, v.copy() if isinstance(v,list) else v)
    return s

def save_state(s): _write_json(STATE_FILE, s)

def is_admin(update: Update):
    return bool(update.effective_user and update.effective_user.id in ADMIN_IDS)


def sync_tracks():
    for t in load_library()["tracks"]: DB.track_upsert(t)


def _luminance(hex_color: str | None) -> float:
    if not hex_color: return 62.0
    try:
        h=hex_color.lstrip("#")
        r,g,b=[int(h[i:i+2],16) for i in (0,2,4)]
        return (0.2126*r+0.7152*g+0.0722*b)/255*100
    except Exception: return 62.0


def _pexels(query: str) -> list[dict]:
    if not PEXELS_KEY or not SEND_PHOTOS: return []
    try:
        r=requests.get("https://api.pexels.com/v1/search",headers={"Authorization":PEXELS_KEY},params={"query":query,"per_page":15,"orientation":"portrait"},timeout=15)
        r.raise_for_status()
        return r.json().get("photos", [])
    except Exception as e:
        log.warning("Pexels failed: %s", e); return []


def _photo_candidates(mood: str, state: dict) -> list[dict]:
    recent=set(state.get("recent_images", [])[-10:])
    queries=MOODS[mood]["queries"][:]
    random.shuffle(queries)
    photos=[]
    for q in queries[:3]:
        for p in _pexels(q):
            url=(p.get("src") or {}).get("large2x") or (p.get("src") or {}).get("large")
            if not url or url in recent: continue
            meta={"url":url,"query":q,"alt":p.get("alt", ""),"luminance":_luminance(p.get("avg_color"))}
            photos.append(meta)
        if len(photos)>=12: break
    return photos


def _pick_photo(photos: list[dict], mood: str) -> dict | None:
    if not photos: return None
    ranked=sorted(photos,key=lambda p:image_score(p,mood),reverse=True)
    return random.choice(ranked[:min(5,len(ranked))])


def _select_track(lib: dict, mood: str, state: dict, preview: bool=False):
    tracks=lib["tracks"]
    return choose_music(tracks,mood,state.get("recent_track_ids",[]),state.get("preview_track_ids",[]) if preview else [])


def build_package(preview=False) -> dict:
    state=load_state(); lib=load_library(); tracks=lib["tracks"]
    best=None
    for _ in range(MAX_ATTEMPTS):
        mood=choose_mood(state)
        caption=choose_caption(mood,state.get("recent_caption_hashes",[]))
        track=_select_track(lib,mood,state,preview=preview)
        photos=_photo_candidates(mood,state) if SEND_PHOTOS else []
        photo=_pick_photo(photos,mood)
        score=quality_score(mood,caption,track,photo)
        package={"mood":mood,"caption":caption,"track":track,"photo":photo,"score":score}
        if best is None or score["overall"]>best["score"]["overall"]: best=package
        if score["overall"]>=QUALITY_THRESHOLD: break
    return best


def _audio_caption(track: dict) -> str:
    title=track.get("title") or "Unknown"
    artist=track.get("performer") or "Unknown"
    return f"🎧 {artist} — {title}\n\n{SIGNATURE}"


async def send_package(context: ContextTypes.DEFAULT_TYPE, package: dict, preview=False):
    caption=f"{package['caption']}\n\n{SIGNATURE}"
    photo=package.get("photo"); track=package.get("track")
    if photo:
        try:
            data=requests.get(photo["url"],timeout=20).content
            bio=io.BytesIO(data); bio.name="silentruins.jpg"
            photo_msg=await context.bot.send_photo(CHANNEL_ID, photo=bio, caption=caption)
        except Exception:
            log.exception("Photo send failed"); photo_msg=await context.bot.send_message(CHANNEL_ID, caption=caption)
    else:
        photo_msg=await context.bot.send_message(CHANNEL_ID, caption=caption)
    if track:
        await context.bot.send_audio(CHANNEL_ID,audio=track["file_id"],caption=_audio_caption(track),title=track.get("title"),performer=track.get("performer"))
    return photo_msg


def commit_package(package: dict):
    state=load_state(); track=package.get("track"); photo=package.get("photo")
    state["recent_moods"]=(state.get("recent_moods",[])+[package["mood"]])[-6:]
    state["recent_track_ids"]=(state.get("recent_track_ids",[])+[track["file_id"] if track else ""])[-MUSIC_COOLDOWN:]
    state["recent_images"]=(state.get("recent_images",[])+[photo["url"] if photo else ""])[-12:]
    import hashlib
    h=hashlib.sha256(normalize(package["caption"]).encode()).hexdigest()
    state["recent_caption_hashes"]=(state.get("recent_caption_hashes",[])+[h])[-25:]
    state["last_post_at"]=int(time.time())
    save_state(state)
    lib=load_library()
    if track:
        lib["unplayed"]=[x for x in lib.get("unplayed",[]) if x != track["file_id"]]
        if not lib["unplayed"]:
            lib["unplayed"]= [t["file_id"] for t in lib["tracks"] if t["file_id"] not in state["recent_track_ids"]] or [t["file_id"] for t in lib["tracks"]]
        save_library(lib); DB.track_played(track["file_id"])
    DB.post_success(package["mood"],package["caption"],track.get("file_id") if track else None,photo.get("url") if photo else None,package["score"]["overall"])


async def post_once(context: ContextTypes.DEFAULT_TYPE, force=False):
    if load_state().get("paused") and not force: return
    try:
        package=build_package(False)
        if not package: return
        await send_package(context,package)
        commit_package(package)
        log.info("Published mood=%s quality=%s",package["mood"],package["score"]["overall"])
    except Exception as e:
        log.exception("Publish failed")
        DB.post_failed(package.get("mood") if 'package' in locals() else None,package.get("caption","") if 'package' in locals() else "",e)


async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    package=build_package(True)
    if not package:
        await update.message.reply_text("❌ نتونستم Preview بسازم."); return
    text=(f"🌗 حس این پست: {MOODS[package['mood']]['fa']} {MOODS[package['mood']]['emoji']}\n"
          f"⭐ کیفیت: {package['score']['overall']}/100\n"
          f"📝 متن: {package['score']['text']} | 🖼 عکس: {package['score']['image']} | 🎧 آهنگ: {package['score']['music']} | 🔗 هماهنگی: {package['score']['coherence']}")
    state=load_state(); track=package.get("track")
    state["preview_track_ids"]=(state.get("preview_track_ids",[])+[track["file_id"] if track else ""])[-25:]; save_state(state)
    caption=f"{package['caption']}\n\n{SIGNATURE}\n\n{text}"
    photo=package.get("photo")
    if photo:
        try:
            data=requests.get(photo["url"],timeout=20).content; bio=io.BytesIO(data); bio.name="preview.jpg"
            await update.message.reply_photo(photo=bio,caption=caption)
        except Exception:
            await update.message.reply_text(caption)
    else: await update.message.reply_text(caption)
    if track:
        await update.message.reply_audio(audio=track["file_id"],caption=_audio_caption(track),title=track.get("title"),performer=track.get("performer"))


async def manual_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await post_once(context,force=True); await update.message.reply_text("✅ پست ساخته و ارسال شد.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🥀 SilentRuins v5\nبرای دریافت Preview: /preview\nبرای پنل مدیریت: /panel")

async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    kb=[[InlineKeyboardButton("👁 Preview",callback_data="preview"),InlineKeyboardButton("🚀 Post",callback_data="post")],
        [InlineKeyboardButton("⏸ Pause",callback_data="pause"),InlineKeyboardButton("▶️ Resume",callback_data="resume")],
        [InlineKeyboardButton("📊 Stats",callback_data="stats"),InlineKeyboardButton("🎵 Songs",callback_data="songs")],
        [InlineKeyboardButton("🕐 Schedule",callback_data="schedule"),InlineKeyboardButton("💾 Backup",callback_data="backup")]]
    await update.message.reply_text("🥀 SilentRuins Control",reply_markup=InlineKeyboardMarkup(kb))

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(update): return
    if q.data=="preview": await preview(update,context)
    elif q.data=="post": await post_once(context,True); await q.message.reply_text("✅ ارسال شد")
    elif q.data=="pause": s=load_state();s["paused"]=True;save_state(s);await q.message.reply_text("⏸ متوقف شد")
    elif q.data=="resume": s=load_state();s["paused"]=False;save_state(s);await q.message.reply_text("▶️ ادامه پیدا کرد")
    elif q.data=="stats": await stats(update,context)
    elif q.data=="songs": await songs(update,context)
    elif q.data=="schedule": await schedule_cmd(update,context)
    elif q.data=="backup": await backup(update,context)

async def add_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not update.message or not update.message.audio: return
    a=update.message.audio
    lib=load_library(); mood=(context.user_data.get("pending_mood") or "lonely")
    track={"file_id":a.file_id,"title":a.title or "Unknown","performer":a.performer or "Unknown","mood":mood,"added_at":int(time.time())}
    existing={t["file_id"] for t in lib["tracks"]}
    if track["file_id"] not in existing:
        lib["tracks"].append(track); lib["unplayed"].append(track["file_id"]); save_library(lib); DB.track_upsert(track)
        await update.message.reply_text(f"🎵 اضافه شد: {track['performer']} — {track['title']}\nحس: {MOODS.get(mood,{}).get('fa',mood)}")
    else: await update.message.reply_text("ℹ️ این آهنگ قبلاً اضافه شده.")

async def music_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    mood=(context.args[0].lower() if context.args else "lonely")
    if mood not in MOODS: mood="lonely"
    context.user_data["pending_mood"]=mood
    await update.message.reply_text(f"🎵 آهنگ بعدی را بفرست. حس انتخاب‌شده: {MOODS[mood]['fa']} {MOODS[mood]['emoji']}")

async def songs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    tracks=load_library()["tracks"]
    if not tracks: await update.message.reply_text("🎵 کتابخانه خالی است."); return
    lines=[f"🎵 Music Library: {len(tracks)} آهنگ"]+[f"{i+1}. {t.get('performer','?')} — {t.get('title','?')} [{MOODS.get(t.get('mood'),{}).get('fa',t.get('mood'))}]" for i,t in enumerate(tracks[-50:])]
    await update.message.reply_text("\n".join(lines))

async def find_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    query=normalize(" ".join(context.args)); tracks=load_library()["tracks"]
    hits=[t for t in tracks if query in normalize(f"{t.get('title')} {t.get('performer')} {t.get('mood')}")]
    await update.message.reply_text("\n".join([f"🎵 {t.get('performer')} — {t.get('title')}" for t in hits[:20]]) or "پیدا نشد.")

async def mood_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if not context.args or context.args[0] not in MOODS: await update.message.reply_text("حس‌ها: "+", ".join(MOODS)); return
    context.user_data["pending_mood"]=context.args[0]; await update.message.reply_text(f"حس بعدی: {MOODS[context.args[0]]['fa']}")

async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    s=load_state();s["paused"]=True;save_state(s);await update.message.reply_text("⏸ زمان‌بندی متوقف شد.")

async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    s=load_state();s["paused"]=False;save_state(s);await update.message.reply_text("▶️ زمان‌بندی فعال شد.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    x=DB.summary(); await update.message.reply_text(f"📊 SilentRuins\nپست موفق: {x['posts']}\nخطا: {x['failed']}\n۲۴ ساعت اخیر: {x['today']}\nمیانگین کیفیت: {x['avg_quality']}/100\nآهنگ‌ها: {x['tracks']}")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE): await stats(update,context)

async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    s=load_state(); status="⏸ متوقف" if s.get("paused") else "▶️ فعال"
    await update.message.reply_text(f"🕐 Schedule: {', '.join(POST_TIMES)}\n🌍 {TZ_NAME}\n{status}\nThreshold: {QUALITY_THRESHOLD}")

async def jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    jobs=context.job_queue.jobs(); await update.message.reply_text("\n".join([f"• {j.name}" for j in jobs]) or "هیچ job فعالی نیست.")

async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    stamp=datetime.now(TZ).strftime("%Y%m%d_%H%M%S"); target=BACKUP_DIR/f"silentruins_{stamp}.zip"
    lib=load_library(); state=load_state(); save_library(lib); save_state(state)
    with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as z:
        for p in (LIBRARY_FILE,STATE_FILE,DB_FILE):
            if p.exists(): z.write(p,p.name)
    with target.open("rb") as f: await update.message.reply_document(f,filename=target.name,caption="💾 SilentRuins backup")

async def delete_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("مثال: /del 3"); return
    idx=int(context.args[0])-1; lib=load_library()
    if idx<0 or idx>=len(lib["tracks"]): await update.message.reply_text("شماره نامعتبر."); return
    track=lib["tracks"].pop(idx); lib["unplayed"]=[x for x in lib["unplayed"] if x!=track["file_id"]]; save_library(lib); DB.track_delete(track["file_id"])
    await update.message.reply_text(f"🗑 حذف شد: {track.get('title')}")

async def health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    lib=load_library(); await update.message.reply_text(f"🟢 Healthy\nDATA_DIR: {DATA_DIR}\nVolume: {VOLUME_DIR or 'not detected'}\nSongs: {len(lib['tracks'])}")

async def scheduled_job(context: ContextTypes.DEFAULT_TYPE): await post_once(context)


def install_schedule(app: Application):
    jq=app.job_queue
    if POST_INTERVAL:
        jq.run_repeating(scheduled_job, interval=POST_INTERVAL*3600, first=30, name="silentruins-interval")
    else:
        for raw in POST_TIMES:
            try:
                h,m=map(int,raw.split(":",1)); jq.run_daily(scheduled_job,time=dtime(h,m,tzinfo=TZ),name=f"silentruins-{raw}")
            except Exception: log.warning("Bad POST_TIMES value: %s",raw)

async def post_init(app: Application):
    sync_tracks(); install_schedule(app)
    log.info("SilentRuins v5 online | data=%s | songs=%s",DATA_DIR,len(load_library()["tracks"]))


def main():
    app=Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("preview",preview)); app.add_handler(CommandHandler("post",manual_post)); app.add_handler(CommandHandler("panel",panel))
    app.add_handler(CommandHandler("pause",pause)); app.add_handler(CommandHandler("resume",resume)); app.add_handler(CommandHandler("stats",stats)); app.add_handler(CommandHandler("report",report)); app.add_handler(CommandHandler("songs",songs)); app.add_handler(CommandHandler("music",music_cmd)); app.add_handler(CommandHandler("findsong",find_song)); app.add_handler(CommandHandler("mood",mood_cmd)); app.add_handler(CommandHandler("schedule",schedule_cmd)); app.add_handler(CommandHandler("jobs",jobs)); app.add_handler(CommandHandler("backup",backup)); app.add_handler(CommandHandler("del",delete_song)); app.add_handler(CommandHandler("health",health))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.AUDIO,add_audio))
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__": main()
