"""SilentRuins Coherence Intelligence v1.

Scores the post as one editorial scene instead of treating caption, image,
and soundtrack as independent assets.

The module is intentionally a narrow runtime patch: it replaces only the
content engine's coherence scorer and leaves mood rotation, publishing,
quality weights, and library state untouched.
"""
from __future__ import annotations

import re
import content_engine as engine

# Editorial vocabulary shared by the six production moods.
MOOD_SIGNALS = {
    "rain": {
        "caption": {"باران", "پنجره", "خیس", "خیابان", "سکوت", "خاطره", "امشب", "صدا", "تنها"},
        "visual": {"rain", "rainy", "window", "wet", "street", "umbrella", "reflection", "storm"},
        "music": {"rain", "melancholy", "missing", "memories", "emotional", "night", "lonely"},
    },
    "night": {
        "caption": {"شب", "نیمه‌شب", "تاریکی", "چراغ", "شهر", "خاطره", "سکوت", "بیدار"},
        "visual": {"night", "moon", "dark", "city", "silhouette", "neon", "street", "midnight"},
        "music": {"night", "dark", "melancholy", "loneliness", "emotional", "memories", "tired"},
    },
    "lonely": {
        "caption": {"تنهایی", "تنها", "نبودن", "کسی", "حضور", "سکوت", "صندلی", "خالی", "آدم"},
        "visual": {"alone", "lonely", "silhouette", "empty", "bench", "room", "window", "distance"},
        "music": {"loneliness", "lonely", "missing", "emotional", "dark", "memories", "night"},
    },
    "love": {
        "caption": {"دلتنگی", "خاطره", "آدم", "فاصله", "دوست", "نبودن", "گذشته", "اسم", "رابطه", "برگشتن"},
        "visual": {"rose", "letter", "photograph", "distance", "empty", "bed", "goodbye", "memory", "heartbreak"},
        "music": {"heartbreak", "missing", "breakup", "regret", "romantic", "unrequited", "betrayal", "emotional", "memories"},
    },
    "tired": {
        "caption": {"خستگی", "خسته", "سکوت", "ذهن", "فکر", "توان", "آرام", "حرف", "دوام", "تنها"},
        "visual": {"tired", "eyes", "head", "candle", "hood", "exhausted", "smoke", "dark", "room"},
        "music": {"breakdown", "depression", "emotional", "loneliness", "melancholy", "regret", "tired", "numb"},
    },
    "ruins": {
        "caption": {"ویرانه", "خرابه", "خاطره", "گذشته", "جای", "باقی", "رفته", "پایان", "خانه", "شکسته"},
        "visual": {"ruins", "broken", "ashes", "ghost", "memory", "memories", "lost", "empty", "faded", "gone"},
        "music": {"melancholy", "dark", "memories", "depression", "night", "emotional", "sadness", "loneliness", "missing"},
    },
}

# Stronger phrase-level bridges prevent generic words such as "شب" from
# dominating every comparison.
BRIDGES = {
    "rain": {
        "باران": {"rain"}, "پنجره": {"window"}, "خیابان": {"street"},
        "خاطره": {"memories", "missing"}, "سکوت": {"melancholy", "night", "lonely"},
    },
    "night": {
        "شب": {"night", "dark"}, "نیمه‌شب": {"night", "midnight"}, "چراغ": {"city", "night"},
        "شهر": {"city", "night"}, "خاطره": {"memories", "missing"}, "سکوت": {"dark", "melancholy"},
    },
    "lonely": {
        "تنهایی": {"lonely", "loneliness"}, "تنها": {"alone", "lonely"}, "نبودن": {"missing", "without you"},
        "حضور": {"lonely", "missing"}, "خالی": {"empty", "lonely"}, "کسی": {"someone you loved", "missing"},
    },
    "love": {
        "دلتنگی": {"missing", "love", "heartbreak"}, "خاطره": {"memories", "missing"},
        "فاصله": {"distance", "missing"}, "گذشته": {"memories", "love"}, "رابطه": {"breakup", "love"},
    },
    "tired": {
        "خستگی": {"tired", "exhausted", "breakdown"}, "خسته": {"tired", "exhausted"},
        "ذهن": {"melancholy", "emotional", "tired"}, "فکر": {"melancholy", "night", "tired"},
        "توان": {"tired", "breakdown"}, "سکوت": {"melancholy", "lonely"},
    },
    "ruins": {
        "ویرانه": {"ruins", "broken"}, "خرابه": {"ruins", "broken"}, "خاطره": {"memories", "ghost"},
        "گذشته": {"memories", "faded"}, "پایان": {"gone", "goodbye"}, "شکسته": {"broken", "heartbreak"},
    },
}


