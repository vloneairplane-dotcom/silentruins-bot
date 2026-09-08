"""SilentRuins V4.3 calibrated editorial quality engine.

Scores the complete mood + caption + image + music package. The score is a
selection signal, not a cosmetic number: strong sets should land in the
80s/90s, while obvious mismatches remain below the publishing threshold.
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
    "bunny", "rabbit ears", "ears filter", "costume", "party", "festival",
    "celebration", "influencer", "selfie", "shopping", "vacation", "wedding",
    "birthday", "toy", "cartoon", "neon party", "concert", "fashion shoot",
}

STRONG_VISUAL_TERMS = {
    "alone", "lonely", "silhouette", "window", "empty", "street", "night",
    "moon", "rain", "reflection", "fog", "abandoned", "broken", "room",
    "distance", "shadow", "sad", "dark", "memories", "bench", "figure",
    "person", "woman", "man", "girl", "boy", "face",
}

CAPTION_CUES = {
    "love": {"عشق", "دلتنگ", "خاطره", "رفتن", "نبودن", "برنگشت", "رابطه", "جدایی", "دل"},
    "lonely": {"تنهایی", "تنها", "سکوت", "فاصله", "هیچکس", "کسی", "نباشی", "نبودن"},
    "night": {"شب", "نیمه شب", "ماه", "چراغ", "تاریکی", "سکوت", "نیمه‌شب"},
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

    score = 0.72
    words = tokens(text)
    length = len(text)

    if 30 <= length <= 120:
        score += 0.09
    elif 22 <= length <= 145:
        score += 0.04
    elif length < 15 or length > 190:
        score -= 0.10

    if 6 <= len(words) <= 22:
        score += 0.06
    elif len(words) < 4:
        score -= 0.08

    if any(h in text for h in GOOD_CAPTION_HINTS):
        score += 0.05
    if any(b in text for b in BAD_CAPTION_PATTERNS):
        score -= 0.50
    if text.count("#") or text.count("؟") >= 2:
        score -= 0.06
    if re.search(r"[!?]{2,}", text):
        score -= 0.05

    cues = CAPTION_CUES.get(mood, set())
    cue_hits = sum(1 for cue in cues if normalize(cue) in text)
    if cue_hits:
        score += min(0.08, cue_hits * 0.04)
    else:
        semantic = mood_similarity(
            text,
            mood,
            {m: {"queries": list(p.get("concepts", []))} for m, p in MOOD_PROFILES.items()},
            None,
        )
        score += min(0.04, semantic * 0.08)

    return max(0.0, min(1.0, score))


def _image_score(photo_meta: dict | None, mood: str) -> tuple[float, float]:
    if not photo_meta:
        return 0.50, 0.85

    query = normalize(photo_meta.get("query", ""))
    alt = normalize(photo_meta.get("alt", ""))
    haystack = f"{query} {alt}"

    strong_hits = sum(1 for term in STRONG_VISUAL_TERMS if normalize(term) in haystack)
    bad_hits = sum(1 for term in BAD_VISUAL_TERMS if normalize(term) in haystack)
    mood_terms = {normalize(x) for x in MOOD_PROFILES.get(mood, {}).get("visual_terms", set())}
    mood_hits = sum(1 for term in mood_terms if term and term in haystack)

    score = 0.70
    score += min(0.12, strong_hits * 0.025)
    score += min(0.10, mood_hits * 0.025)
    score -= min(0.30, bad_hits * 0.12)

    luminance = photo_meta.get("luminance")
    if isinstance(luminance, (int, float)):
        if 42 <= luminance <= 90:
            score += 0.08
        elif 30 <= luminance < 42 or 90 < luminance <= 115:
            score += 0.03
        elif luminance < 30:
            score -= 0.10
        elif luminance > 145:
            score -= 0.08

    clean = max(0.0, 1.0 - min(1.0, bad_hits * 0.30))
    return max(0.0, min(1.0, score)), clean


def _music_score(track: dict | None, mood: str, moods: dict, aliases: dict | None) -> float:
    if not track:
        return 0.35
    return max(0.0, min(1.0, track_match(track, mood, moods, aliases)))


def _coherence(caption: str, mood: str, track: dict | None, photo_meta: dict | None,
               moods: dict, aliases: dict | None) -> float:
    caption_text = _caption_core(caption)
    cue_hits = sum(1 for cue in CAPTION_CUES.get(mood, set()) if normalize(cue) in caption_text)
    caption_signal = min(1.0, 0.70 + cue_hits * 0.06)

    music_signal = _music_score(track, mood, moods, aliases)
    image_signal, clean = _image_score(photo_meta, mood)

    # Coherence is intentionally high only when all three layers are reasonably strong.
    weakest = min(caption_signal, music_signal, image_signal)
    average = (caption_signal + music_signal + image_signal) / 3.0
    coherence = average * 0.60 + weakest * 0.40

    if music_signal >= 0.95 and image_signal >= 0.80:
        coherence += 0.03
    if clean < 0.70:
        coherence -= 0.10

    return max(0.0, min(1.0, coherence))


def quality_score(mood: str, caption: str, track: dict | None, photo_meta: dict | None,
                  moods: dict, aliases: dict | None = None) -> dict:
    """Return calibrated 0-100 component and overall editorial scores."""
    text = _caption_score(caption, mood)
    image, clean = _image_score(photo_meta, mood)
    music = _music_score(track, mood, moods, aliases)
    coherence = _coherence(caption, mood, track, photo_meta, moods, aliases)

    # The score rewards a complete package. Music and coherence are slightly
    # more important than raw image aesthetics for SilentRuins.
    overall = (
        text * 0.30
        + image * 0.22
        + music * 0.28
        + coherence * 0.20
    ) * 100

    # Only serious problems get hard penalties. Do not punish a valid cinematic
    # image merely because its metadata is sparse.
    if text < 0.52:
        overall -= 8
    if music < 0.65:
        overall -= 7
    if image < 0.52:
        overall -= 5
    if clean < 0.70:
        overall -= 8
    if coherence < 0.62:
        overall -= 6

    overall = max(0, min(100, round(overall)))
    return {
        "text": round(text * 100),
        "image": round(image * 100),
        "music": round(music * 100),
        "coherence": round(coherence * 100),
        "overall": overall,
    }
