"""SilentRuins Owner Mode runtime hardening.

This launcher wraps the current bot without changing the content data. It patches
only two high-risk runtime paths before starting the original application:
1) music candidate selection can never call random.choice([]),
2) audio analytics are recorded only after Telegram accepts the audio.

It is intentionally isolated so the underlying bot can later absorb these fixes
into bot.py once the production architecture is stable.
"""
from __future__ import annotations

import asyncio
import random
import runpy
from pathlib import Path


BRANCH_GUARD_VERSION = "4.0.0-owner-guard"


def _install_patches(ns: dict) -> None:
    load_library = ns["load_library"]
    save_library = ns["save_library"]
    load_state = ns["load_state"]
    save_state = ns["save_state"]
    track_match = ns["track_match"]
    moods = ns["MOODS"]
    aliases = ns.get("MOOD_ALIASES", {})
    max_candidates = max(5, int(ns.get("MAX_CANDIDATES", 10)))
    cooldown_posts = max(1, int(ns.get("MUSIC_COOLDOWN_POSTS", 8)))

    def safe_get_next_track(mood=None, peek=False):
        lib = load_library()
        tracks = [t for t in lib.get("tracks", []) if t and t.get("file_id")]
        if not tracks:
            return None

        state = load_state()
        recent_ids = [x for x in (state.get("recent_track_ids", []) or []) if x]
        cooldown_ids = set(recent_ids[-cooldown_posts:])
        by_id = {t["file_id"]: t for t in tracks}

        if peek:
            preview_recent = [x for x in (state.get("preview_recent_track_ids", []) or []) if x]
            preview_excluded = set(preview_recent[-max_candidates:])
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
                    key=lambda t: track_match(t, mood, moods, aliases),
                    reverse=True,
                )
                top_score = track_match(ranked[0], mood, moods, aliases)
                threshold = max(0.70, top_score - 0.08)
                shortlist = [
                    t for t in ranked
                    if track_match(t, mood, moods, aliases) >= threshold
                ]
                if not shortlist:
                    shortlist = ranked[: min(5, len(ranked))]
            else:
                shortlist = pool

            # The guard invariant: random.choice is never called on an empty list.
            if not shortlist:
                return None
            chosen = random.choice(shortlist)
            preview_recent.append(chosen["file_id"])
            save_state({"preview_recent_track_ids": preview_recent[-max_candidates:]})
            return chosen

        valid_unplayed = [
            fid for fid in (lib.get("unplayed", []) or [])
            if fid in by_id
        ]
        lib["unplayed"] = valid_unplayed

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
                key=lambda fid: track_match(by_id[fid], mood, moods, aliases),
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

    ns["get_next_track"] = safe_get_next_track

    async def safe_send_track(context, chat_id, track, reply_to=None):
        if not track:
            return None
        caption = ns["build_audio_caption"](track)
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
            ns["DB"].track_played(track.get("file_id"))
        except Exception:
            ns["logger"].exception("Owner guard: failed to record track play")
        return message

    ns["send_track"] = safe_send_track


def main() -> None:
    # Load bot.py as a module namespace, so we can replace its globals before
    # any main() / run_polling entry point is called.
    ns = runpy.run_path("bot.py", run_name="silentruins_bot_runtime")
    _install_patches(ns)

    # Most versions of this project expose main(). Keep compatibility with
    # either main() or a module-level Application object.
    main_fn = ns.get("main")
    if callable(main_fn):
        main_fn()
        return

    app = ns.get("application") or ns.get("app")
    if app is not None and hasattr(app, "run_polling"):
        app.run_polling()
        return

    raise RuntimeError("SilentRuins startup entry point not found in bot.py")


if __name__ == "__main__":
    main()
