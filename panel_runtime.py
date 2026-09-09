"""SilentRuins Panel Runtime v1.
Fixes Telegram inline-keyboard callbacks without changing production bot logic.
"""
from __future__ import annotations
import datetime as dt
import io
import zipfile
import bot

async def callback(update, context):
    q = update.callback_query
    if not q or not bot.is_admin(update):
        return
    await q.answer()
    target = q.message
    try:
        if q.data == "preview":
            await bot.preview(update, context)
        elif q.data == "post":
            await bot.post_once(context, True)
            await target.reply_text("✅ دستور Post اجرا شد.")
        elif q.data == "pause":
            s = bot.load_state(); s["paused"] = True; bot.save_state(s)
            await target.reply_text("⏸ زمان‌بندی متوقف شد.")
        elif q.data == "resume":
            s = bot.load_state(); s["paused"] = False; bot.save_state(s)
            await target.reply_text("▶️ زمان‌بندی فعال شد.")
        elif q.data == "stats":
            x = bot.DB.summary()
            await target.reply_text(
                f"📊 SilentRuins\nپست موفق: {x['posts']}\nخطا: {x['failed']}\n"
                f"۲۴ ساعت اخیر: {x['today']}\nمیانگین کیفیت: {x['avg_quality']}/100\n"
                f"آهنگ‌ها: {x['tracks']}"
            )
        elif q.data == "songs":
            tracks = bot.load_library()["tracks"]
            if not tracks:
                await target.reply_text("🎵 کتابخانه خالی است.")
            else:
                lines = [f"🎵 Music Library: {len(tracks)} آهنگ"]
                for i, t in enumerate(tracks[-50:]):
                    mood = bot.MOODS.get(t.get("mood"), {}).get("fa", t.get("mood"))
                    lines.append(f"{i+1}. {t.get('performer','?')} — {t.get('title','?')} [{mood}]")
                await target.reply_text("\n".join(lines))
        elif q.data == "schedule":
            s = bot.load_state(); status = "⏸ متوقف" if s.get("paused") else "▶️ فعال"
            await target.reply_text(
                f"🕐 Schedule: {', '.join(bot.POST_TIMES)}\n🌍 {bot.TZ_NAME}\n"
                f"{status}\nThreshold: {bot.QUALITY_THRESHOLD}"
            )
        elif q.data == "backup":
            stamp = dt.datetime.now(bot.TZ).strftime("%Y%m%d_%H%M%S")
            path = bot.BACKUP_DIR / f"silentruins_{stamp}.zip"
            bot.save_library(bot.load_library()); bot.save_state(bot.load_state())
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for p in (bot.LIBRARY_FILE, bot.STATE_FILE, bot.DB_FILE):
                    if p.exists(): z.write(p, p.name)
            with path.open("rb") as f:
                await target.reply_document(f, filename=path.name, caption="💾 SilentRuins backup")
    except Exception:
        bot.log.exception("Panel callback failed: %s", q.data)
        await target.reply_text(f"❌ اجرای دکمه {q.data} با خطا مواجه شد.")

bot.callback = callback

if __name__ == "__main__":
    bot.main()
