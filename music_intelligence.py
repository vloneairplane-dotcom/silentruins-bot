"""SilentRuins Music Intelligence v7.1.

Multi-layer soundtrack selection:
- editorial mood compatibility
- legacy-tag correction from title/artist semantics
- title concept matching
- emotional intensity
- recent-track diversity
- deterministic best-first ranking
- calibrated fallback for generic legacy uploads
"""
from __future__ import annotations

import re
import content_engine as engine

MOOD_TITLE_SIGNALS = {
    "rain": {"rain", "rainy", "storm", "umbrella", "teardrop", "tears", "falling", "after rain", "rainy days", "apocalypse", "blue", "cry"},
    "love": {"love", "loved", "lovely", "heart", "heartbreak", "broken", "breakup", "sorry", "miss", "missing", "drivers license", "someone you loved", "the night we met", "i miss you", "goodbye", "perfect", "falling", "kiss", "lover"},
    "night": {"night", "midnight", "moon", "dark", "lights", "night we met", "after dark", "city lights", "nightmare", "3am", "midnight"},
    "lonely": {"lonely", "alone", "all by myself", "nobody", "someone you loved", "missing", "empty", "lost", "home", "without you", "solitude", "nobody gets me"},
    "tired": {"tired", "exhausted", "breakdown", "falling apart", "empty", "heavy", "sad", "numb", "burnout", "breathe", "drowning", "hurt", "suffer", "exhausted"},
    "ruins": {"ruins", "broken", "ashes", "ghost", "memory", "memories", "lost", "empty", "dark", "faded", "gone", "goodbye", "demons", "bury", "grave", "falling apart"},
}

PREFERRED_TAGS = {
    mood: set(info.get("music", []))
    for mood, info in engine.MOODS.items()
}

TAG_NEIGHBORS = {
    "rain": {"rain", "melancholy", "sadness", "missing", "memories", "emotional", "night", "lonely", "heartbreak", "breakup"},
    "love": {"heartbreak", "breakup", "missing", "memories", "regret", "romantic", "unrequited love", "betrayal", "emotional", "lonely"},
    "night": {"night", "dark", "melancholy", "loneliness", "lonely", "memories", "emotional", "missing", "tired"},
    "lonely": {"loneliness", "lonely", "missing", "emotional", "dark", "memories", "night", "regret", "heartbreak"},
    "tired": {"breakdown", "emotional", "loneliness", "melancholy", "regret", "sadness", "dark", "lonely", "depression"},
    "ruins": {"melancholy", "dark", "memories", "depression", "night", "emotional", "sadness", "loneliness", "lonely", "missing"},
}

DEFAULT_LEGACY_TAGS = {"", "unknown", "lonely"}

TITLE_CONCEPTS = {
    "glimpse of us": {"love": 1.00, "missing": 0.98, "memories": 0.94, "lonely": 0.92},
    "another love": {"love": 1.00, "heartbreak": 1.00, "missing": 0.96, "lonely": 0.92},
    "lovely": {"lonely": 0.98, "tired": 0.92, "ruins": 0.86},
    "someone you loved": {"missing": 1.00, "love": 0.98, "lonely": 0.96},
    "the night we met": {"night": 1.00, "memories": 1.00, "missing": 0.98, "love": 0.94},
    "what was i made for": {"tired": 0.98, "empty": 0.98, "lonely": 0.94, "ruins": 0.90},
    "i walk this earth all by myself": {"lonely": 1.00, "night": 0.90, "ruins": 0.86},
    "love in the dark": {"love": 1.00, "night": 0.98, "dark": 0.96},
    "atlantis": {"ruins": 0.96, "love": 0.92, "memories": 0.90},
    "fix you": {"love": 0.98, "emotional": 0.96, "tired": 0.90},
    "drivers license": {"love": 0.98, "missing": 0.96, "memories": 0.92},
    "i miss you, i'm sorry": {"missing": 1.00, "love": 0.98, "regret": 0.96},
}

CONCEPT_WORDS = {
    "heartbreak": {"love", "missing", "lonely", "ruins"},
    "breakup": {"love", "missing", "memories"},
    "missing": {"missing", "love", "lonely", "memories"},
    "memories": {"memories", "night", "missing", "ruins", "love"},
    "loneliness": {"lonely", "night", "tired"},
    "alone": {"lonely", "night", "ruins"},
    "empty": {"tired", "lonely", "ruins"},
    "dark": {"night", "ruins", "lonely"},
    "rain": {"rain", "night", "melancholy"},
    "falling apart": {"tired", "ruins", "love"},
}

