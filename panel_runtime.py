"""SilentRuins unified panel runtime.
Runs the real panel callback runtime and keeps Music Intelligence v7 enabled.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import zipfile
import requests

import bot
import music_intelligence

# Keep the production soundtrack intelligence enabled.
music_intelligence.apply(bot)
bot.MAX_ATTEMPTS = max(getattr(bot, "MAX_ATTEMPTS", 8), 24)


async def preview(update, context):
    """Admin Preview: search hard, show useful diagnostics, never weaken Auto Post."""
    if not bot.is_admin(update):
        return

    target = update.callback_query.message if getattr(update, "callback_query", None) else update.message
    package = bot.build_package(True)

    if not package:
        await target.reply_text("❌ Preview نتوانست هیچ پکیج قابل‌بررسی بسازد.")
        return

    sc = package["score"]
    # Preview is intentionally softer than Auto Post. Auto Post still uses
    # QUALITY_THRESHOLD=82; Preview only requires usable image/music and a
    # reasonable overall score so the admin can inspect the result.
    if sc["image"] < 68 or sc["music"] < 68 or sc["overall"] < 75:
        await target.reply_text(
            "⚠️ بهترین گزینه این دور هنوز ضعیف بود.\n"
            f"🌗 Mood: {bot.MOODS[package['mood']]['fa']}\n"
            f"📝 متن: {sc['text']} | 🖼 عکس: {sc['image']} | 🎧 آهنگ: {sc['music']} | 🔗 هماهنگی: {sc['coherence']}\n"
            f"⭐ کلی: {sc['overall']}/100\n"
            "این فقط Preview است و پست خودکار همچنان استاندارد تولید را حفظ می‌کند."
        )
        return

    detail = (
        f"🌗 حس این پست: {bot.MOODS[package['mood']]['fa']} {bot.MOODS[package['mood']]['emoji']}\n"
        f"⭐ کیفیت: {sc['overall']}/100\n"
        f"📝 متن: {sc['text']} | 🖼 عکس: {sc['image']} | 🎧 آهنگ: {sc['music']} | 🔗 هماهنگی: {sc['coherence']}"
    )
    caption = f"{package['caption']}\n\n{bot.SIGNATURE}\n\n{detail}"
    photo = package.get("photo")

    try:
        if photo:
            response = requests.get(photo["url"], timeout=20)
            response.raise_for_status()
            bio = io.BytesIO(response.content)
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
    except Exception as exc:
        bot.log.exception("Panel Preview send failed")
        await target.reply_text(f"❌ ارسال Preview شکست خورد: {exc}")
        return

    # Preview history is committed only after successful delivery.
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


async def callback(update, context):
    q = update.callback_query
    if not q or not bot.is_admin(update):
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
        "preview_post": "preview",
        "preview_now": "preview",
        "post_now": "post",
        "publish": "post",
        "stop": "pause",
        "start": "resume",
        "report": "stats",
        "statistics": "stats",
        "music": "songs",
        "library": "songs",
        "times": "schedule",
        "backup_now": "backup",
    }
    action = aliases.get(action, action)

    try:
        if action == "preview":
            await bot.preview(update, context)
        elif action == "post":
            await bot.post_once(context, True)
            await target.reply_text("✅ دستور Post اجرا شد.")
        elif action == "pause":
            state = bot.load_state(); state["paused"] = True; bot.save_state(state)
            await target.reply_text("⏸ زمان‌بندی متوقف شد.")
        elif action == "resume":
            state = bot.load_state(); state["paused"] = False; bot.save_state(state)
            await target.reply_text("▶️ زمان‌بندی فعال شد.")
        elif action == "stats":
            x = bot.DB.summary()
            await target.reply_text(
                "📊 SilentRuins\n"
                f"پست موفق: {x['posts']}\n"
                f"خطا: {x['failed']}\n"
                f"۲۴ ساعت اخیر: {x['today']}\n"
                f"میانگین کیفیت: {x['avg_quality']}/100\n"
                f"آهنگ‌ها: {x['tracks']}"
            )
        elif action == "songs":
            tracks = bot.load_library()["tracks"]
            if not tracks:
                await target.reply_text("🎵 کتابخانه خالی است.")
            else:
                lines = [f"🎵 Music Library: {len(tracks)} آهنگ"]
                for i, track in enumerate(tracks[-50:], 1):
                    mood = bot.MOODS.get(track.get("mood"), {}).get("fa", track.get("mood", "?"))
                    lines.append(f"{i}. {track.get('performer', '?')} — {track.get('title', '?')} [{mood}]")
                await target.reply_text("\n".join(lines))
        elif action == "schedule":
            state = bot.load_state(); status = "⏸ متوقف" if state.get("paused") else "▶️ فعال"
            await target.reply_text(
                f"🕐 Schedule: {', '.join(bot.POST_TIMES)}\n"
                f"🌍 {bot.TZ_NAME}\n{status}\nThreshold: {bot.QUALITY_THRESHOLD}"
            )
        elif action == "backup":
            stamp = dt.datetime.now(bot.TZ).strftime("%Y%m%d_%H%M%S")
            path = bot.BACKUP_DIR / f"silentruins_{stamp}.zip"
            bot.save_library(bot.load_library()); bot.save_state(bot.load_state())
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for p in (bot.LIBRARY_FILE, bot.STATE_FILE, bot.DB_FILE):
                    if p.exists(): z.write(p, p.name)
            with path.open("rb") as f:
                await target.reply_document(f, filename=path.name, caption="💾 SilentRuins backup")
        else:
            await target.reply_text(f"⚠️ دکمه ناشناخته است: {data}")
    except Exception as exc:
        bot.log.exception("Panel callback failed: %s", data)
        await target.reply_text(f"❌ اجرای دکمه {data} با خطا مواجه شد: {exc}")


bot.callback = callback

if __name__ == "__main__":
    bot.main()
