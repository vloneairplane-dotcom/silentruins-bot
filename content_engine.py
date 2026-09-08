"""SilentRuins V4.3 content intelligence.

Every post is treated as one editorial package:
    mood + caption + image + music

V4.3 focuses on consistency rather than optimistic scoring. It adds:
- stronger Persian caption quality and mood relevance
- visual-intent scoring with penalties for generic/off-brand imagery
- music compatibility scoring
- explicit text/image/music coherence
- diversity-aware quality penalties
- a publishing-friendly score that rewards complete sets, not isolated good parts
"""
from __future__ import annotations

import hashlib
import random
import re
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Normalization / lexical helpers
# ---------------------------------------------------------------------------

def normalize(text: str | None) -> str:
    text = (text or "").lower()
    replacements = {
        "ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه",
        "ؤ": "و", "إ": "ا", "أ": "ا", "ـ": "",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    text = re.sub(r"[\u200c\u200f\u200e]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokens(text: str | None) -> set[str]:
    return {t for t in re.findall(r"[\w\u0600-\u06ff-]+", normalize(text)) if len(t) >= 2}


def _contains_any(text: str, phrases: set[str]) -> int:
    return sum(1 for phrase in phrases if phrase and phrase in text)


# ---------------------------------------------------------------------------
# Editorial taxonomy
# ---------------------------------------------------------------------------
MOOD_PROFILES: dict[str, dict[str, Any]] = {
    "rain": {
        "time_weights": {"day": 1, "morning": 5, "afternoon": 3, "evening": 5, "night": 2},
        "concepts": {"rain", "window", "wet", "street", "silence", "reflection", "بارون", "پنجره", "خیابون"},
        "music_tags": {"rain", "melancholy", "memories", "emotional", "night"},
        "visual_terms": {"rain", "window", "wet", "reflection", "street", "umbrella", "storm"},
    },
    "night": {
        "time_weights": {"day": 0.5, "morning": 0.5, "afternoon": 1, "evening": 7, "night": 12},
        "concepts": {"night", "midnight", "moon", "dark", "city", "street", "silence", "شب", "نیمه شب", "ماه"},
        "music_tags": {"night", "dark night", "melancholy", "loneliness", "emotional", "memories"},
        "visual_terms": {"night", "moon", "dark", "city", "silhouette", "neon", "street", "midnight"},
    },
    "lonely": {
        "time_weights": {"day": 2, "morning": 1, "afternoon": 2, "evening": 8, "night": 11},
        "concepts": {"alone", "lonely", "silence", "empty", "distance", "تنهایی", "تنها", "سکوت", "فاصله"},
        "music_tags": {"loneliness", "lonely", "missing", "emotional", "dark", "memories", "night"},
        "visual_terms": {"alone", "lonely", "single", "empty", "silhouette", "bench", "room", "window", "distance"},
    },
    "love": {
        "time_weights": {"day": 3, "morning": 2, "afternoon": 4, "evening": 10, "night": 4},
        "concepts": {"love", "missing", "heartbreak", "memory", "goodbye", "distance", "دلتنگی", "عشق", "خاطره", "رفتن"},
        "music_tags": {"heartbreak", "missing", "breakup", "regret", "romantic", "unrequited love", "betrayal", "emotional", "memories"},
        "visual_terms": {"rose", "letter", "photograph", "couple", "distance", "empty bed", "goodbye", "memory"},
    },
    "tired": {
        "time_weights": {"day": 6, "morning": 2, "afternoon": 8, "evening": 5, "night": 2},
        "concepts": {"tired", "exhausted", "overthinking", "silence", "burden", "خستگی", "خسته", "فکر", "سنگینی"},
        "music_tags": {"breakdown", "depression", "emotional", "loneliness", "melancholy", "regret"},
        "visual_terms": {"tired", "eyes", "head down", "smoke", "candle", "broken mirror", "hood", "exhausted"},
    },
    "ruins": {
        "time_weights": {"day": 2, "morning": 1, "afternoon": 3, "evening": 7, "night": 10},
        "concepts": {"ruins", "abandoned", "fog", "old", "broken", "silence", "ویرانه", "خرابه", "مه", "متروک"},
        "music_tags": {"melancholy", "dark", "memories", "depression", "night", "emotional"},
        "visual_terms": {"ruins", "abandoned", "fog", "old house", "forest", "dead tree", "gothic", "broken", "empty"},
    },
}

MUSIC_TAG_MAP: dict[str, set[str]] = {
    "heartbreak": {"love", "lonely", "night"},
    "breakup": {"love", "lonely", "night"},
    "missing": {"love", "lonely", "night", "rain"},
    "memories": {"love", "lonely", "night", "rain", "ruins"},
    "emotional": {"night", "lonely", "love", "tired", "rain"},
    "romantic": {"love"},
    "unrequited love": {"love", "lonely"},
    "regret": {"love", "tired", "lonely"},
    "betrayal": {"love", "lonely", "tired"},
    "resentment": {"love", "tired"},
    "insecurity": {"lonely", "tired", "love"},
    "confusion": {"love", "tired", "lonely"},
    "distance": {"love", "lonely", "night"},
    "toxic love": {"love", "lonely", "night"},
    "obsession": {"love", "night", "lonely"},
    "anger": {"tired", "love"},
    "breakdown": {"tired", "lonely", "night"},
    "depression": {"tired", "lonely", "ruins", "night"},
    "sadness": {"rain", "tired", "lonely", "night"},
    "melancholy": {"rain", "night", "lonely", "ruins", "tired"},
    "dark": {"night", "ruins", "lonely"},
    "dark night": {"night", "lonely", "ruins"},
    "loneliness": {"lonely", "night", "ruins"},
    "lonely": {"lonely", "night"},
    "night": {"night", "lonely"},
    "rain": {"rain", "night"},
    "fear": {"night", "tired", "lonely"},
}

BAD_CAPTION_PATTERNS = {
    "رورو", "بدترین قراره", "یه بارونی بزن", "لاله‌های وطن", "پاییز مواظب گلا نیست",
    "خواب برای اوناست که دار می‌شن", "تو جمع پر بحث", "سفره‌ی تک‌نفره", "حساب من",
    "کی قراره حالتو بپرسه", "توی خونه غرقیم",
}

GOOD_CAPTION_HINTS = {
    "شب", "سکوت", "تنهایی", "خاطره", "دلتنگ", "رفتن", "ماندن", "نبودن", "باران",
    "پنجره", "فاصله", "آهنگ", "یاد", "برنگشت", "خاموش", "بغض", "گذشته", "آخرین",
    "ویرانه", "خسته", "فکر", "تنها", "ماه", "چراغ", "فراموش", "نبود",
}

# Visual terms that often indicate a generic/social-media aesthetic rather than the
# SilentRuins editorial identity. They are soft penalties, not absolute rejection.
OFF_BRAND_VISUAL_TERMS = {
    "bunny", "rabbit ears", "ears filter", "party", "festival", "celebration",
    "selfie", "influencer", "vacation", "beach party", "colorful party", "cute",
    "toy", "costume", "neon makeup", "fashion shoot",
}

HUMAN_CINEMATIC_TERMS = {
    "person", "woman", "man", "girl", "boy", "silhouette", "alone", "lonely",
    "window", "room", "street", "bench", "shadow", "face", "portrait", "figure",
}


# ---------------------------------------------------------------------------
# Mood selection
# ---------------------------------------------------------------------------

def _time_bucket(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def choose_mood(moods: dict, state: dict, local_hour: int | None = None) -> str:
    if local_hour is None:
        local_hour = datetime.now().hour
    bucket = _time_bucket(local_hour)
    recent = state.get("recent_moods", [])
    recent = recent if isinstance(recent, list) else []
    recent = recent[-4:]

    scored: list[tuple[str, float]] = []
    for mood in moods:
        profile = MOOD_PROFILES.get(mood, {})
        weight = float(profile.get("time_weights", {}).get(bucket, 1))
        if recent and mood == recent[-1]:
            weight *= 0.08
        elif mood in recent[-2:]:
            weight *= 0.35
        elif mood in recent:
            weight *= 0.65
        if bucket == "night" and mood in {"night", "lonely", "ruins"}:
            weight *= 1.35
        if weight > 0:
            scored.append((mood, weight))
    if not scored:
        return random.choice(list(moods))
    return random.choices([m for m, _ in scored], weights=[w for _, w in scored], k=1)[0]


# ---------------------------------------------------------------------------
# Semantic matching
# ---------------------------------------------------------------------------

def mood_similarity(text: str | None, mood: str, moods: dict, aliases: dict | None = None) -> float:
    text_n = normalize(text)
    if not text_n:
        return 0.0
    profile = MOOD_PROFILES.get(mood, {})
    concepts = {normalize(x) for x in profile.get("concepts", set())}
    alias_list = {normalize(x) for x in (aliases or {}).get(mood, [])}
    hits = _contains_any(text_n, {x for x in concepts | alias_list if x})
    query_text = " ".join(str(x) for x in moods.get(mood, {}).get("queries", []))
    token_overlap = len(tokens(text_n) & tokens(query_text))
    return min(1.0, hits * 0.18 + token_overlap * 0.06)


def track_match(track: dict | None, mood: str, moods: dict, aliases: dict | None = None) -> float:
    if not track:
        return 0.0
    tagged = normalize(track.get("mood"))
    title = normalize(track.get("title"))
    performer = normalize(track.get("performer"))
    combined = f"{title} {performer} {tagged}"

    if tagged == mood:
        return 1.0
    mapped = MUSIC_TAG_MAP.get(tagged, set())
    if mood in mapped:
        return 0.96

    profile = MOOD_PROFILES.get(mood, {})
    music_tags = {normalize(x) for x in profile.get("music_tags", set())}
    hits = _contains_any(combined, music_tags)
    alias_hits = _contains_any(combined, {normalize(x) for x in (aliases or {}).get(mood, [])})
    return min(0.82, 0.50 + hits * 0.09 + alias_hits * 0.10)


def caption_quality(caption: str, mood: str) -> float:
    text = normalize(caption)
    text = re.sub(r"—\s*silent\s+ruins.*$", "", text).strip()
    if not text:
        return 0.0

    score = 0.66
    words = tokens(text)
    char_len = len(text)
    sentence_count = max(1, len(re.findall(r"[.!؟!?]", text)))

    if 30 <= char_len <= 120:
        score += 0.10
    elif 20 <= char_len <= 145:
        score += 0.04
    elif char_len < 15 or char_len > 190:
        score -= 0.10

    if 5 <= len(words) <= 24:
        score += 0.07
    if sentence_count <= 2:
        score += 0.04
    if _contains_any(text, GOOD_CAPTION_HINTS):
        score += 0.06
    if _contains_any(text, BAD_CAPTION_PATTERNS):
        score -= 0.60
    if text.count("؟") >= 2 or text.count("#") > 0:
        score -= 0.08
    if re.search(r"[!]{2,}|[?]{2,}", text):
        score -= 0.08

    # A caption should contain at least one signal related to its assigned mood.
    profile = MOOD_PROFILES.get(mood, {})
    concepts = {normalize(x) for x in profile.get("concepts", set())}
    mood_hits = _contains_any(text, concepts)
    if mood_hits == 0:
        score -= 0.12
    elif mood_hits >= 2:
        score += 0.04

    return max(0.0, min(1.0, score))


def text_match(caption: str, mood: str, moods: dict, aliases: dict | None = None) -> float:
    copy = caption_quality(caption, mood)
    semantic = mood_similarity(caption, mood, moods, aliases)
    # No artificial 0.65 semantic floor. Weakly related captions must actually score lower.
    relevance = min(1.0, 0.48 + semantic * 0.58)
    return max(0.0, min(1.0, copy * 0.72 + relevance * 0.28))


def image_match(photo_meta: dict | None, mood: str, moods: dict, aliases: dict | None = None) -> float:
    if not photo_meta:
        return 0.42

    query = normalize(photo_meta.get("query", ""))
    alt = normalize(photo_meta.get("alt", ""))
    haystack = f"{query} {alt}"
    profile = MOOD_PROFILES.get(mood, {})
    visual_terms = {normalize(x) for x in profile.get("visual_terms", set())}
    visual_hits = _contains_any(haystack, visual_terms)
    semantic = mood_similarity(haystack, mood, moods, aliases)

    # Start neutral; reward explicit editorial intent instead of rewarding darkness alone.
    score = 0.52 + min(0.18, visual_hits * 0.045) + semantic * 0.16

    cinematic_hits = _contains_any(haystack, HUMAN_CINEMATIC_TERMS)
    if cinematic_hits:
        score += min(0.10, cinematic_hits * 0.025)

    off_brand_hits = _contains_any(haystack, OFF_BRAND_VISUAL_TERMS)
    if off_brand_hits:
        score -= min(0.22, off_brand_hits * 0.08)

    luminance = photo_meta.get("luminance")
    if isinstance(luminance, (int, float)):
        if 42 <= luminance <= 78:
            score += 0.07
        elif 30 <= luminance < 42 or 78 < luminance <= 105:
            score += 0.02
        elif luminance < 30:
            score -= 0.12
        elif luminance > 145:
            score -= 0.08

    return max(0.0, min(1.0, score))


def _coherence_score(text_score: float, image_score: float, music_score: float) -> float:
    """Reward balanced sets and punish one weak component hiding behind two strong ones."""
    values = [text_score, image_score, music_score]
    arithmetic = sum(values) / 3.0
    minimum = min(values)
    # Harmonic mean strongly penalizes a weak component while remaining smooth.
    if any(v <= 0 for v in values):
        harmonic = 0.0
    else:
        harmonic = 3.0 / sum(1.0 / v for v in values)
    return max(0.0, min(1.0, arithmetic * 0.45 + harmonic * 0.35 + minimum * 0.20))


def quality_score(
    mood: str,
    caption: str,
    track: dict | None,
    photo_meta: dict | None,
    moods: dict,
    aliases: dict | None = None,
) -> dict:
    """Return component scores plus an explicit editorial coherence score."""
    t = text_match(caption, mood, moods, aliases)
    i = image_match(photo_meta, mood, moods, aliases)
    m = track_match(track, mood, moods, aliases) if track else 0.30
    coherence = _coherence_score(t, i, m)

    # Emotional package weighting. Coherence has enough influence to prevent a pretty
    # image or famous song from rescuing a mismatched set.
    overall = (t * 0.30 + i * 0.20 + m * 0.30 + coherence * 0.20) * 100

    caption_q = caption_quality(caption, mood)
    if caption_q < 0.50:
        overall -= 12
    if m < 0.65:
        overall -= 6
    if i < 0.52:
        overall -= 5
    if coherence < 0.55:
        overall -= 7
    if min(t, i, m) < 0.45:
        overall -= 5

    overall = max(0, min(100, round(overall)))
    return {
        "text": round(t * 100),
        "image": round(i * 100),
        "music": round(m * 100),
        "coherence": round(coherence * 100),
        "overall": overall,
    }


# ---------------------------------------------------------------------------
# Anti-repetition / state helpers
# ---------------------------------------------------------------------------

def post_signature(mood: str, caption: str, track: dict | None, image_url: str | None) -> str:
    raw = "|".join([
        mood,
        normalize(caption),
        str((track or {}).get("file_id") or ""),
        str(image_url or ""),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def caption_signature(caption: str) -> str:
    return hashlib.sha256(normalize(caption).encode("utf-8")).hexdigest()


def remember_post(
    state: dict,
    mood: str,
    caption: str,
    track: dict | None,
    image_url: str | None,
    score: dict,
) -> dict:
    state = dict(state)

    recent = state.get("recent_post_signatures", [])
    recent = recent if isinstance(recent, list) else []
    recent.append(post_signature(mood, caption, track, image_url))
    state["recent_post_signatures"] = recent[-50:]

    recent_caps = state.get("recent_caption_signatures", [])
    recent_caps = recent_caps if isinstance(recent_caps, list) else []
    recent_caps.append(caption_signature(caption))
    state["recent_caption_signatures"] = recent_caps[-80:]

    recent_images = state.get("recent_image_urls", [])
    recent_images = recent_images if isinstance(recent_images, list) else []
    if image_url:
        recent_images.append(image_url)
    state["recent_image_urls"] = recent_images[-50:]

    recent_track_ids = state.get("recent_track_ids", [])
    recent_track_ids = recent_track_ids if isinstance(recent_track_ids, list) else []
    if track and track.get("file_id"):
        recent_track_ids.append(track.get("file_id"))
    state["recent_track_ids"] = recent_track_ids[-12:]

    recent_moods = state.get("recent_moods", [])
    recent_moods = recent_moods if isinstance(recent_moods, list) else []
    recent_moods.append(mood)
    state["recent_moods"] = recent_moods[-8:]
    state["last_quality_score"] = score
    return state


def is_duplicate(
    state: dict,
    mood: str,
    caption: str,
    track: dict | None,
    image_url: str | None,
) -> bool:
    if post_signature(mood, caption, track, image_url) in set(state.get("recent_post_signatures", []) or []):
        return True
    if caption_signature(caption) in set(state.get("recent_caption_signatures", []) or []):
        return True
    if track and track.get("file_id") in set(state.get("recent_track_ids", []) or []):
        return True
    if image_url and image_url in set(state.get("recent_image_urls", []) or []):
        return True
    return False
