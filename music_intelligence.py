"""SilentRuins Music Intelligence v6.3.
Safe semantic soundtrack matching with a hard no-empty-choice guarantee.
"""
from __future__ import annotations
import random
import content_engine as engine

MOOD_TITLE_SIGNALS = {
    "rain": {"rain", "rainy", "storm", "umbrella", "teardrop", "tears", "falling"},
    "love": {"love", "loved", "lovely", "heart", "heartbreak", "broken", "breakup", "sorry", "miss", "missing", "drivers license", "someone you loved", "the night we met"},
    "night": {"night", "midnight", "moon", "dark", "lights", "night we met", "after dark"},
    "lonely": {"lonely", "alone", "all by myself", "nobody", "someone you loved", "missing", "empty"},
    "tired": {"tired", "exhausted", "breakdown", "falling apart", "empty", "heavy", "sad"},
    "ruins": {"ruins", "broken", "ashes", "ghost", "memory", "memories", "lost", "empty", "dark"},
}

TAG_NEIGHBORS = {
    "rain": {"rain", "melancholy", "sadness", "missing", "memories", "emotional", "night"},
    "love": {"heartbreak", "breakup", "missing", "memories", "regret", "romantic", "unrequited love", "betrayal", "emotional"},
    "night": {"night", "dark", "melancholy", "loneliness", "lonely", "memories", "emotional", "missing"},
    "lonely": {"loneliness", "lonely", "missing", "emotional", "dark", "memories", "night", "regret"},
    "tired": {"breakdown", "emotional", "loneliness", "melancholy", "regret", "sadness", "dark"},
    "ruins": {"melancholy", "dark", "memories", "depression", "night", "emotional", "sadness", "loneliness"},
}

def _norm(v):
    return engine.normalize(v)

def smart_music_score(track, mood):
    if not track:
        return 0.30
    tag = _norm(track.get("mood"))
    title = _norm(track.get("title"))
    performer = _norm(track.get("performer"))
    combined = f"{title} {performer} {tag}"
    if tag == mood:
        base = 1.00
    elif tag in TAG_NEIGHBORS.get(mood, set()):
        base = 0.94
    else:
        base = 0.52
    signals = MOOD_TITLE_SIGNALS.get(mood, set())
    hits = sum(1 for s in signals if _norm(s) in combined)
    if hits:
        base = max(base, min(0.98, 0.82 + hits * 0.05))
    return max(0.30, min(1.0, base))

def smart_choose_music(tracks, mood, recent_ids=None, preview_ids=None):
    tracks = tracks or []
    if not tracks:
        return None
    recent_ids = recent_ids or []
    preview_ids = preview_ids or []
    blocked = set(recent_ids[-8:]) | set(preview_ids[-20:])
    fresh = [t for t in tracks if t.get("file_id") not in blocked]
    if not fresh:
        fresh = [t for t in tracks if t.get("file_id") not in set(recent_ids[-8:])]
    if not fresh:
        fresh = list(tracks)
    ranked = sorted(fresh, key=lambda t: smart_music_score(t, mood), reverse=True)
    top_score = smart_music_score(ranked[0], mood)
    threshold = max(0.82, top_score - 0.08)
    shortlist = [t for t in ranked if smart_music_score(t, mood) >= threshold]
    if not shortlist:
        shortlist = ranked[:1]
    return random.choice(shortlist[:min(6, len(shortlist))])

engine.music_score = smart_music_score

def apply(bot_module):
    bot_module.choose_music = smart_choose_music
    bot_module.MAX_ATTEMPTS = max(getattr(bot_module, "MAX_ATTEMPTS", 8), 24)
    return bot_module
