"""SilentRuins v5.4 runtime.
Robust legacy/Persian music labels, semantic soundtrack matching, and hard publish gate.
"""
from __future__ import annotations
import io, random
from datetime import datetime


def main():
    import content_engine as e
    import bot

    preview_memory = []
    # Existing uploads may use English, Persian, or descriptive labels.
    TAG_TO_MOODS = {
        "rain": {"rain", "night", "lonely"}, "rainy": {"rain", "night", "lonely"}, "storm": {"rain", "night", "ruins"},
        "night": {"night", "lonely"}, "midnight": {"night", "lonely", "ruins"}, "dark": {"night", "ruins", "lonely", "tired"},
        "lonely": {"lonely", "night"}, "loneliness": {"lonely", "night", "ruins"}, "alone": {"lonely", "night"},
        "solitude": {"lonely", "night", "ruins"}, "isolation": {"lonely", "night", "ruins"}, "distance": {"love", "lonely", "night"},
        "love": {"love"}, "romantic": {"love"}, "romance": {"love"}, "heartbreak": {"love", "lonely", "night", "ruins"},
        "breakup": {"love", "lonely", "night", "ruins"}, "break up": {"love", "lonely", "night", "ruins"},
        "betrayal": {"love", "lonely", "tired", "ruins"}, "unrequited love": {"love", "lonely"}, "regret": {"love", "tired", "lonely", "night"},
        "missing": {"love", "lonely", "night", "rain", "ruins"}, "loss": {"love", "lonely", "night", "ruins"},
        "memory": {"ruins", "love", "lonely", "night", "rain"}, "memories": {"ruins", "love", "lonely", "night", "rain"},
        "nostalgia": {"ruins", "love", "night", "rain"}, "past": {"ruins", "love", "lonely", "night"},
        "broken": {"ruins", "love", "lonely", "night"}, "empty": {"ruins", "lonely", "night", "tired"}, "emptiness": {"ruins", "lonely", "night", "tired"},
        "sad": {"rain", "tired", "lonely", "night", "ruins", "love"}, "sadness": {"rain", "tired", "lonely", "night", "ruins"},
        "emotional": {"night", "lonely", "love", "tired", "rain", "ruins"}, "melancholy": {"rain", "night", "lonely", "ruins", "tired", "love"},
        "tired": {"tired", "lonely", "night", "ruins"}, "exhausted": {"tired", "lonely", "night"}, "burnout": {"tired", "lonely", "night"},
        "breakdown": {"tired", "lonely", "night"}, "depression": {"tired", "lonely", "ruins", "night"},
        "calm": {"rain", "night"}, "piano": {"night", "rain", "lonely", "tired"}, "ambient": {"night", "rain", "ruins", "lonely"},
        "بارون": {"rain", "night", "lonely"}, "باران": {"rain", "night", "lonely"}, "شب": {"night", "lonely"}, "نیمه شب": {"night", "lonely", "ruins"},
        "تنهایی": {"lonely", "night", "ruins"}, "دلتنگی": {"love", "lonely", "night", "ruins"}, "خستگی": {"tired", "lonely", "night", "ruins"},
        "ویرونه": {"ruins", "lonely", "night", "love"}, "ویرانه": {"ruins", "lonely", "night", "love"}, "غم": {"rain", "tired", "lonely", "night", "ruins"},
        "شکست": {"love", "ruins", "lonely"}, "خاطره": {"ruins", "love", "lonely", "night"}, "درد": {"love", "lonely", "tired", "ruins"},
    }

    def norm(x):
        return e.normalize(str(x or "")).replace("ي", "ی").replace("ك", "ک")

    def labels_for(raw):
        text = norm(raw)
        labels = set()
        for label, moods in TAG_TO_MOODS.items():
            if text == label or label in text:
                labels.update(moods)
        return labels

    def music_score(track, mood):
        if not track:
            return 0.0
        tag = norm(track.get("mood"))
        title_artist = norm(f"{track.get('title','')} {track.get('performer','')}")
        # Explicit tag gets highest priority.
        if tag == mood:
            return 1.00
        tag_moods = labels_for(tag)
        if mood in tag_moods:
            return 0.96
        # Search title/artist for semantic mood labels, including Persian labels.
        title_moods = labels_for(title_artist)
        if mood in title_moods:
            return 0.90
        # A direct editorial alias is useful as a last signal.
        aliases = [norm(a) for a in e.MOOD_ALIASES.get(mood, [])]
        hits = sum(1 for a in aliases if a and a in title_artist)
        if hits >= 2:
            return 0.86
        if hits == 1:
            return 0.78
        return 0.52

    def choose_mood(state, hour=None):
        hour = datetime.now().hour if hour is None else hour
        pool = (["night", "lonely", "love", "ruins"] if hour >= 22 or hour < 5 else
                ["love", "lonely", "night", "rain", "ruins"] if hour >= 17 else
                ["tired", "love", "rain", "lonely"])
        recent = list(state.get("recent_moods", []))[-3:]
        old = list(state.get("preview_moods", []))[-6:]
        blocked = set(recent + old + preview_memory[-4:])
        choices = [m for m in pool if m not in blocked] or [m for m in pool if m not in set(recent[-1:])] or pool
        counts = {m: recent.count(m) + old.count(m) + preview_memory.count(m) for m in choices}
        low = min(counts.values())
        return random.choice([m for m in choices if counts[m] == low])

    def quality(mood, caption, track, photo):
        t = e.caption_score(caption, mood)
        m = music_score(track, mood)
        i = e.image_score(photo, mood)
        c = max(0, min(1, .18*t + .50*m + .32*i))
        overall = round((t*.26 + i*.27 + m*.35 + c*.12)*100)
        return {"text": round(t*100), "image": round(i*100), "music": round(m*100), "coherence": round(c*100), "overall": max(0,min(100,overall))}

    e.choose_mood = choose_mood
    e.music_score = music_score
    e.quality_score = quality

    def pick_music(tracks, mood, state, preview=False):
        if not tracks:
            return None
        recent = set(state.get("recent_track_ids", [])[-8:])
        preview_ids = set(state.get("preview_track_ids", [])[-25:]) if preview else set()
        available = [t for t in tracks if t.get("file_id") not in recent and t.get("file_id") not in preview_ids]
        if not available:
            available = [t for t in tracks if t.get("file_id") not in recent] or tracks[:]
        ranked = sorted(available, key=lambda t: music_score(t, mood), reverse=True)
        strong = [t for t in ranked if music_score(t, mood) >= .72]
        return random.choice((strong[:8] if strong else ranked[:8]))

    def build(preview=False):
        state = bot.load_state(); lib = bot.load_library(); best = None
        gate = max(82, bot.QUALITY_THRESHOLD)
        for _ in range(max(18, bot.MAX_ATTEMPTS)):
            mood = choose_mood(state)
            caption = e.choose_caption(mood, state.get("recent_caption_hashes", []))
            track = pick_music(lib["tracks"], mood, state, preview)
            photos = bot._photo_candidates(mood, state) if bot.SEND_PHOTOS else []
            photo = bot._pick_photo(photos, mood) if photos else None
            score = quality(mood, caption, track, photo)
            pack = {"mood": mood, "caption": caption, "track": track, "photo": photo, "score": score}
            if best is None or score["overall"] > best["score"]["overall"]:
                best = pack
            if (score["overall"] >= gate and score["image"] >= 72 and
                score["music"] >= 72 and score["coherence"] >= 78):
                break
        if preview:
            if best:
                preview_memory.append(best["mood"]); del preview_memory[:-6]
                s = bot.load_state()
                s["preview_moods"] = (s.get("preview_moods", []) + [best["mood"]])[-12:]
                if best.get("track"):
                    s["preview_track_ids"] = (s.get("preview_track_ids", []) + [best["track"]["file_id"]])[-25:]
                bot.save_state(s)
            return best
        if not best:
            return None
        sc = best["score"]
        if not (sc["overall"] >= gate and sc["image"] >= 72 and sc["music"] >= 72 and sc["coherence"] >= 78):
            return None
        return best

    bot.build_package = build

    async def callback(update, context):
        q = update.callback_query
        await q.answer()
        if not bot.is_admin(update):
            return
        if q.data == "preview":
            p = bot.build_package(True)
            if not p:
                await q.message.reply_text("❌ نتونستم Preview بسازم."); return
            s = p["score"]
            text = (f"🌗 حس این پست: {e.MOODS[p['mood']]['fa']} {e.MOODS[p['mood']]['emoji']}\n"
                    f"⭐ کیفیت: {s['overall']}/100\n📝 متن: {s['text']} | 🖼 عکس: {s['image']} | 🎧 آهنگ: {s['music']} | 🔗 هماهنگی: {s['coherence']}")
            caption = f"{p['caption']}\n\n{e.SIGNATURE}\n\n{text}"
            if p.get("photo"):
                try:
                    data = bot.requests.get(p["photo"]["url"], timeout=20).content
                    bio = io.BytesIO(data); bio.name = "preview.jpg"
                    await q.message.reply_photo(photo=bio, caption=caption)
                except Exception:
                    await q.message.reply_text(caption)
            else:
                await q.message.reply_text(caption)
            if p.get("track"):
                t = p["track"]
                await q.message.reply_audio(audio=t["file_id"], caption=bot._audio_caption(t), title=t.get("title"), performer=t.get("performer"))
        elif q.data == "post":
            await bot.post_once(context, True); await q.message.reply_text("✅ ارسال شد")
        elif q.data == "pause":
            s=bot.load_state(); s["paused"]=True; bot.save_state(s); await q.message.reply_text("⏸ متوقف شد")
        elif q.data == "resume":
            s=bot.load_state(); s["paused"]=False; bot.save_state(s); await q.message.reply_text("▶️ ادامه پیدا کرد")
        elif q.data == "stats":
            x=bot.DB.summary(); await q.message.reply_text(f"📊 SilentRuins\nپست موفق: {x['posts']}\nخطا: {x['failed']}\n۲۴ ساعت اخیر: {x['today']}\nمیانگین کیفیت: {x['avg_quality']}/100\nآهنگ‌ها: {x['tracks']}")
        elif q.data == "songs":
            ts=bot.load_library()["tracks"]
            await q.message.reply_text("\n".join([f"🎵 Music Library: {len(ts)} آهنگ"] + [f"{i+1}. {t.get('performer','?')} — {t.get('title','?')}" for i,t in enumerate(ts[-50:])]))
        elif q.data == "schedule":
            s=bot.load_state(); await q.message.reply_text(f"🕐 Schedule: {', '.join(bot.POST_TIMES)}\n🌍 {bot.TZ_NAME}\n{'⏸ متوقف' if s.get('paused') else '▶️ فعال'}\nThreshold: {bot.QUALITY_THRESHOLD}")
        elif q.data == "backup":
            await q.message.reply_text("💾 برای Backup از /backup استفاده کن.")

    bot.callback = callback
    bot.main()


if __name__ == "__main__":
    main()
