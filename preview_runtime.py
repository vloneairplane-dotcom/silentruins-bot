"""SilentRuins Preview Runtime v6.1.
Keeps production bot.py untouched while making /preview more useful.
"""
from __future__ import annotations

import hashlib
import io
import requests

import bot
from telegram import Update
from telegram.ext import ContextTypes

# Preview can search harder without changing Auto Post's quality standard.
bot.MAX_ATTEMPTS = max(bot.MAX_ATTEMPTS, 24)


async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bot.is_admin(update):
        return

    target = update.callback_query.message if getattr(update, "callback_query", None) else update.message
    package = bot.build_package(True)

    if not package:
        await target.reply_text("❌ این دور Preview محتوای قابل‌قبول پیدا نکرد؛ دوباره امتحان کن.")
        return

    sc = package["score"]
    # Preview gate is intentionally softer. Auto Post remains at QUALITY_THRESHOLD.
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

    # Consume mood only after a successful Preview.
    state = bot.load_state()
    mood = package["mood"]
    state["preview_moods"] = (state.get("preview_moods", []) + [mood])[-12:]
    if package.get("track"):
        state["preview_track_ids"] = (state.get("preview_track_ids", []) + [package["track"]["file_id"]])[-25:]
    h = hashlib.sha256(bot.normalize(package["caption"]).encode()).hexdigest()
    state["preview_caption_hashes"] = (state.get("preview_caption_hashes", []) + [h])[-25:]
    bot._advance_mood(state, mood)
    bot.save_state(state)


# Patch the command and callback target before starting the normal bot runtime.
bot.preview = preview

if __name__ == "__main__":
    bot.main()
