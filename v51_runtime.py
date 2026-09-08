"""SilentRuins v5.2 editorial runtime."""
from __future__ import annotations
import io, random
from datetime import datetime


def main():
    import content_engine as e
    import bot

    def mood(state, hour=None):
        hour = datetime.now().hour if hour is None else hour
        if 22 <= hour or hour < 5:
            pool=["night","lonely","love","ruins"]
        elif 17 <= hour < 22:
            pool=["love","lonely","night","rain","ruins"]
        elif 12 <= hour < 17:
            pool=["tired","love","rain","lonely"]
        else:
            pool=["rain","tired","love","lonely"]
        recent=list(state.get("recent_moods",[]))[-3:]
        previews=list(state.get("preview_moods",[]))[-4:]
        blocked=set(recent+previews)
        choices=[m for m in pool if m not in blocked] or [m for m in pool if m not in recent[-1:]] or pool
        counts={m:recent.count(m)+previews.count(m) for m in choices}
        low=min(counts.values())
        return random.choice([m for m in choices if counts[m]==low])

    def image_score(photo, m):
        if not photo: return .18
        text=e.normalize(f"{photo.get('query','')} {photo.get('alt','')}")
        good=sum(1 for w in e.GOOD_VISUAL if e.normalize(w) in text)
        bad=sum(1 for w in e.BAD_VISUAL if e.normalize(w) in text)
        visual=sum(1 for w in e.MOODS[m]["visual"] if e.normalize(w) in text)
        s=.46+min(.24,visual*.055)+min(.12,good*.018)-min(.42,bad*.14)
        lum=photo.get("luminance")
        if isinstance(lum,(int,float)):
            if 28<=lum<=78: s+=.16
            elif 78<lum<=105: s+=.03
            elif lum<20: s-=.18
            elif lum>145: s-=.24
            elif lum>120: s-=.12
        w,h=photo.get("width"),photo.get("height")
        if isinstance(w,int) and isinstance(h,int):
            if h>=1200 and h>=w*1.15: s+=.06
            elif h<700: s-=.08
        if len(e.normalize(photo.get("alt","")))<10: s-=.06
        return max(0,min(1,s))

    # Music matching is intentionally semantic rather than dependent on one exact
    # library label. Existing uploads may use labels such as Heartbreak, Missing,
    # Sadness, Dark, Emotional, Memories, etc.
    MUSIC_TAG_GROUPS = {
        "heartbreak": {"love","lonely","night","rain"},
        "breakup": {"love","lonely","night"},
        "missing": {"love","lonely","night","rain","ruins"},
        "memories": {"love","lonely","night","rain","ruins"},
        "memory": {"love","lonely","night","rain","ruins"},
        "sadness": {"rain","tired","lonely","night","ruins"},
        "sad": {"rain","tired","lonely","night","ruins","love"},
        "emotional": {"night","lonely","love","tired","rain","ruins"},
        "melancholy": {"rain","night","lonely","ruins","tired","love"},
        "dark": {"night","ruins","lonely","tired"},
        "loneliness": {"lonely","night","ruins"},
        "lonely": {"lonely","night"},
        "night": {"night","lonely"},
        "rain": {"rain","night","lonely"},
        "regret": {"love","tired","lonely","night"},
        "distance": {"love","lonely","night"},
        "romantic": {"love"},
        "unrequited love": {"love","lonely"},
        "betrayal": {"love","lonely","tired"},
        "breakdown": {"tired","lonely","night"},
        "depression": {"tired","lonely","ruins","night"},
        "calm": {"rain","night"},
        "piano": {"night","rain","lonely","tired"},
        "ambient": {"night","rain","ruins","lonely"},
    }

    def music_score(track,m):
        if not track: return .15
        tagged=e.normalize(track.get("mood"))
        title=e.normalize(track.get("title"))
        performer=e.normalize(track.get("performer"))
        text=e.normalize(f"{title} {performer} {tagged}")

        # Exact mood labels are strongest.
        if tagged == m:
            return 1.0

        # Recognise common library labels even when they are not in the original
        # engine's map. This prevents generic 58-ish scores for clearly sad tracks.
        group_hits=[]
        for label, moods in MUSIC_TAG_GROUPS.items():
            if label in tagged or label in text:
                group_hits.append((label,moods))
        if group_hits:
            if any(m in moods for _,moods in group_hits):
                best=.88
                if any(label in tagged for label,_ in group_hits): best=.93
                return best
            # A clearly melancholic track can still be a reasonable night fallback,
            # but should not outrank an actual mood match.
            if m in {"night","lonely","ruins","rain","tired"}:
                return .72

        # Preserve the original engine's title/performer/tag matching as a fallback.
        old=e.music_score(track,m)
        direct=sum(1 for w in e.MOOD_ALIASES[m] if e.normalize(w) in text)
        return max(.60, old, min(.84,.56+direct*.08))

    def quality(m,caption,track,photo):
        t=e.caption_score(caption,m); ms=music_score(track,m); im=image_score(photo,m)
        c=max(0,min(1,.24*t+.42*ms+.34*im))
        overall=round((t*.30+im*.31+ms*.27+c*.12)*100)
        return {"text":round(t*100),"image":round(im*100),"music":round(ms*100),"coherence":round(c*100),"overall":max(0,min(100,overall))}

    e.choose_mood=mood; e.image_score=image_score; e.music_score=music_score; e.quality_score=quality

    def photos(m,state):
        recent=set(state.get("recent_images",[])[-14:]); out=[]
        for q in e.MOODS[m]["queries"]:
            for p in bot._pexels(q):
                src=p.get("src") or {}; url=src.get("portrait") or src.get("large2x") or src.get("large")
                if not url or url in recent: continue
                x={"url":url,"query":q,"alt":p.get("alt","") ,"luminance":bot._luminance(p.get("avg_color")),"width":p.get("width"),"height":p.get("height")}
                if image_score(x,m)>=.56: out.append(x)
            if len(out)>=24: break
        return out

    def pick(items,m):
        if not items:return None
        ranked=sorted(items,key=lambda x:image_score(x,m),reverse=True)
        return random.choice(ranked[:min(4,len(ranked))])

    def build(preview=False):
        state=bot.load_state(); lib=bot.load_library(); best=None
        for _ in range(max(12,bot.MAX_ATTEMPTS)):
            m=mood(state); c=e.choose_caption(m,state.get("recent_caption_hashes",[]))
            tr=e.choose_music(lib["tracks"],m,state.get("recent_track_ids",[]),state.get("preview_track_ids",[]) if preview else [])
            ph=pick(photos(m,state),m) if bot.SEND_PHOTOS else None
            sc=quality(m,c,tr,ph); pack={"mood":m,"caption":c,"track":tr,"photo":ph,"score":sc}
            if best is None or sc["overall"]>best["score"]["overall"]: best=pack
            if sc["overall"]>=max(82,bot.QUALITY_THRESHOLD) and sc["image"]>=72 and sc["music"]>=72: break
        if preview and best:
            s=bot.load_state(); s["preview_moods"]=(s.get("preview_moods",[])+[best["mood"]])[-12:]; bot.save_state(s)
        return best

    bot.build_package=build; bot._photo_candidates=photos; bot._pick_photo=pick

    async def callback(update,context):
        q=update.callback_query; await q.answer()
        if not bot.is_admin(update): return
        if q.data=="preview":
            p=bot.build_package(True)
            if not p: await q.message.reply_text("❌ نتونستم Preview بسازم."); return
            s=p["score"]; txt=f"🌗 حس این پست: {e.MOODS[p['mood']]['fa']} {e.MOODS[p['mood']]['emoji']}\n⭐ کیفیت: {s['overall']}/100\n📝 متن: {s['text']} | 🖼 عکس: {s['image']} | 🎧 آهنگ: {s['music']} | 🔗 هماهنگی: {s['coherence']}"
            cap=f"{p['caption']}\n\n{e.SIGNATURE}\n\n{txt}"
            if p.get("photo"):
                try:
                    data=bot.requests.get(p["photo"]["url"],timeout=20).content; b=io.BytesIO(data); b.name="preview.jpg"; await q.message.reply_photo(photo=b,caption=cap)
                except Exception: await q.message.reply_text(cap)
            else: await q.message.reply_text(cap)
            if p.get("track"):
                t=p["track"]; await q.message.reply_audio(audio=t["file_id"],caption=bot._audio_caption(t),title=t.get("title"),performer=t.get("performer"))
        elif q.data=="post": await bot.post_once(context,True); await q.message.reply_text("✅ ارسال شد")
        elif q.data=="pause": s=bot.load_state();s["paused"]=True;bot.save_state(s);await q.message.reply_text("⏸ متوقف شد")
        elif q.data=="resume": s=bot.load_state();s["paused"]=False;bot.save_state(s);await q.message.reply_text("▶️ ادامه پیدا کرد")
        elif q.data=="stats": x=bot.DB.summary();await q.message.reply_text(f"📊 SilentRuins\nپست موفق: {x['posts']}\nخطا: {x['failed']}\n۲۴ ساعت اخیر: {x['today']}\nمیانگین کیفیت: {x['avg_quality']}/100\nآهنگ‌ها: {x['tracks']}")
        elif q.data=="songs":
            ts=bot.load_library()["tracks"]; lines=[f"🎵 Music Library: {len(ts)} آهنگ"]+[f"{i+1}. {t.get('performer','?')} — {t.get('title','?')}" for i,t in enumerate(ts[-50:])]; await q.message.reply_text("\n".join(lines) or "🎵 کتابخانه خالی است.")
        elif q.data=="schedule": s=bot.load_state();await q.message.reply_text(f"🕐 Schedule: {', '.join(bot.POST_TIMES)}\n🌍 {bot.TZ_NAME}\n{'⏸ متوقف' if s.get('paused') else '▶️ فعال'}\nThreshold: {bot.QUALITY_THRESHOLD}")
        elif q.data=="backup": await q.message.reply_text("💾 برای Backup از /backup استفاده کن.")
    bot.callback=callback
    bot.main()

if __name__=="__main__": main()
