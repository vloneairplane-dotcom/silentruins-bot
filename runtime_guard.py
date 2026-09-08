"""SilentRuins Owner Mode runtime hardening.

The current bot.py is executed as-is except for two surgical runtime repairs:
- music selection has a hard fallback so an empty shortlist can never reach
  random.choice();
- audio play analytics are written only after Telegram accepts the audio.

This wrapper lets us stabilize production behavior without rewriting the large
legacy bot file in one risky operation. The fixes can later be folded into
bot.py after the regression suite is expanded.
"""
from __future__ import annotations

import random
import runpy
from pathlib import Path


GUARD_VERSION = "4.0.1-owner-guard"


def _patch_source(source: str) -> str:
    start = source.index("def get_next_track(mood=None, peek=False):")
    end = source.index("\n\ndef consume_track(track):", start)
    replacement = '''def get_next_track(mood=None, peek=False):
    """Select music safely; this function has a total fallback for every state."""
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
        preview_excluded = set(preview_recent[-MAX_CANDIDATES:])
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
            if ranked:
                top_score = track_match(ranked[0], mood, MOODS, MOOD_ALIASES)
                threshold = max(0.70, top_score - 0.08)
                shortlist = [
                    t for t in ranked
                    if track_match(t, mood, MOODS, MOOD_ALIASES) >= threshold
                ]
                if not shortlist:
                    shortlist = ranked[: min(5, len(ranked))]
            else:
                shortlist = pool
        else:
            shortlist = pool

        if not shortlist:
            return None
        chosen = random.choice(shortlist)
        preview_recent.append(chosen["file_id"])
        save_state({"preview_recent_track_ids": preview_recent[-MAX_CANDIDATES:]})
        return chosen

    lib["unplayed"] = [fid for fid in (lib.get("unplayed", []) or []) if fid in by_id]
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

    if chosen_id is None and lib["unplayed"]:
        chosen_id = lib["unplayed"][0]
    if chosen_id is None:
        return None

    lib["unplayed"].remove(chosen_id)
    save_library(lib)
    return by_id.get(chosen_id)
'''
    source = source[:start] + replacement + source[end:]

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
    return source[:start] + replacement + source[end:]


def main() -> None:
    source = Path("bot.py").read_text(encoding="utf-8")
    patched = _patch_source(source)
    compile(patched, "bot.py (Owner Mode patched)", "exec")

    # Execute the repaired source as __main__, preserving the original startup
    # behavior and avoiding assumptions about the bot's entry-point function.
    ns = {
        "__name__": "__main__",
        "__file__": str(Path("bot.py").resolve()),
        "__package__": None,
    }
    exec(compile(patched, "bot.py (Owner Mode patched)", "exec"), ns, ns)


if __name__ == "__main__":
    main()
