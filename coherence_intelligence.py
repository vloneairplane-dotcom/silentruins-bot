"""SilentRuins Coherence Intelligence v1.1.

Coherence is the alignment of the three editorial assets. It uses the
already-established mood-aware caption, image, and soundtrack scorers as the
primary signal, then adds a small semantic bridge bonus when the caption,
scene, and soundtrack share concrete concepts.
"""
from __future__ import annotations

import re
import math
import content_engine as engine

MOOD_SIGNALS = {
    "rain": {"caption": {"باران", "پنجره", "خیس", "خیابان", "سکوت", "خاطره", "امشب", "صدا", "تنها"}},
    "night": {"caption": {"شب", "نیمه‌شب", "تاریکی", "چراغ", "شهر", "خاطره", "سکوت", "بیدار"}},
    "lonely": {"caption": {"تنهایی", "تنها", "نبودن", "کسی", "حضور", "سکوت", "صندلی", "خالی", "آدم"}},
    "love": {"caption": {"دلتنگی", "خاطره", "آدم", "فاصله", "دوست", "نبودن", "گذشته", "اسم", "رابطه", "برگشتن"}},
    "tired": {"caption": {"خستگی", "خسته", "سکوت", "ذهن", "فکر", "توان", "آرام", "حرف", "دوام", "تنها"}},
    "ruins": {"caption": {"ویرانه", "خرابه", "خاطره", "گذشته", "جای", "باقی", "رفته", "پایان", "خانه", "شکسته"}},
}

BRIDGES = {
    "rain": {"باران": {"rain"}, "پنجره": {"window"}, "خیابان": {"street"}, "خاطره": {"memories", "missing"}, "سکوت": {"melancholy", "night", "lonely"}},
    "night": {"شب": {"night", "dark"}, "نیمه‌شب": {"night", "midnight"}, "چراغ": {"city", "night"}, "شهر": {"city", "night"}, "خاطره": {"memories", "missing"}, "سکوت": {"dark", "melancholy"}},
    "lonely": {"تنهایی": {"lonely", "loneliness"}, "تنها": {"alone", "lonely"}, "نبودن": {"missing", "without you"}, "حضور": {"lonely", "missing"}, "خالی": {"empty", "lonely"}, "کسی": {"missing", "someone you loved"}},
    "love": {"دلتنگی": {"missing", "love", "heartbreak"}, "خاطره": {"memories", "missing"}, "فاصله": {"distance", "missing"}, "گذشته": {"memories", "love"}, "رابطه": {"breakup", "love"}},
    "tired": {"خستگی": {"tired", "exhausted", "breakdown"}, "خسته": {"tired", "exhausted"}, "ذهن": {"melancholy", "emotional", "tired"}, "فکر": {"melancholy", "night", "tired"}, "توان": {"tired", "breakdown"}, "سکوت": {"melancholy", "lonely"}},
    "ruins": {"ویرانه": {"ruins", "broken"}, "خرابه": {"ruins", "broken"}, "خاطره": {"memories", "ghost"}, "گذشته": {"memories", "faded"}, "پایان": {"gone", "goodbye"}, "شکسته": {"broken", "heartbreak"}},
}


def _norm(value) -> str:
    return engine.normalize(value)


def _tokens(value: str) -> set[str]:
    return {x for x in re.findall(r"[\wآ-ی]+", _norm(value)) if len(x) > 1}


def _asset_text(photo: dict | None) -> str:
    if not photo:
        return ""
    return _norm(" ".join(str(photo.get(k, "")) for k in ("url", "alt", "query", "description", "photographer")))


def _music_text(track: dict | None) -> str:
    if not track:
        return ""
    return _norm(" ".join(str(track.get(k, "")) for k in ("title", "performer", "mood")))


def _bridge_bonus(caption: str, mood: str, music_text: str, visual_text: str) -> float:
    hits = 0
    for word, targets in BRIDGES.get(mood, {}).items():
        if _norm(word) in _norm(caption) and any(_norm(target) in music_text or _norm(target) in visual_text for target in targets):
            hits += 1
    return min(0.06, hits * 0.02)


def _caption_fit(caption: str, mood: str) -> float:
    words = {_norm(x) for x in MOOD_SIGNALS.get(mood, {}).get("caption", set())}
    hits = len(_tokens(caption or "") & words)
    return min(1.0, 0.72 + hits * 0.05) if hits else 0.64


def smart_coherence(caption, mood, track=None, photo=None):
    """Return a stable 0..1 editorial alignment score.

    The harmonic mean deliberately penalizes a genuinely weak component, but
    does not collapse just because Pexels metadata lacks a matching keyword.
    """
    caption_fit = max(0.0, min(1.0, engine.caption_score(caption or "", mood)))
    image_fit = max(0.0, min(1.0, engine.image_score(photo, mood))) if photo else 0.55
    music_fit = max(0.0, min(1.0, engine.music_score(track, mood))) if track else 0.55

    # Caption scorer is already semantic, but a tiny vocabulary check gives
    # coherence a scene-specific signal without double-counting sentiment.
    scene_fit = _caption_fit(caption or "", mood)
    harmonic = 3.0 / (
        (1.0 / max(caption_fit, 0.05))
        + (1.0 / max(image_fit, 0.05))
        + (1.0 / max(music_fit, 0.05))
    )

    bridge = _bridge_bonus(caption or "", mood, _music_text(track), _asset_text(photo))
    score = harmonic * 0.82 + scene_fit * 0.12 + bridge

    if not track or not photo:
        score = min(score, 0.76)
    return round(max(0.0, min(1.0, score)), 3)


engine.coherence = smart_coherence


def apply(bot_module=None):
    engine.coherence = smart_coherence
    return bot_module
