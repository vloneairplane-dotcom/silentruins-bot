"""SilentRuins V4.3 editorial quality engine.

Scores a complete post as a coherent editorial package instead of rewarding
individual components in isolation. The engine is intentionally deterministic
for the same inputs so the score can be trusted as a publishing gate.
"""
from __future__ import annotations

import re

from content_engine import (
    MOOD_PROFILES,
    MUSIC_TAG_MAP,
    BAD_CAPTION_PATTERNS,
    GOOD_CAPTION_HINTS,
    mood_similarity,
    track_match,
    normalize,
    tokens,
)


BAD_VISUAL_TERMS = {
    "bunny", "rabbit", "ears", "costume", "party", "festival", "celebration",
    "fashion", "influencer", "selfie", "shopping", "vacation", "wedding",
    "birthday", "toy", "cartoon", "colorful", "neon party", "concert",
}

STRONG_VISUAL_TERMS = {
    "alone", "lonely", "silhouette", "window", "empty", "street", "night",
    "moon", "rain", "reflection", "fog", "abandoned", "broken", "room",
    "distance", "shadow", "sad", "dark", "memories", "bench",
}


# Persian/English mood cues used to judge whether caption and soundtrack tell
# the same emotional story. These are deliberately conservative.
CAPTION_MUSIC_CUES = {
    "love": {"عشق", "دلتنگ", "خاطره", "رفتن", "نبودن", "برنگشت", "رابطه", "جدایی", "دل"},
    "lonely": {"تنهایی", "تنها", "سکوت", "فاصله", "هیچکس", "کسی", "نباشی"},
    "night": {"شب", "نیمه شب", "ماه", "چراغ", "تاریکی", "سکوت"},
    "rain": {"باران", "بارون", "پنجره", "خیس", "خیابان", "خیابون"},
    "tired": {"خسته", "خستگی", "فکر", "سنگینی", "بغض", "طاقت"},
    "ruins": {"ویرانه", "خرابه", "متروک", "شکسته", "گذشته", "خاموش"},
}


def _caption_core(caption: str) -> str:
    text = normalize(caption)
    return re.sub(r"—\s*silent\s+ruins.*$", "", text).strip()


def _caption_score(caption: str, mood: str) -> float:
    text = _caption_core(caption)
    if not text:
        return 0.0
    score = 0.68
    word_count = len(tokens(text))
    length = len(text)

    if 30 <= length <= 120:
        score += 0.10
    elif 22 <= length <= 145:
        score += 0.05
    elif length < 15 or length > 180:
        score -= 0.10

    if 6 <= word_count <= 22:
        score += 0.08
    elif word_count < 4:
        score -= 0.08

    if any(h in text for h in GOOD_CAPTION_HINTS):
        score += 0.05
    if any(b in text for b in BAD_CAPTION_PATTERNS):
        score -= 0.45
    if text.count("#") or text.count("؟") >= 2:
        score -= 0.07
    if re.search(r"[!?]{2,}", text):
        score -= 0.05

    semantic = mood_similarity(text, mood, {m: {"queries": list(p.get("concepts", []))} for m, p in MOOD_PROFILES.items()}, None)
    score += min(0.10, semantic * 0.16)
    return max(0.0, min(1.0, score))


def _image_score(photo_meta: dict | None, mood: str) -> tuple[float, float]:
    if not photo_meta:
        return 0.45, 0.45

    query = normalize(photo_meta.get("query", ""))
    alt = normalize(photo_meta.get("alt", ""))
    haystack = f"{query} {alt}"
    strong = sum(1 for term in STRONG_VISUAL_TERMS if normalize(term) in haystack)
    bad = sum(1 for term in BAD_VISUAL_TERMS if normalize(term) in haystack)

    score = 0.66
    score += min(0.16, strong * 0.025)
    score -= min(0.28, bad * 0.10)

    luminance = photo_meta.get("luminance")
    if isinstance(luminance, (int, float)):
        if 42 <= luminance <= 85:
            score += 0.10
        elif 35 <= luminance < 42 or 85 < luminance <= 115:
            score += 0.03
        elif luminance < 35:
            score -= 0.12
        elif luminance > 140:
            score -= 0.13
        elif luminance > 115:
            score -= 0.05

    # Human/solitary imagery is a core part of the brand, but don't require it.
    human_terms = {"person", "man", "woman", "human", "face", "boy", "girl", "silhouette"}
    if any(term in haystack for term in human_terms):
        score += 0.04

    mood_visuals = {normalize(x) for x in MOOD_PROFILES.get(mood, {}).get("visual_terms", set())}
    mood_hits = sum(1 for term in mood_visuals if term and term in haystack)
    score += min(0.08, mood_hits * 0.02)

    return max(0.0, min(1.0, score)), 1.0 - min(1.0, bad * 0.25)


def _music_score(track: dict | None, mood: str, moods: dict, aliases: dict | None) -> float:
    if not track:
        return 0.35
    base = track_match(track, mood, moods, aliases)
    return max(0.0, min(1.0, base))


def _coherence(caption: str, mood: str, track: dict | None, photo_meta: dict | None, moods: dict, aliases: dict | None) -> float:
    """Measure whether the three media layers reinforce one emotional intent."""
    caption_text = _caption_core(caption)
    caption_mood_hits = sum(
        1 for cue in CAPTION_MUSIC_CUES.get(mood, set())
        if normalize(cue) in caption_text
    )
    caption_signal = min(1.0, 0.55 + caption_mood_hits * 0.10)

    music_signal = _music_score(track, mood, moods, aliases)
    image_signal, image_clean = _image_score(photo_meta, mood)

    # A good package needs at least two independent layers to agree strongly.
    agreement = (caption_signal * 0.34 + music_signal * 0.36 + image_signal * 0.30)
    if music_signal >= 0.95 and image_signal >= 0.78:
        agreement += 0.04
    if image_clean < 0.75:
        agreement -= 0.08
    return max(0.0, min(1.0, agreement))


def quality_score(mood: str, caption: str, track: dict | None, photo_meta: dict | None,
                  moods: dict, aliases: dict | None = None) -> dict:
    """Return calibrated 0-100 editorial scores for a complete post."""
    text = _caption_score(caption, mood)
    image, image_clean = _image_score(photo_meta, mood)
    music = _music_score(track, mood, moods, aliases)
    coherence = _coherence(caption, mood, track, photo_meta, moods, aliases)

    # SilentRuins is an emotional media brand: soundtrack and coherence matter
    # slightly more than raw visual attractiveness.
    overall = (
        text * 0.32
        + image * 0.23
        + music * 0.27
        + coherence * 0.18
    ) * 100

    # Publishing should reject obvious mismatches rather than letting one strong
    # component hide a serious weakness.
    if text < 0.55:
        overall -= 10
    if music < 0.70:
        overall -= 8
    if image < 0.58:
        overall -= 7
    if image_clean < 0.75:
        overall -= 8
    if coherence < 0.68:
        overall -= 5

    overall = max(0, min(100, round(overall)))
    return {
        "text": round(text * 100),
        "image": round(image * 100),
        "music": round(music * 100),
        "coherence": round(coherence * 100),
        "overall": overall,
    }
