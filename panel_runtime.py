"""SilentRuins unified panel runtime.
Runs the real panel callback runtime and keeps Music Intelligence enabled.
"""
from __future__ import annotations

import datetime as dt
import zipfile

import bot
import music_intelligence

# Preserve the smarter soundtrack selection used by the working Preview runtime.
music_intelligence.apply(bot)
bot.MAX_ATTEMPTS = max(getattr(bot, "MAX_ATTEMPTS", 8), 24)


async def callback(update, context):
    q = update.callback_query
    if not q or not bot.is_admin(update):
        return

    data = (q.data or "").strip().lower()
    await q.answer()
    target = q.message

    # Accept both the current callback IDs and common prefixed/legacy IDs.
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
            state = bot.load_state()
            state["paused"] = True
            bot.save_state(state)
            await target.reply_text("⏸ زمان‌بندی متوقف شد.")

        elif action == "resume":
            state = bot.load_state()
            state["paused"] = False
            bot.save_state(state)
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
                    lines.append(
                        f"{i}. {track.get('performer', '?')} — {track.get('title', '?')} [{mood}]"
                    )
                await target.reply_text("\n".join(lines))

        elif action == "schedule":
            state = bot.load_state()
            status = "⏸ متوقف" if state.get("paused") else "▶️ فعال"
            await target.reply_text(
                f"🕐 Schedule: {', '.join(bot.POST_TIMES)}\n"
                f"🌍 {bot.TZ_NAME}\n{status}\n"
                f"Threshold: {bot.QUALITY_THRESHOLD}"
            )

        elif action == "backup":
            stamp = dt.datetime.now(bot.TZ).strftime("%Y%m%d_%H%M%S")
            path = bot.BACKUP_DIR / f"silentruins_{stamp}.zip"
            bot.save_library(bot.load_library())
            bot.save_state(bot.load_state())
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for p in (bot.LIBRARY_FILE, bot.STATE_FILE, bot.DB_FILE):
                    if p.exists():
                        z.write(p, p.name)
            with path.open("rb") as f:
                await target.reply_document(
                    f, filename=path.name, caption="💾 SilentRuins backup"
                )

        else:
            await target.reply_text(f"⚠️ دکمه ناشناخته است: {data}")

    except Exception as exc:
        bot.log.exception("Panel callback failed: %s", data)
        await target.reply_text(f"❌ اجرای دکمه {data} با خطا مواجه شد: {exc}")


bot.callback = callback

if __name__ == "__main__":
    bot.main()
