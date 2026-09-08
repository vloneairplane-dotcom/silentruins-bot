"""SilentRuins v5.4 runtime: strict editorial matching and quality-gated publishing."""
from __future__ import annotations
import io, random
from datetime import datetime


def main():
    import content_engine as e
    import bot
    preview_memory = []

    # Normalize the free-form mood labels stored in older music-library entries.
    # This keeps the existing uploaded Telegram file_ids; only matching logic changes.
    mood_aliases = {
        "rain": {"rain", "rainy", "storm", "stormy"},
        "night": {"night", "midnight", "dark", "nocturnal", "late night"},
        "lonely": {"lonely", "loneliness", "alone", "solitude", "isolation", "missing", "distance"},
        "love": {"love", "romantic", "romance", "heartbreak", "breakup", "break up", "betrayal", "unrequited love", "regret"},
        "tired": {"tired", "exhausted", "burnout", "breakdown", "depression", "heavy", "sadness"},
        "ruins": {"ruins", "ruin", "memories", "memory", "nostalgia", "past", "loss", "broken", "empty", "emptiness"},
    }
    music_groups = {
        "heartbreak":{"love","lonely","night","rain","ruins"},
        "breakup":{"love","lonely","night","ruins"},
        "missing":{"love","lonely","night","rain","ruins"},
        "memories":{"love","lonely","night","rain","ruins"},
        "memory":{"love","lonely","night","rain","ruins"},
        "loss":{"love","lonely","night","ruins"},
        "broken":{"love","lonely","night","ruins"},
        "empty":{"lonely","night","ruins","tired"},
        "emptiness":{"lonely","night","ruins","tired"},
        "nostalgia":{"ruins","love","rain","night"},
        "sadness":{"rain","tired","lonely","night","ruins"},
        "sad":{"rain","tired","lonely","night","ruins","love"},
        "emotional":{"night","lonely","love","tired","rain","ruins"},
        "melancholy":{"rain","night","lonely","ruins","tired","love"},
        "dark":{"night","ruins","lonely","tired"},
        "loneliness":{"lonely","night","ruins"},
        "lonely":{"lonely","night"},
        "night":{"night","lonely"},
        "rain":{"rain","night","lonely"},
        "regret":{"love","tired","lonely","night","ruins"},
        "distance":{"love","lonely","night"},
        "romantic":{"love"},
        "unrequited love":{"love","lonely"},
        "betrayal":{"love","lonely","tired","ruins"},
        "breakdown":{"tired","lonely","night"},
        "depression":{"tired","lonely","ruins","night"},
        "calm":{"rain","night"},
        "piano":{"night","rain","lonely","tired"},
        "ambient":{"night","rain","ruins","lonely"},
    }

    def normalize_labels(raw):
        text = e.normalize(str(raw or ""))
        labels = {text} if text else set()
        for label, aliases in mood_aliases.items():
            if text in aliases or any(a in text for a in aliases):
                labels.add(label)
        return labels

    def choose_mood(state, hour=None):
        hour=datetime.now().hour if hour is None else hour
        pool=(['night','lonely','love','ruins'] if hour>=22 or hour<5 else
              ['love','lonely','night','rain','ruins'] if hour<22 else
              ['tired','love','rain','lonely'] if hour<17 else ['rain','tired','love','lonely'])
        recent=list(state.get('recent_moods',[]))[-3:]
        old=list(state.get('preview_moods',[]))[-6:]
        blocked=set(recent+old+preview_memory[-4:])
        choices=[m for m in pool if m not in blocked] or [m for m in pool if m not in set(recent[-1:])] or pool
        counts={m:recent.count(m)+old.count(m)+preview_memory.count(m) for m in choices}
        low=min(counts.values())
        return random.choice([m for m in choices if counts[m]==low])

    def music_score(track,mood):
        if not track:return 0.0
        tagged=e.normalize(track.get('mood')); text=e.normalize(f"{track.get('title','')} {track.get('performer','')} {tagged}")
        labels=normalize_labels(tagged)
        if mood in labels:return 1.0
        hits=[(label,moods) for label,moods in music_groups.items() if label in tagged or label in text]
        if hits:
            if any(mood in moods for _,moods in hits): return .96 if any(label in labels for label,_ in hits) else .90
            return .68
        # Compare every known mood alias against title/artist/tag text.
        direct=sum(1 for w in mood_aliases.get(mood,set()) if e.normalize(w) in text)
        return .86 if direct>=2 else .78 if direct==1 else .52

    def quality(mood,caption,track,photo):
        t=e.caption_score(caption,mood); m=music_score(track,mood); i=e.image_score(photo,mood)
        c=max(0,min(1,.20*t+.48*m+.32*i))
        overall=round((t*.28+i*.30+m*.32+c*.10)*100)
        return {'text':round(t*100),'image':round(i*100),'music':round(m*100),'coherence':round(c*100),'overall':max(0,min(100,overall))}

    e.choose_mood=choose_mood; e.music_score=music_score; e.quality_score=quality

    def pick_music(tracks,mood,state,preview=False):
        if not tracks:return None
        recent=set(state.get('recent_track_ids',[])[-8:]); pids=set(state.get('preview_track_ids',[])[-20:]) if preview else set()
        available=[t for t in tracks if t.get('file_id') not in recent and t.get('file_id') not in pids]
        if not available:available=[t for t in tracks if t.get('file_id') not in recent] or tracks[:]
        ranked=sorted(available,key=lambda t:music_score(t,mood),reverse=True)
        strong=[t for t in ranked if music_score(t,mood)>=.72]
        return random.choice((strong[:8] if strong else ranked[:8]))

    def build(preview=False):
        state=bot.load_state(); lib=bot.load_library(); best=None
        for _ in range(max(14,bot.MAX_ATTEMPTS)):
            mood=choose_mood(state); caption=e.choose_caption(mood,state.get('recent_caption_hashes',[]))
            track=pick_music(lib['tracks'],mood,state,preview); photos=bot._photo_candidates(mood,state) if bot.SEND_PHOTOS else []
            photo=bot._pick_photo(photos,mood) if photos else None; score=quality(mood,caption,track,photo)
            pack={'mood':mood,'caption':caption,'track':track,'photo':photo,'score':score}
            if best is None or score['overall']>best['score']['overall']:best=pack
            if score['overall']>=max(82,bot.QUALITY_THRESHOLD) and score['image']>=72 and score['music']>=72 and score['coherence']>=78:break
        # Preview may show the best candidate even if it misses the publishing gate.
        if preview and best:
            preview_memory.append(best['mood']); del preview_memory[:-6]
            s=bot.load_state(); s['preview_moods']=(s.get('preview_moods',[])+[best['mood']])[-12:]
            if best.get('track'):s['preview_track_ids']=(s.get('preview_track_ids',[])+[best['track']['file_id']])[-25:]
            bot.save_state(s)
            return best
        # Production is now hard-gated. Never auto-publish a weak soundtrack package.
        if not best:return None
        sc=best['score']
        if not (sc['overall']>=max(82,bot.QUALITY_THRESHOLD) and sc['image']>=72 and sc['music']>=72 and sc['coherence']>=78):
            return None
        return best

    bot.build_package=build

    async def callback(update,context):
        q=update.callback_query; await q.answer()
        if not bot.is_admin(update):return
        if q.data=='preview':
            p=bot.build_package(True)
            if not p:await q.message.reply_text('❌ نتونستم Preview بسازم.');return
            s=p['score']; txt=f"🌗 حس این پست: {e.MOODS[p['mood']]['fa']} {e.MOODS[p['mood']]['emoji']}\n⭐ کیفیت: {s['overall']}/100\n📝 متن: {s['text']} | 🖼 عکس: {s['image']} | 🎧 آهنگ: {s['music']} | 🔗 هماهنگی: {s['coherence']}"; cap=f"{p['caption']}\n\n{e.SIGNATURE}\n\n{txt}"
            if p.get('photo'):
                try:
                    data=bot.requests.get(p['photo']['url'],timeout=20).content; bio=io.BytesIO(data); bio.name='preview.jpg'; await q.message.reply_photo(photo=bio,caption=cap)
                except Exception:await q.message.reply_text(cap)
            else:await q.message.reply_text(cap)
            if p.get('track'):
                t=p['track']; await q.message.reply_audio(audio=t['file_id'],caption=bot._audio_caption(t),title=t.get('title'),performer=t.get('performer'))
        elif q.data=='post':
            await bot.post_once(context,True); await q.message.reply_text('✅ ارسال شد')
        elif q.data=='pause':s=bot.load_state();s['paused']=True;bot.save_state(s);await q.message.reply_text('⏸ متوقف شد')
        elif q.data=='resume':s=bot.load_state();s['paused']=False;bot.save_state(s);await q.message.reply_text('▶️ ادامه پیدا کرد')
        elif q.data=='stats':x=bot.DB.summary();await q.message.reply_text(f"📊 SilentRuins\nپست موفق: {x['posts']}\nخطا: {x['failed']}\n۲۴ ساعت اخیر: {x['today']}\nمیانگین کیفیت: {x['avg_quality']}/100\nآهنگ‌ها: {x['tracks']}")
        elif q.data=='songs':
            ts=bot.load_library()['tracks'];await q.message.reply_text('\n'.join([f'🎵 Music Library: {len(ts)} آهنگ']+[f"{i+1}. {t.get('performer','?')} — {t.get('title','?')}" for i,t in enumerate(ts[-50:])]))
        elif q.data=='schedule':s=bot.load_state();await q.message.reply_text(f"🕐 Schedule: {', '.join(bot.POST_TIMES)}\n🌍 {bot.TZ_NAME}\n{'⏸ متوقف' if s.get('paused') else '▶️ فعال'}\nThreshold: {bot.QUALITY_THRESHOLD}")
        elif q.data=='backup':await q.message.reply_text('💾 برای Backup از /backup استفاده کن.')

    bot.callback=callback; bot.main()

if __name__=='__main__':main()
