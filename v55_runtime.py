"""SilentRuins v6 runtime: persistent soundtrack profiles and strict anti-repetition."""
from __future__ import annotations
import hashlib, io, random
from datetime import datetime


def main():
    import content_engine as e
    import bot

    preview_memory=[]
    MOOD_WORDS={
      "rain":("rain rainy storm بارون باران"),
      "night":("night midnight dark nocturnal شب نیمه شب"),
      "lonely":("lonely loneliness alone solitude isolation تنهایی"),
      "love":("love romantic romance heartbreak breakup betrayal missing loss دلتنگی شکست"),
      "ruins":("memory memories nostalgia past broken empty emptiness loss خاطره ویرونه ویرانه"),
      "tired":("tired exhausted burnout breakdown depression regret خستگی درد"),
    }
    PHRASES={
      "the night we met":{"ruins":1,"love":.92,"night":.9,"lonely":.86},
      "glimpse of us":{"love":1,"ruins":.9,"lonely":.86},
      "another love":{"love":1,"lonely":.9,"night":.8,"ruins":.76},
      "lovely":{"lonely":1,"night":.88,"tired":.72},
      "someone you loved":{"love":1,"lonely":.94,"ruins":.84},
      "what was i made for":{"tired":.92,"lonely":.9,"ruins":.86,"night":.84},
      "i walk this earth all by myself":{"lonely":1,"night":.88,"ruins":.8},
      "love in the dark":{"love":1,"night":.96,"lonely":.9,"ruins":.78},
      "drivers license":{"love":.98,"ruins":.86,"lonely":.84,"night":.74},
      "i miss you":{"love":.9,"lonely":.94,"ruins":.84,"night":.78},
      "fix you":{"tired":.84,"lonely":.82,"love":.74,"rain":.72},
      "dark paradise":{"love":.9,"night":1,"lonely":.86,"ruins":.74},
      "atlantis":{"love":.88,"ruins":.94,"lonely":.86,"night":.82},
    }
    def norm(x): return e.normalize(str(x or "")).replace("ي","ی").replace("ك","ک").replace("’","'").lower().strip()
    def profile(t):
      old=t.get("mood_profile")
      if isinstance(old,dict) and all(m in old for m in e.MOODS): return old
      tag=norm(t.get("mood")); text=norm(f"{t.get('title','')} {t.get('performer','')} {tag}")
      p={m:.42 for m in e.MOODS}
      for m,words in MOOD_WORDS.items():
        for w in words.split():
          if w in tag: p[m]=max(p[m],1.0 if w in ("night","lonely","love","memory","memories","tired","rain") else .88)
      for phrase,vals in PHRASES.items():
        if phrase in text:
          for m,v in vals.items(): p[m]=max(p[m],v)
      for m in e.MOODS:
        if tag==m or tag==norm(e.MOODS[m]["fa"]): p[m]=1.0
        for a in e.MOOD_ALIASES.get(m,[]):
          a=norm(a)
          if len(a)>=4 and a in text: p[m]=max(p[m],.82)
      t["mood_profile"]={m:round(max(0,min(1,v)),3) for m,v in p.items()}
      return t["mood_profile"]
    def profile_library(lib):
      changed=False
      for t in lib.get("tracks",[]):
        old=t.get("mood_profile"); profile(t)
        if old!=t.get("mood_profile"): changed=True
      if changed: bot.save_library(lib)
      return lib
    def music_score(t,mood): return float(profile(t).get(mood,.42)) if t else 0.0
    def choose_mood(state,hour=None):
      h=datetime.now().hour if hour is None else hour
      pool=["night","lonely","love","ruins"] if h>=22 or h<5 else (["love","lonely","night","rain","ruins"] if h>=17 else ["tired","love","rain","lonely","ruins"])
      blocked=set(list(state.get("recent_moods",[]))[-3:]+list(state.get("preview_moods",[]))[-6:]+preview_memory[-4:])
      choices=[m for m in pool if m not in blocked] or [m for m in pool if m not in set(list(state.get("recent_moods",[]))[-1:])] or pool
      counts={m:sum(1 for x in list(state.get("recent_moods",[]))+list(state.get("preview_moods",[]))+preview_memory if x==m) for m in choices}
      low=min(counts.values()); return random.choice([m for m in choices if counts[m]==low])
    def quality(m,c,t,p):
      ts=e.caption_score(c,m); ms=music_score(t,m); im=e.image_score(p,m); co=max(0,min(1,.12*ts+.56*ms+.32*im))
      return {"text":round(ts*100),"image":round(im*100),"music":round(ms*100),"coherence":round(co*100),"overall":round((ts*.25+im*.25+ms*.38+co*.12)*100)}
    e.choose_mood=choose_mood; e.music_score=music_score; e.quality_score=quality
    def pick(tracks,mood,state,preview):
      recent=set(state.get("recent_track_ids",[])[-8:]); seen=set(state.get("preview_track_ids",[])[-25:]) if preview else set()
      fresh=[t for t in tracks if t.get("file_id") not in recent and t.get("file_id") not in seen]
      strong=sorted([t for t in fresh if music_score(t,mood)>=.72],key=lambda t:music_score(t,mood),reverse=True)
      if strong:return random.choice(strong[:12])
      reusable=sorted([t for t in tracks if t.get("file_id") not in recent and music_score(t,mood)>=.72],key=lambda t:music_score(t,mood),reverse=True)
      if reusable:return random.choice(reusable[:12])
      ranked=sorted(tracks,key=lambda t:music_score(t,mood),reverse=True); return ranked[0] if ranked else None
    def build(preview=False):
      state=bot.load_state(); lib=profile_library(bot.load_library()); gate=max(82,bot.QUALITY_THRESHOLD); block=list(state.get("recent_caption_hashes",[]))[-25:]+list(state.get("preview_caption_hashes",[]))[-25:]; best=None
      for _ in range(max(24,bot.MAX_ATTEMPTS)):
        m=choose_mood(state); c=e.choose_caption(m,block); t=pick(lib["tracks"],m,state,preview); photos=bot._photo_candidates(m,state) if bot.SEND_PHOTOS else []; ph=bot._pick_photo(photos,m) if photos else None; sc=quality(m,c,t,ph); pack={"mood":m,"caption":c,"track":t,"photo":ph,"score":sc}
        if best is None or (sc["music"],sc["overall"])>(best["score"]["music"],best["score"]["overall"]): best=pack
        if sc["music"]>=72 and sc["image"]>=72 and sc["coherence"]>=78 and sc["overall"]>=gate: break
      if not best:return None
      sc=best["score"]
      if sc["music"]<72:return None
      if not preview and not(sc["overall"]>=gate and sc["image"]>=72 and sc["music"]>=72 and sc["coherence"]>=78):return None
      if preview:
        preview_memory.append(best["mood"]); del preview_memory[:-6]; s=bot.load_state(); s["preview_moods"]=(s.get("preview_moods",[])+[best["mood"]])[-12:]
        if best.get("track"):s["preview_track_ids"]=(s.get("preview_track_ids",[])+[best["track"]["file_id"]])[-25:]
        h=hashlib.sha256(norm(best["caption"]).encode()).hexdigest(); s["preview_caption_hashes"]=(s.get("preview_caption_hashes",[])+[h])[-25:]; bot.save_state(s)
      return best
    bot.build_package=build
    async def preview(update,context):
      if not bot.is_admin(update):return
      p=build(True); target=update.callback_query.message if getattr(update,"callback_query",None) else update.message
      if not p: await target.reply_text("❌ Preview با آهنگ مناسب پیدا نشد؛ آهنگ ضعیف عمداً نمایش داده نمی‌شود."); return
      s=p["score"]; cap=f"{p['caption']}\n\n{e.SIGNATURE}\n\n🌗 حس این پست: {e.MOODS[p['mood']]['fa']} {e.MOODS[p['mood']]['emoji']}\n⭐ کیفیت: {s['overall']}/100\n📝 متن: {s['text']} | 🖼 عکس: {s['image']} | 🎧 آهنگ: {s['music']} | 🔗 هماهنگی: {s['coherence']}"
      if p.get("photo"):
        try:
          data=bot.requests.get(p["photo"]["url"],timeout=20).content; b=io.BytesIO(data); b.name="preview.jpg"; await target.reply_photo(photo=b,caption=cap)
        except Exception: await target.reply_text(cap)
      else: await target.reply_text(cap)
      if p.get("track"):
        t=p["track"]; await target.reply_audio(audio=t["file_id"],caption=bot._audio_caption(t),title=t.get("title"),performer=t.get("performer"))
    bot.preview=preview
    async def callback(update,context):
      q=update.callback_query; await q.answer()
      if not bot.is_admin(update):return
      if q.data=="preview":await preview(update,context)
      elif q.data=="post":await bot.post_once(context,True);await q.message.reply_text("✅ ارسال شد")
      elif q.data=="pause":s=bot.load_state();s["paused"]=True;bot.save_state(s);await q.message.reply_text("⏸ متوقف شد")
      elif q.data=="resume":s=bot.load_state();s["paused"]=False;bot.save_state(s);await q.message.reply_text("▶️ ادامه پیدا کرد")
      elif q.data=="stats":await bot.stats(update,context)
      elif q.data=="songs":
        ts=bot.load_library()["tracks"];await q.message.reply_text("🎵 Music Library: "+str(len(ts))+" آهنگ")
      elif q.data=="schedule":await bot.schedule_cmd(update,context)
      elif q.data=="backup":await q.message.reply_text("💾 برای Backup از /backup استفاده کن.")
    bot.callback=callback
    bot.main()

if __name__=="__main__":main()