# Calibrated floor for the existing library. These are not claims that every
# track is a perfect semantic match; they mean the library is intentionally a
# sad/ambient collection, so a legacy upload with no useful tag should not be
# scored as if it were a random genre. Title/tag evidence can always raise it.
LEGACY_BASELINE = {
    "rain": 0.78,
    "love": 0.84,
    "night": 0.82,
    "lonely": 0.86,
    "tired": 0.84,
    "ruins": 0.82,
}


def _norm(value) -> str:
    return engine.normalize(value)


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", _norm(value)).strip()


def _title_concept_score(title: str, mood: str) -> float:
    t = _compact(title)
    if not t:
        return 0.0
    best = 0.0
    for phrase, mapping in TITLE_CONCEPTS.items():
        if phrase in t:
            best = max(best, mapping.get(mood, 0.0))
    for word, moods in CONCEPT_WORDS.items():
        if word in t and mood in moods:
            best = max(best, 0.78)
    return best


def _semantic_score(track: dict, mood: str) -> float:
    tag = _compact(track.get("mood"))
    title = _compact(track.get("title"))
    performer = _compact(track.get("performer"))
    combined = f"{title} {performer}"
    preferred = PREFERRED_TAGS.get(mood, set())
    title_score = _title_concept_score(title, mood)

    if tag == mood and tag not in DEFAULT_LEGACY_TAGS:
        tag_score = 1.00
    elif tag in preferred:
        tag_score = 0.95
    elif tag in TAG_NEIGHBORS.get(mood, set()) and tag not in DEFAULT_LEGACY_TAGS:
        tag_score = 0.90
    elif tag in DEFAULT_LEGACY_TAGS:
        tag_score = LEGACY_BASELINE.get(mood, 0.78)
    else:
        tag_score = 0.58

    signals = MOOD_TITLE_SIGNALS.get(mood, set())
    hits = sum(1 for signal in signals if _norm(signal) in combined)
    signal_score = min(0.98, 0.72 + hits * 0.07) if hits else 0.0

    preferred_hits = sum(1 for concept in preferred if _norm(concept) in combined)
    preferred_score = min(0.94, 0.74 + preferred_hits * 0.05) if preferred_hits else 0.0

    return max(0.0, min(1.0, max(tag_score, title_score, signal_score, preferred_score)))


def smart_music_score(track, mood):
    if not track:
        return 0.30
    semantic = _semantic_score(track, mood)
    title = _compact(track.get("title"))
    tag = _compact(track.get("mood"))
    concept = _title_concept_score(title, mood)
    if title and concept >= 0.90:
        semantic = max(semantic, concept)
    if tag == mood and tag not in DEFAULT_LEGACY_TAGS:
        semantic = min(1.0, semantic + 0.02)
    return round(max(0.30, min(1.0, semantic)), 3)


def _candidate_rank(track: dict, mood: str, recent_ids: set[str], preview_ids: set[str]):
    score = smart_music_score(track, mood)
    tid = track.get("file_id")
    penalty = 0.0
    if tid in preview_ids:
        penalty += 0.18
    if tid in recent_ids:
        penalty += 0.22
    metadata_bonus = 0.02 if _compact(track.get("title")) and _compact(track.get("performer")) else 0.0
    return score + metadata_bonus - penalty


def smart_choose_music(tracks, mood, recent_ids=None, preview_ids=None):
    tracks = [t for t in (tracks or []) if isinstance(t, dict) and t.get("file_id")]
    if not tracks:
        return None
    recent_ids = set((recent_ids or [])[-8:])
    preview_ids = set((preview_ids or [])[-20:])
    fresh = [t for t in tracks if t.get("file_id") not in recent_ids | preview_ids]
    if not fresh:
        fresh = [t for t in tracks if t.get("file_id") not in recent_ids]
    if not fresh:
        fresh = tracks[:]
    ranked = sorted(fresh, key=lambda t: _candidate_rank(t, mood, recent_ids, preview_ids), reverse=True)
    best = smart_music_score(ranked[0], mood)
    band = [t for t in ranked if smart_music_score(t, mood) >= max(0.78, best - 0.06)]
    if not band:
        band = ranked[:1]
    return band[0]


engine.music_score = smart_music_score


def apply(bot_module):
    bot_module.choose_music = smart_choose_music
    bot_module.MAX_ATTEMPTS = max(getattr(bot_module, "MAX_ATTEMPTS", 8), 24)
    return bot_module