def _norm(value) -> str:
    return engine.normalize(value)


def _tokens(value: str) -> set[str]:
    text = _norm(value)
    return {x for x in re.findall(r"[\wآ-ی]+", text) if len(x) > 1}


def _asset_text(photo: dict | None) -> str:
    if not photo:
        return ""
    return _norm(" ".join(str(photo.get(k, "")) for k in ("url", "alt", "query", "description", "photographer")))


def _music_text(track: dict | None) -> str:
    if not track:
        return ""
    return _norm(" ".join(str(track.get(k, "")) for k in ("title", "performer", "mood")))


def _caption_bridge(caption: str, mood: str, music_text: str, visual_text: str) -> float:
    bridges = BRIDGES.get(mood, {})
    hits = 0
    for fa_word, targets in bridges.items():
        if _norm(fa_word) in _norm(caption) and any(_norm(target) in music_text or _norm(target) in visual_text for target in targets):
            hits += 1
    return min(1.0, 0.60 + hits * 0.10) if hits else 0.0


def smart_coherence(caption, mood, track=None, photo=None):
    """Return a calibrated 0..1 editorial coherence score."""
    info = MOOD_SIGNALS.get(mood, {})
    cap = _tokens(caption or "")
    music_text = _music_text(track)
    visual_text = _asset_text(photo)

    # Caption-to-mood: use exact Persian editorial vocabulary, not generic
    # sentiment words. This rewards a scene that actually belongs to the mood.
    cap_hits = len(cap & {_norm(x) for x in info.get("caption", set())})
    caption_scene = min(1.0, 0.55 + cap_hits * 0.07) if cap_hits else 0.48

    # Asset semantic fit. URLs and Pexels alt/query text carry scene clues.
    visual_hits = sum(1 for x in info.get("visual", set()) if _norm(x) in visual_text)
    music_hits = sum(1 for x in info.get("music", set()) if _norm(x) in music_text)
    visual_fit = min(1.0, 0.58 + visual_hits * 0.06) if visual_hits else 0.50
    music_fit = min(1.0, 0.60 + music_hits * 0.06) if music_hits else 0.50

    # Direct bridges are stronger than merely sharing the same mood label.
    bridge = _caption_bridge(caption or "", mood, music_text, visual_text)

    # Cross-asset agreement: the same scene vocabulary should appear in at
    # least two assets. This is what distinguishes a coherent post from three
    # individually acceptable assets.
    scene_terms = {_norm(x) for x in info.get("visual", set()) | info.get("music", set())}
    visual_scene = {x for x in scene_terms if x in visual_text}
    music_scene = {x for x in scene_terms if x in music_text}
    cross = min(1.0, 0.55 + len(visual_scene & music_scene) * 0.08) if visual_scene or music_scene else 0.48

    score = (
        caption_scene * 0.28
        + visual_fit * 0.20
        + music_fit * 0.22
        + bridge * 0.15
        + cross * 0.15
    )

    # Keep the scorer conservative when metadata is sparse; never manufacture
    # a 90+ coherence score from a single weak signal.
    if not track or not photo:
        score = min(score, 0.76)
    return round(max(0.0, min(1.0, score)), 3)


engine.coherence = smart_coherence


def apply(bot_module=None):
    """Patch the shared content engine. Returns the optional bot module."""
    engine.coherence = smart_coherence
    return bot_module
