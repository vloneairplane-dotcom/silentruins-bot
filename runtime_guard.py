"""SilentRuins Owner Mode runtime hardening.

Production safety layer for the legacy bot while the fixes are gradually folded
back into bot.py. It patches only the music selector, audio accounting, and
Pexels dark-image picker before executing the original bot.
"""
from __future__ import annotations

import random
from pathlib import Path

GUARD_VERSION = "4.1.0-owner-guard"


def _patch_source(source: str) -> str:
    # ------------------------------------------------------------------
    # Music selector: total function + preview diversity.
    # ------------------------------------------------------------------
    start = source.index("def get_next_track(mood=None, peek=False):")
    end = source.index("\n\ndef consume_track(track):", start)
    replacement = '''def get_next_track(mood=None, peek=False):
    """Select music safely with cooldowns and preview isolation."""
    lib = load_library()
    tracks = [t for t in lib.get("tracks", []) if t and t.get("file_id")]
    if not tracks:
        return None

    state = load_state()
    recent_ids = [x for x in (state.get("recent_track_ids", []) or []) if x]
    cooldown_ids = set(recent_ids[-MUSIC_COOLDOWN_POSTS:])
    by_id = {t["file_id"]: t for t in tracks}

    if peek:
        preview_recent = [x for x in (state.get("preview_recent_track_ids", []) or []) if x]
        # Do not reuse a track that appeared in recent previews unless the
        # whole library has been exhausted.
        preview_excluded = set(preview_recent[-max(10, MAX_CANDIDATES):])
        pool = [
            t for t in tracks
            if t["file_id"] not in cooldown_ids
            and t["file_id"] not in preview_excluded
        ]
        if not pool:
            pool = [t for t in tracks if t["file_id"] not in cooldown_ids]
        if not pool:
            pool = tracks[:]
        if not pool:
            return None

        if mood:
            ranked = sorted(
                pool,
                key=lambda t: track_match(t, mood, MOODS, MOOD_ALIASES),
                reverse=True,
            )
            # Keep the strongest semantic matches, but rotate among them.
            if ranked:
                scores = [track_match(t, mood, MOODS, MOOD_ALIASES) for t in ranked]
                top_score = scores[0]
                threshold = max(0.70, top_score - 0.10)
                shortlist = [
                    t for t, s in zip(ranked, scores)
                    if s >= threshold
                ]
                if not shortlist:
                    shortlist = ranked[: min(5, len(ranked))]
            else:
                shortlist = pool
        else:
            shortlist = pool

        if not shortlist:
            return None
        chosen = random.choice(shortlist[: min(5, len(shortlist))])
        preview_recent.append(chosen["file_id"])
        save_state({"preview_recent_track_ids": preview_recent[-max(10, MAX_CANDIDATES):]})
        return chosen

    lib["unplayed"] = [
        fid for fid in (lib.get("unplayed", []) or []) if fid in by_id
    ]
    if not lib["unplayed"]:
        eligible = [t for t in tracks if t["file_id"] not in cooldown_ids]
        if not eligible:
            eligible = tracks[:]
        lib["unplayed"] = [t["file_id"] for t in eligible]
        random.shuffle(lib["unplayed"])

    chosen_id = None
    if mood:
        ranked_ids = sorted(
            lib["unplayed"],
            key=lambda fid: track_match(by_id[fid], mood, MOODS, MOOD_ALIASES),
            reverse=True,
        )
        for fid in ranked_ids:
            if fid not in cooldown_ids:
                chosen_id = fid
                break

    if chosen_id is None:
        for fid in lib["unplayed"]:
            if fid not in cooldown_ids:
                chosen_id = fid
                break

    # Absolute fallback: never index or choose from an empty sequence.
    if chosen_id is None and lib["unplayed"]:
        chosen_id = lib["unplayed"][0]
    if chosen_id is None:
        return None

    lib["unplayed"].remove(chosen_id)
    save_library(lib)
    return by_id.get(chosen_id)
'''
    source = source[:start] + replacement + source[end:]

    # ------------------------------------------------------------------
    # Audio accounting: count a play only after Telegram accepts it.
    # ------------------------------------------------------------------
    start = source.index("async def send_track(context, chat_id, track, reply_to=None):")
    end = source.index("\n\ndef delete_track_by_number", start)
    replacement = '''async def send_track(context, chat_id, track, reply_to=None):
    """Send audio first; only then count the track as played."""
    if not track:
        return None
    caption = build_audio_caption(track)
    file_path = track.get("file_path")
    if file_path and Path(file_path).exists():
        with open(file_path, "rb") as f:
            message = await context.bot.send_audio(
                chat_id=chat_id,
                audio=f,
                caption=caption,
                title=(track.get("title") or None),
                performer=(track.get("performer") or None),
                reply_to_message_id=reply_to,
            )
    else:
        message = await context.bot.send_audio(
            chat_id=chat_id,
            audio=track["file_id"],
            caption=caption,
            reply_to_message_id=reply_to,
        )
    try:
        DB.track_played(track.get("file_id"))
    except Exception:
        logger.exception("Failed to record track play")
    return message
'''
    source = source[:start] + replacement + source[end:]

    # ------------------------------------------------------------------
    # Image picker: keep the cinematic dark look without selecting images
    # that are effectively black/indistinguishable.
    # ------------------------------------------------------------------
    start = source.index("def _pick_dark_photo(photos, excluded_urls=None):")
    end = source.index("\n\ndef fetch_pexels_photo", start)
    replacement = '''def _pick_dark_photo(photos, excluded_urls=None):
    """Pick a dark cinematic image, but reject near-black unusable results."""
    excluded_urls = set(excluded_urls or [])
    fresh = [
        p for p in photos
        if p.get("src", {}).get("large2x") not in excluded_urls
        and p.get("src", {}).get("large") not in excluded_urls
        and p.get("src", {}).get("original") not in excluded_urls
    ]
    if fresh:
        photos = fresh

    scored = []
    for photo in photos:
        lum = _luminance(photo.get("avg_color") or "#808080")
        width = float(photo.get("width") or 0)
        height = float(photo.get("height") or 0)
        resolution = min(1.0, (width * height) / 12000000.0) if width and height else 0.0

        # Target a dark-but-readable luminance around 55-75. Penalize images
        # below 30 because Telegram previews become almost black.
        readability = 1.0 - min(1.0, abs(lum - 62.0) / 62.0)
        if lum < 30:
            readability *= 0.15
        elif lum < 38:
            readability *= 0.45
        elif lum > 125:
            readability *= 0.55

        score = readability * 0.82 + resolution * 0.18
        scored.append((score, lum, photo))

    if not scored:
        return None

    scored.sort(key=lambda item: item[0], reverse=True)
    # Rotate through the best few rather than repeatedly returning the same image.
    top = scored[: min(8, len(scored))]
    return random.choice(top)[2]
'''
    source = source[:start] + replacement + source[end:]

    return source


def main() -> None:
    source = Path("bot.py").read_text(encoding="utf-8")
    patched = _patch_source(source)
    compile(patched, "bot.py (Owner Mode patched)", "exec")

    ns = {
        "__name__": "__main__",
        "__file__": str(Path("bot.py").resolve()),
        "__package__": None,
    }
    exec(compile(patched, "bot.py (Owner Mode patched)", "exec"), ns, ns)


if __name__ == "__main__":
    main()
