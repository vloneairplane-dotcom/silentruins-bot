"""SilentRuins V3.2 content intelligence.

The engine treats every post as a coherent editorial package:
    mood + caption + image + music

V3.2 adds:
- deterministic time-of-day mood priorities
- semantic music taxonomy (e.g. Heartbreak -> love)
- caption quality heuristics for Persian copy
- image intent scoring instead of only darkness
- weighted quality score with hard penalties for weak combinations
- stronger anti-repetition helpers
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
    return sum(1 for phrase in phrases if phrase in text)


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

# Music Library uses many finer-grained labels. Map them into the six editorial moods.
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

# Captions that should never survive editorial scoring. They read as typos, memes,
# political/off-topic copy, or machine-generated filler for this brand.
BAD_CAPTION_PATTERNS = {
    "رورو", "بدترین قراره", "یه بارونی بزن", "لاله‌های وطن", "پاییز مواظب گلا نیست",
    "خواب برای اوناست که دار می‌شن", "تو جمع پر بحث", "سفره‌ی تک‌نفره", "حساب من",
    "کی قراره حالتو بپرسه", "توی خونه غرقیم",
}

# Short, clean Persian phrases that are strong enough to use as a quality baseline.
GOOD_CAPTION_HINTS = {
    "شب", "سکوت", "تنهایی", "خاطره", "دلتنگ", "رفتن", "ماندن", "نبودن", "باران",
    "پنجره", "فاصله", "آهنگ", "یاد", "برنگشت", "خاموش", "بغض", "گذشته", "آخرین",
    "ویرانه", "خسته", "فکر", "تنها", "ماه", "چراغ",
}


def _time_bucket(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def choose_mood(moods: dict, state: dict, local_hour: int | None = None) -> str:
    """Choose mood from editorial time priorities + cooldown, with controlled variety."""
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
        # Strongly discourage the immediate repeat and moderately discourage recent repeats.
        if recent and mood == recent[-1]:
            weight *= 0.08
        elif mood in recent[-2:]:
            weight *= 0.35
        elif mood in recent:
            weight *= 0.65
        # Midnight identity: Night/Lonely/Ruins dominate, but not deterministically.
        if bucket == "night" and mood in {"night", "lonely", "ruins"}:
            weight *= 1.35
        if weight > 0:
            scored.append((mood, weight))
    if not scored:
        return random.choice(list(moods))
    return random.choices([m for m, _ in scored], weights=[w for _, w in scored], k=1)[0]


def mood_similarity(text: str | None, mood: str, moods: dict, aliases: dict | None = None) -> float:
    """Semantic similarity between free text and a mood profile, 0..1."""
    text_n = normalize(text)
    if not text_n:
        return 0.0
    profile = MOOD_PROFILES.get(mood, {})
    concepts = {normalize(x) for x in profile.get("concepts", set())}
    alias_list = {normalize(x) for x in (aliases or {}).get(mood, [])}
    hits = _contains_any(text_n, {x for x in concepts | alias_list if x})
    token_overlap = len(tokens(text_n) & tokens(" ".join(str(x) for x in moods.get(mood, {}).get("queries", []))))
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
        # Exact library taxonomy match gets the strongest score.
        return 0.96

    # Title/artist can still provide a weak semantic signal when the mood field is imperfect.
    profile = MOOD_PROFILES.get(mood, {})
    music_tags = {normalize(x) for x in profile.get("music_tags", set())}
    hits = _contains_any(combined, music_tags)
    alias_hits = _contains_any(combined, {normalize(x) for x in (aliases or {}).get(mood, [])})
    return min(0.82, 0.58 + hits * 0.10 + alias_hits * 0.10)


def caption_quality(caption: str, mood: str) -> float:
    """Editorial quality of the actual caption copy, independent of mood matching."""
    text = normalize(caption)
    # Remove signature/emoji before judging copy.
    text = re.sub(r"—\s*silent\s+ruins.*$", "", text).strip()
    if not text:
        return 0.0

    score = 0.72
    words = tokens(text)
    char_len = len(text)
    sentence_count = max(1, len(re.findall(r"[.!؟!?]", text)))

    if 25 <= char_len <= 125:
        score += 0.08
    elif char_len > 180:
        score -= 0.10
    if 5 <= len(words) <= 24:
        score += 0.06
    if sentence_count <= 2:
        score += 0.04
    if _contains_any(text, GOOD_CAPTION_HINTS):
        score += 0.05
    if _contains_any(text, BAD_CAPTION_PATTERNS):
        score -= 0.55
    # Avoid noisy question-heavy or hashtag-like copy.
    if text.count("؟") >= 2 or text.count("#") > 0:
        score -= 0.08
    if re.search(r"[!]{2,}|[?]{2,}", text):
        score -= 0.08
    return max(0.0, min(1.0, score))


def text_match(caption: str, mood: str, moods: dict, aliases: dict | None = None) -> float:
    semantic = mood_similarity(caption, mood, moods, aliases)
    copy = caption_quality(caption, mood)
    # Copy quality matters more than token overlap because the caption pool is curated.
    return max(0.0, min(1.0, copy * 0.72 + max(0.65, semantic) * 0.28))


def image_match(photo_meta: dict | None, mood: str, moods: dict, aliases: dict | None = None) -> float:
    if not photo_meta:
        return 0.50
    query = normalize(photo_meta.get("query", ""))
    alt = normalize(photo_meta.get("alt", ""))
    haystack = f"{query} {alt}"
    profile = MOOD_PROFILES.get(mood, {})
    visual_terms = {normalize(x) for x in profile.get("visual_terms", set())}
    visual_hits = _contains_any(haystack, visual_terms)
    semantic = mood_similarity(haystack, mood, moods, aliases)
    luminance = photo_meta.get("luminance")
    score = 0.62 + visual_hits * 0.055 + semantic * 0.16
    if isinstance(luminance, (int, float)):
        if luminance < 45:
            score += 0.09
        elif luminance < 70:
            score += 0.06
        elif luminance > 150:
            score -= 0.10
    return max(0.0, min(1.0, score))


def quality_score(mood: str, caption: str, track: dict | None, photo_meta: dict | None, moods: dict, aliases: dict | None = None) -> dict:
    t = text_match(caption, mood, moods, aliases)
    i = image_match(photo_meta, mood, moods, aliases)
    m = track_match(track, mood, moods, aliases) if track else 0.35

    # Brand priority: copy + music are the emotional core; visual coherence follows.
    overall = (t * 0.38 + i * 0.25 + m * 0.37) * 100

    # Hard editorial penalties. A pretty image cannot rescue an obviously weak caption.
    if caption_quality(caption, mood) < 0.50:
        overall -= 12
    if track and m < 0.65:
        overall -= 7
    if photo_meta and i < 0.60:
        overall -= 5

    overall = max(0, min(100, round(overall)))
    return {
        "text": round(t * 100),
        "image": round(i * 100),
        "music": round(m * 100),
        "overall": overall,
    }


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


def remember_post(state: dict, mood: str, caption: str, track: dict | None, image_url: str | None, score: dict) -> dict:
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


def is_duplicate(state: dict, mood: str, caption: str, track: dict | None, image_url: str | None) -> bool:
    if post_signature(mood, caption, track, image_url) in set(state.get("recent_post_signatures", []) or []):
        return True
    if caption_signature(caption) in set(state.get("recent_caption_signatures", []) or []):
        return True
    if track and track.get("file_id") in set(state.get("recent_track_ids", []) or []):
        return True
    if image_url and image_url in set(state.get("recent_image_urls", []) or []):
        return True
    return False
