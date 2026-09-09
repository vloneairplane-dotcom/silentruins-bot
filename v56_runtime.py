"""SilentRuins v5.6 runtime: visual intelligence, mood balancing, and strict editorial gates."""
from __future__ import annotations
import hashlib
import io
import random
from datetime import datetime


def main():
    import content_engine as e
    import bot

    # Preserve original engine functions before installing v5.6 wrappers.
    original_image_score = e.image_score
    preview_memory = []

    MOOD_WORDS = {
        "rain": "rain rainy storm بارون باران",
        "night": "night midnight dark nocturnal شب نیمه شب",
        "lonely": "lonely loneliness alone solitude isolation تنهایی",
        "love": "love romantic romance heartbreak breakup betrayal missing loss دلتنگی شکست",
        "ruins": "memory memories nostalgia past broken empty emptiness loss خاطره ویرونه ویرانه",
        "tired": "tired exhausted burnout breakdown regret خستگی درد",
    }
    PHRASES = {
        "the night we met": {"ruins": 1, "love": .92, "night": .9, "lonely": .86},
        "glimpse of us": {"love": 1, "ruins": .9, "lonely": .86},
        "another love": {"love": 1, "lonely": .9, "night": .8, "ruins": .76},
        "lovely": {"lonely": 1, "night": .88, "tired": .72},
        "someone you loved": {"love": 1, "lonely": .94, "ruins": .84},
        "what was i made for": {"tired": .92, "lonely": .9, "ruins": .86, "night": .84},
        "i walk this earth all by myself": {"lonely": 1, "night": .88, "ruins": .8},
        "love in the dark": {"love": 1, "night": .96, "lonely": .9, "ruins": .78},
        "drivers license": {"love": .98, "ruins": .86, "lonely": .84, "night": .74},
        "i miss you": {"love": .9, "lonely": .94, "ruins": .84, "night": .78},
        "fix you": {"tired": .84, "lonely": .82, "love": .74, "rain": .72},
        "dark paradise": {"love": .9, "night": 1, "lonely": .86, "ruins": .74},
        "atlantis": {"love": .88, "ruins": .94, "lonely": .86, "night": .82},
    }
    SCENES = {
        "rain": {"rain": 1, "rainy": 1, "window": .95, "wet": .9, "reflection": .8, "umbrella": .78, "storm": .72},
        "night": {"night": 1, "midnight": 1, "moon": .92, "dark": .82, "street": .78, "city": .7, "silhouette": .72, "neon": .65},
        "lonely": {"alone": 1, "lonely": 1, "silhouette": .9, "empty": .82, "bench": .9, "room": .7, "window": .68, "distance": .82, "single": .88},
        "love": {"rose": 1, "withered": .95, "photograph": .95, "letter": .9, "goodbye": .9, "heartbreak": .88, "memory": .72, "distance": .72},
        "tired": {"tired": 1, "exhausted": 1, "head down": 1, "candle": .82, "hood": .72, "smoke": .55, "sitting": .7, "alone": .62},
        "ruins": {"ruins": 1, "ruin": 1, "abandoned": 1, "decay": .95, "broken": .9, "derelict": .95, "old building": .9, "empty building": .92, "crumbling": .95, "forgotten": .72},
    }
    BAD_VISUAL = {
        "people", "group", "crowd", "party", "wedding", "food", "restaurant", "car", "motorcycle",
        "product", "office", "business", "meeting", "daylight", "beach", "summer", "smiling", "happy",
        "sports", "concert", "colorful", "cartoon", "illustration", "logo", "text", "sign",
    }

    def norm(x):
        return e.normalize(str(x or "")).replace("ي", "ی").replace("ك", "ک").replace("’", "'").lower().strip()

    def profile(t):
        old = t.get("mood_profile")
        if isinstance(old, dict) and all(m in old for m in e.MOODS):
            return old
        tag = norm(t.get("mood")); text = norm(f"{t.get('title','')} {t.get('performer','')} {tag}")
        p = {m: .42 for m in e.MOODS}
        for m, words in MOOD_WORDS.items():
            for w in words.split():
                if w in tag:
                    p[m] = max(p[m], 1.0 if w in ("night", "lonely", "love", "memory", "memories", "tired", "rain") else .88)
        for phrase, vals in PHRASES.items():
            if phrase in text:
                for m, v in vals.items(): p[m] = max(p[m], v)
        for m in e.MOODS:
            if tag == m or tag == norm(e.MOODS[m]["fa"]): p[m] = 1.0
            for a in e.MOOD_ALIASES.get(m, []):
                a = norm(a)
                if len(a) >= 4 and a in text: p[m] = max(p[m], .82)
        t["mood_profile"] = {m: round(max(0, min(1, v)), 3) for m, v in p.items()}
        return t["mood_profile"]

    def profile_library(lib):
        changed = False
        for t in lib.get("tracks", []):
            old = t.get("mood_profile"); profile(t)
            if old != t.get("mood_profile"): changed = True
        if changed: bot.save_library(lib)
        return lib

    def music_score(t, mood): return float(profile(t).get(mood, .42)) if t else 0.0

    def choose_mood(state, hour=None):
        h = datetime.now().hour if hour is None else hour
        if h >= 22 or h < 5: pool = ["night", "lonely", "love", "ruins"]
        elif h >= 17: pool = ["love", "lonely", "night", "rain", "ruins"]
        else: pool = ["tired", "love", "rain", "lonely", "ruins"]
        recent = list(state.get("recent_moods", []))[-3:]
        previews = list(state.get("preview_moods", []))[-6:]
        process = preview_memory[-4:]
        counts = {m: sum(1 for x in recent + previews + process if x == m) for m in pool}
        weights = []
        for m in pool:
            w = 1.0 / (1.0 + 1.35 * counts[m])
            if m in recent: w *= .28
            if m in previews: w *= .48
            if m in process: w *= .58
            weights.append(w)
        return random.choices(pool, weights=weights, k=1)[0]

    def visual_score(photo, mood):
        if not photo: return 0.0
        text = norm(f"{photo.get('query', '')} {photo.get('alt', '')}")
        terms = SCENES.get(mood, {})
        positive = sum(weight for term, weight in terms.items() if term in text)
        possible = sum(terms.values()) or 1.0
        scene = min(1.0, positive / max(1.0, min(2.2, possible)))
        bad = sum(1 for term in BAD_VISUAL if term in text)
        luminance = float(photo.get("luminance", 55))
        dark = 1.0 if luminance <= 48 else max(0.0, 1.0 - (luminance - 48) / 48)
        portrait = float(photo.get("height", 0)) / max(1.0, float(photo.get("width", 1)))
        portrait_bonus = min(1.0, max(0.0, (portrait - 1.0) / .55))
        alt_bonus = .08 if len(norm(photo.get("alt", "")).split()) >= 4 else 0.0
        score = .48 * scene + .20 * dark + .18 * portrait_bonus + .14 * min(1.0, alt_bonus * 8)
        score -= min(.28, bad * .06)
        return max(0.0, min(1.0, score))

    def image_score(photo, mood):
        # IMPORTANT: call the original engine function, not e.image_score,
        # because e.image_score is replaced by this wrapper below.
        base = original_image_score(photo, mood) if photo else 0.0
        scene = visual_score(photo, mood)
        return max(0.0, min(1.0, .35 * base + .65 * scene))

    def quality(mood, caption, track, photo):
        ts = e.caption_score(caption, mood); ms = music_score(track, mood); im = image_score(photo, mood)
        co = max(0, min(1, .10 * ts + .52 * ms + .38 * im))
        overall = ts * .24 + im * .30 + ms * .34 + co * .12
        return {"text": round(ts * 100), "image": round(im * 100), "music": round(ms * 100), "coherence": round(co * 100), "overall": round(overall * 100)}

    e.choose_mood = choose_mood; e.music_score = music_score; e.image_score = image_score; e.quality_score = quality

    def pick_photo(photos, mood):
        if not photos: return None
        ranked = sorted(photos, key=lambda p: image_score(p, mood), reverse=True)
        strong = [p for p in ranked if image_score(p, mood) >= .72]
        pool = strong[:6] if strong else ranked[:3]
        return random.choice(pool) if pool else None

    def pick_music(tracks, mood, state, preview):
        recent = set(state.get("recent_track_ids", [])[-8:]); seen = set(state.get("preview_track_ids", [])[-25:]) if preview else set()
        fresh = [t for t in tracks if t.get("file_id") not in recent and t.get("file_id") not in seen]
        strong = sorted([t for t in fresh if music_score(t, mood) >= .72], key=lambda t: music_score(t, mood), reverse=True)
        if strong: return random.choice(strong[:12])
        reusable = sorted([t for t in tracks if t.get("file_id") not in recent and music_score(t, mood) >= .72], key=lambda t: music_score(t, mood), reverse=True)
        if reusable: return random.choice(reusable[:12])
        ranked = sorted(tracks, key=lambda t: music_score(t, mood), reverse=True)
        return ranked[0] if ranked else None

    def build(preview=False):
        state = bot.load_state(); lib = profile_library(bot.load_library()); gate = max(82, bot.QUALITY_THRESHOLD)
        blocked = list(state.get("recent_caption_hashes", []))[-25:] + list(state.get("preview_caption_hashes", []))[-25:]
        best = None; best_key = (-1, -1, -1)
        for _ in range(max(30, bot.MAX_ATTEMPTS)):
            mood = choose_mood(state); caption = e.choose_caption(mood, blocked); track = pick_music(lib["tracks"], mood, state, preview)
            photos = bot._photo_candidates(mood, state) if bot.SEND_PHOTOS else []; photo = pick_photo(photos, mood); sc = quality(mood, caption, track, photo)
            pack = {"mood": mood, "caption": caption, "track": track, "photo": photo, "score": sc}; key = (sc["overall"], sc["image"], sc["music"])
            if key > best_key: best, best_key = pack, key
            if sc["overall"] >= gate and sc["image"] >= 76 and sc["music"] >= 72 and sc["coherence"] >= 78: break
        if not best: return None
        sc = best["score"]
        if sc["image"] < 72 or sc["music"] < 72: return None
        if not preview and not (sc["overall"] >= gate and sc["image"] >= 76 and sc["music"] >= 72 and sc["coherence"] >= 78): return None
        if preview:
            preview_memory.append(best["mood"]); del preview_memory[:-6:]
            s = bot.load_state(); s["preview_moods"] = (s.get("preview_moods", []) + [best["mood"]])[-12:]
            if best.get("track"): s["preview_track_ids"] = (s.get("preview_track_ids", []) + [best["track"]["file_id"]])[-25:]
            h = hashlib.sha256(norm(best["caption"]).encode()).hexdigest(); s["preview_caption_hashes"] = (s.get("preview_caption_hashes", []) + [h])[-25:]; bot.save_state(s)
        return best

    bot.build_package = build

    async def preview(update, context):
        if not bot.is_admin(update): return
        p = build(True); target = update.callback_query.message if getattr(update, "callback_query", None) else update.message
        if not p:
            await target.reply_text("❌ این دور Preview به استاندارد لازم نرسید؛ عکس یا آهنگ ضعیف عمداً نمایش داده نمی‌شود."); return
        s = p["score"]; cap = f"{p['caption']}\n\n{e.SIGNATURE}\n\n🌗 حس این پست: {e.MOODS[p['mood']]['fa']} {e.MOODS[p['mood']]['emoji']}\n⭐ کیفیت: {s['overall']}/100\n📝 متن: {s['text']} | 🖼 عکس: {s['image']} | 🎧 آهنگ: {s['music']} | 🔗 هماهنگی: {s['coherence']}"
        if p.get("photo"):
            try:
                data = bot.requests.get(p["photo"]["url"], timeout=20).content; b = io.BytesIO(data); b.name = "preview.jpg"; await target.reply_photo(photo=b, caption=cap)
            except Exception: await target.reply_text(cap)
        else: await target.reply_text(cap)
        if p.get("track"):
            t = p["track"]; await target.reply_audio(audio=t["file_id"], caption=bot._audio_caption(t), title=t.get("title"), performer=t.get("performer"))

    bot.preview = preview

    async def callback(update, context):
        q = update.callback_query; await q.answer()
        if not bot.is_admin(update): return
        if q.data == "preview": await preview(update, context)
        elif q.data == "post": await bot.post_once(context, True); await q.message.reply_text("✅ ارسال شد")
        elif q.data == "pause": s=bot.load_state(); s["paused"]=True; bot.save_state(s); await q.message.reply_text("⏸ متوقف شد")
        elif q.data == "resume": s=bot.load_state(); s["paused"]=False; bot.save_state(s); await q.message.reply_text("▶️ ادامه پیدا کرد")
        elif q.data == "stats": await bot.stats(update, context)
        elif q.data == "songs": await q.message.reply_text("🎵 Music Library: "+str(len(bot.load_library()["tracks"]))+" آهنگ")
        elif q.data == "schedule": await bot.schedule_cmd(update, context)
        elif q.data == "backup": await q.message.reply_text("💾 برای Backup از /backup استفاده کن.")

    bot.callback = callback
    bot.main()


if __name__ == "__main__": main()
