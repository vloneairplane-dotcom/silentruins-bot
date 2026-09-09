"""SilentRuins Music Intelligence v6.2.
Semantic soundtrack matching layered on top of the existing track metadata.
"""
from __future__ import annotations

import re
import random
import content_engine as engine

# Strong title/artist signals for the six editorial moods.
MOOD_TITLE_SIGNALS = {
    "rain": {"rain", "rainy", "storm", "umbrella", "teardrop", "tears", "falling"},
    "love": {"love", "loved", "lovely", "heart", "heartbreak", "broken", "breakup", "sorry", "miss", "missing", "drivers license", "someone you loved", "the night we met"},
    "night": {"night", "midnight", "moon", "dark", "lights", "night we met", "after dark"},
    "lonely": {"lonely", "alone", "all by myself", "nobody", "someone you loved", "missing", "empty"},
    "tired": {"tired", "exhausted", "breakdown", "falling apart", "empty", "heavy", "sad", "depression"},
    "ruins": {"ruins", "broken", "ashes", "ghost", "memory", "memories", "lost", "empty", "dark"},
}

# Tags that are emotionally close enough to count as a strong match.
TAG_NEIGHBORS = {
    "rain": {"rain", "melancholy", "sadness", "missing", "memories", "emotional", "night"},
    "love": {"heartbreak", "breakup", "missing", "memories", "regret", "romantic", "unrequited love", "betrayal", "emotional"},
    "night": {"night", "dark", "melancholy", "loneliness", "lonely", "memories", "emotional", "missing"},
    "lonely": {"loneliness", "lonely", "missing", "emotional", "dark", "memories", "night", "regret"},
    "tired": {"breakdown", "depression", "emotional", "loneliness", "melancholy", "regret", "sadness", "dark"},
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

    # Metadata remains the strongest signal.
    if tag == mood:
        return 1.00
    if tag in TAG_NEIGHBORS.get(mood, set()):
        base = 0.94
    else:
        base = 0.52

    # Title-level semantic signal can rescue tracks whose library tag is broad.
    signals = MOOD_TITLE_SIGNALS.get(mood, set())
    hits = sum(1 for s in signals if _norm(s) in combined)
    if hits:
        base = max(base, min(0.98, 0.82 + hits * 0.05))

    # Generic artist-name matches should never dominate mood metadata.
    if title and len(title.split()) <= 5 and any(_norm(s) in title for s in signals):
        base = max(base, 0.90)

    return max(0.30, min(1.0, base))


def smart_choose_music(tracks, mood, recent_ids, preview_ids=None):
    if not tracks:
        return None
    blocked = set(recent_ids[-8:]) | set((preview_ids or [])[-20:])
    fresh = [t for t in tracks if t.get("file_id") not in blocked]
    if not fresh:
        fresh = [t for t in tracks if t.get("file_id") not in set(recent_ids[-8:])] or tracks[:]

    ranked = sorted(fresh, key=lambda t: smart_music_score(t, mood), reverse=True)
    # Keep some variety among near-equal top tracks, but never randomize the whole library.
    top_score = smart_music_score(ranked[0], mood)
    shortlist = [t for t in ranked if smart_music_score(t, mood) >= max(0.82, top_score - 0.08)]
    return random.choice(shortlist[:min(6, len(shortlist))])


# Patch the engine so existing quality_score automatically uses the improved scorer.
engine.music_score = smart_music_score


def apply(bot_module):
    bot_module.choose_music = smart_choose_music
    bot_module.MAX_ATTEMPTS = max(bot_module.MAX_ATTEMPTS, 24)
    return bot_module
