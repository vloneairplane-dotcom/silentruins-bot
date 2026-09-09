"""SilentRuins Preview Runtime v6.2.
Keeps the production bot structure intact while making Preview selection smarter.
"""
from __future__ import annotations

import hashlib
import io
import random
import re
import requests

import bot
import content_engine as engine
from telegram import Update
from telegram.ext import ContextTypes

# Preview can search harder without lowering the Auto Post quality threshold.
bot.MAX_ATTEMPTS = max(bot.MAX_ATTEMPTS, 24)

# Broader editorial compatibility. The old scorer treated many valid sad tracks
# as weak when their stored tag did not exactly match the six new moods.
MUSIC_COMPAT = {
    "rain": {"rain", "melancholy", "sadness", "emotional", "missing", "memories", "night", "loneliness"},
    "night": {"night", "dark", "melancholy", "loneliness", "emotional", "missing", "memories", "heartbreak", "breakup"},
    "lonely": {"loneliness", "lonely", "missing", "emotional", "melancholy", "heartbreak", "breakup", "memories", "dark"},
    "love": {"heartbreak", "breakup", "missing", "memories", "romantic", "unrequited love", "betrayal", "regret", "emotional", "distance"},
    "tired": {"breakdown", "depression", "melancholy", "emotional", "loneliness", "regret", "sadness", "dark"},
    "ruins": {"melancholy", "dark", "memories", "depression", "night", "emotional", "loneliness", "sadness", "regret"},
}

GENERAL_SAD = {"heartbreak", "breakup", "missing", "memories", "emotional", "melancholy", "dark", "loneliness", "lonely", "sadness", "regret", "depression", "breakdown"}


def smart_music_score(track: dict | None, mood: str) -> float:
    if not track:
        return 0.30
    tag = engine.normalize(track.get("mood"))
    title = engine.normalize(f"{track.get('title', '')} {track.get('performer', '')}")
    if tag == mood:
        return 1.0
    if tag in MUSIC_COMPAT.get(mood, set()):
        return 0.94
    # If metadata is imperfect, title/artist text can still provide a useful signal.
    hits = sum(1 for word in GENERAL_SAD if word in title)
    if hits:
        return min(0.90, 0.78 + hits * 0.06)
    # A correctly selected melancholy library track is preferable to rejecting
    # Preview solely because an old tag cannot map to the new mood taxonomy.
    if tag in GENERAL_SAD:
        return 0.82
    return 0.72


def smart_choose_music(tracks: list[dict], mood: str, recent_ids: list[str], preview_ids: list[str] | None = None):
    if not tracks:
        return None
    blocked = set(recent_ids[-8:]) | set((preview_ids or [])[-20:])
    fresh = [t for t in tracks if t.get("file_id") not in blocked]
    if not fresh:
        fresh = [t for t in tracks if t.get("file_id") not in set(recent_ids[-8:])] or tracks[:]
    ranked = sorted(fresh, key=lambda t: smart_music_score(t, mood), reverse=True)
    # Small controlled randomization among the strongest tracks prevents one
    # song from dominating while preserving relevance.
    top = ranked[:min(10, len(ranked))]
    return random.choice(top)


# bot.py imported these symbols directly, so patch both the module references
# and the underlying engine used by quality_score.
bot.choose_music = smart_choose_music
engine.music_score = smart_music_score


def smart_quality_score(mood: str, caption: str, track: dict | None, photo: dict | None) -> dict:
    t = engine.caption_score(caption, mood)
    m = smart_music_score(track, mood)
    i = engine.image_score(photo, mood)
    c = max(0, min(1, min(1, .55 + engine._contains(engine.normalize(caption), engine.MOOD_ALIASES[mood]) * .10) * .32 + m * .36 + i * .32))
    overall = round((t * .30 + i * .22 + m * .30 + c * .18) * 100)
    return {"text": round(t * 100), "image": round(i * 100), "music": round(m * 100), "coherence": round(c * 100), "overall": max(0, min(100, overall))}


bot.quality_score = smart_quality_score
engine.quality_score = smart_quality_score


async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bot.is_admin(update):
        return

    target = update.callback_query.message if getattr(update, "callback_query", None) else update.message
    package = bot.build_package(True)

    if not package:
        await target.reply_text("❌ این دور Preview محتوای قابل‌قبول پیدا نکرد؛ دوباره امتحان کن.")
        return

    sc = package["score"]
    if sc["image"] < 68 or sc["music"] < 68 or sc["overall"] < 75:
        await target.reply_text(
            f"⚠️ بهترین گزینه این دور کیفیت کافی نداشت.\n"
            f"🖼 عکس: {sc['image']} | 🎧 آهنگ: {sc['music']} | ⭐ کلی: {sc['overall']}\n"
            "دوباره /preview بزن."
        )
        return

    text = (
        f"🌗 حس این پست: {bot.MOODS[package['mood']]['fa']} {bot.MOODS[package['mood']]['emoji']}\n"
        f"⭐ کیفیت: {sc['overall']}/100\n"
        f"📝 متن: {sc['text']} | 🖼 عکس: {sc['image']} | 🎧 آهنگ: {sc['music']} | 🔗 هماهنگی: {sc['coherence']}"
    )
    caption = f"{package['caption']}\n\n{bot.SIGNATURE}\n\n{text}"
    photo = package.get("photo")

    try:
        if photo:
            r = requests.get(photo["url"], timeout=20)
            r.raise_for_status()
            bio = io.BytesIO(r.content)
            bio.name = "preview.jpg"
            await target.reply_photo(photo=bio, caption=caption)
        else:
            await target.reply_text(caption)

        track = package.get("track")
        if track:
            await target.reply_audio(
                audio=track["file_id"],
                caption=bot._audio_caption(track),
                title=track.get("title"),
                performer=track.get("performer"),
            )
    except Exception:
        bot.log.exception("Preview send failed")
        return

    state = bot.load_state()
    mood = package["mood"]
    state["preview_moods"] = (state.get("preview_moods", []) + [mood])[-12:]
    if package.get("track"):
        state["preview_track_ids"] = (state.get("preview_track_ids", []) + [package["track"]["file_id"]])[-25:]
    h = hashlib.sha256(bot.normalize(package["caption"]).encode()).hexdigest()
    state["preview_caption_hashes"] = (state.get("preview_caption_hashes", []) + [h])[-25:]
    bot._advance_mood(state, mood)
    bot.save_state(state)


bot.preview = preview

if __name__ == "__main__":
    bot.main()
