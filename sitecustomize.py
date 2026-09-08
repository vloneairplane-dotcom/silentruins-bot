"""SilentRuins process-wide safety net.

Python imports sitecustomize automatically when this repository is on sys.path.
This protects deployments that still start bot.py directly instead of using
runtime_guard.py. The normal random.choice behavior is unchanged for non-empty
sequences. If the legacy music selector reaches random.choice([]), recover a
music track from the caller's live library instead of crashing the preview.
"""
from __future__ import annotations

import inspect
import random as _random


_original_choice = _random.choice


def _safe_choice(seq):
    if seq:
        return _original_choice(seq)

    frame = inspect.currentframe()
    caller = frame.f_back if frame else None
    try:
        if caller and caller.f_code.co_name == "get_next_track":
            load_library = caller.f_globals.get("load_library")
            track_match = caller.f_globals.get("track_match")
            moods = caller.f_globals.get("MOODS")
            aliases = caller.f_globals.get("MOOD_ALIASES")
            mood = caller.f_locals.get("mood")
            if callable(load_library):
                tracks = [
                    t for t in (load_library().get("tracks", []) or [])
                    if t and t.get("file_id")
                ]
                if tracks:
                    if mood and callable(track_match):
                        ranked = sorted(
                            tracks,
                            key=lambda t: track_match(t, mood, moods, aliases),
                            reverse=True,
                        )
                        return ranked[0]
                    return tracks[0]
    finally:
        del caller
        del frame

    # The caller has no meaningful fallback. Returning None is safer than
    # raising "Cannot choose from an empty sequence" and lets the bot's normal
    # no-music path handle the situation.
    return None


_random.choice = _safe_choice
