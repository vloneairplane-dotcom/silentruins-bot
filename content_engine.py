"""SilentRuins content intelligence: mood selection, matching, anti-repeat and quality scoring."""
from __future__ import annotations

import hashlib
import random
import re
from datetime import datetime
from typing import Iterable


def normalize(text: str | None) -> str:
    text = (text or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokens(text: str | None) -> set[str]:
    return {t for t in re.findall(r"[\w\u0600-\u06ff-]+", normalize(text)) if len(t) >= 2}


def choose_mood(moods: dict, state: dict, local_hour: int | None = None) -> str:
    """Choose a mood using time windows + recent-mood cooldown, not pure random."""
    if local_hour is None:
        local_hour = datetime.now().hour
    recent = state.get("recent_moods", [])
    if not isinstance(recent, list):
        recent = []
    recent = recent[-4:]

    windows = {
        # Strong time-of-day identity. Secondary moods retain some variety.
        "rain": set(range(7, 12)),
        "tired": set(range(12, 17)),
        "love": set(range(17, 21)),
        "lonely": set(range(20, 24)),
        "night": set(list(range(0, 6)) + list(range(21, 24))),
        "ruins": set(list(range(0, 4)) + list(range(16, 20))),
    }
    candidates = [m for m in moods if m not in recent]
    if not candidates:
        candidates = list(moods)

    weighted: list[tuple[str, int]] = []
    for mood in candidates:
        weight = 1
        if local_hour in windows.get(mood, set()):
            weight += 10
        if recent and recent[-1] == mood:
            weight = 0
        weighted.append((mood, weight))
    choices, weights = zip(*[(m, w) for m, w in weighted if w > 0])
    return random.choices(list(choices), weights=list(weights), k=1)[0]


def mood_similarity(text: str | None, mood: str, moods: dict, aliases: dict) -> float:
    text_n = normalize(text)
    if not text_n:
        return 0.0
    alias_hits = sum(1 for a in aliases.get(mood, []) if a.lower() in text_n)
    mood_terms = tokens(" ".join(moods[mood].get("queries", [])))
    text_terms = tokens(text)
    overlap = len(text_terms & mood_terms)
    # Alias matches are stronger than generic query-token overlap.
    score = min(1.0, alias_hits * 0.45 + overlap * 0.08)
    return score


def track_match(track: dict | None, mood: str, moods: dict, aliases: dict) -> float:
    if not track:
        return 0.0
    tagged = normalize(track.get("mood"))
    canonical_aliases = {normalize(a) for a in aliases.get(mood, [])}
    if tagged == normalize(mood) or tagged in canonical_aliases:
        return 1.0
    # Common natural-language variants used in the music library.
    variants = {
        "lonely": {"loneliness"},
        "love": {"heartbreak", "missing", "regret", "romantic", "unrequited love"},
        "rain": {"rainy"},
        "tired": {"exhausted", "breakdown"},
        "ruins": {"melancholy", "dark"},
        "night": {"dark night"},
    }
    if tagged in variants.get(mood, set()):
        return 0.95
    text = f"{track.get('title', '')} {track.get('performer', '')} {track.get('mood', '')}"
    sim = mood_similarity(text, mood, moods, aliases)
    return min(0.75, sim)


def text_match(caption: str, mood: str, moods: dict, aliases: dict) -> float:
    sim = mood_similarity(caption, mood, moods, aliases)
    # Captions are explicitly sourced from the mood pool; baseline is high.
    return max(0.78, min(1.0, 0.82 + sim * 0.18))


def image_match(photo_meta: dict | None, mood: str, moods: dict, aliases: dict) -> float:
    if not photo_meta:
        return 0.72
    haystack = f"{photo_meta.get('query','')} {photo_meta.get('alt','')}"
    sim = mood_similarity(haystack, mood, moods, aliases)
    luminance = photo_meta.get("luminance")
    dark_bonus = 0.08 if isinstance(luminance, (int, float)) and luminance < 65 else 0.0
    return max(0.65, min(1.0, 0.78 + sim * 0.15 + dark_bonus))


def quality_score(mood: str, caption: str, track: dict | None, photo_meta: dict | None, moods: dict, aliases: dict) -> dict:
    t = text_match(caption, mood, moods, aliases)
    i = image_match(photo_meta, mood, moods, aliases)
    m = track_match(track, mood, moods, aliases) if track else 0.45
    # Music is the strongest semantic signal for this bot.
    overall = round((t * 0.34 + i * 0.26 + m * 0.40) * 100)
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
    if not isinstance(recent, list):
        recent = []
    recent.append(post_signature(mood, caption, track, image_url))
    state["recent_post_signatures"] = recent[-40:]

    recent_caps = state.get("recent_caption_signatures", [])
    if not isinstance(recent_caps, list):
        recent_caps = []
    recent_caps.append(caption_signature(caption))
    state["recent_caption_signatures"] = recent_caps[-60:]

    recent_images = state.get("recent_image_urls", [])
    if not isinstance(recent_images, list):
        recent_images = []
    if image_url:
        recent_images.append(image_url)
    state["recent_image_urls"] = recent_images[-40:]

    recent_moods = state.get("recent_moods", [])
    if not isinstance(recent_moods, list):
        recent_moods = []
    recent_moods.append(mood)
    state["recent_moods"] = recent_moods[-6:]
    state["last_quality_score"] = score
    return state


def is_duplicate(state: dict, mood: str, caption: str, track: dict | None, image_url: str | None) -> bool:
    sig = post_signature(mood, caption, track, image_url)
    if sig in set(state.get("recent_post_signatures", []) or []):
        return True
    if caption_signature(caption) in set(state.get("recent_caption_signatures", []) or []):
        return True
    if image_url and image_url in set(state.get("recent_image_urls", []) or []):
        return True
    return False
