"""SilentRuins Owner Mode runtime hardening.

V4.2 production safety/matching layer. It patches the legacy bot at startup so
music selection has strong semantic matching, exploration/diversity, and a
longer preview cooldown; audio analytics are recorded only after Telegram
accepts the file; Pexels keeps the cinematic look without near-black images;
and runtime data is directed to persistent Railway storage when available.
"""
from __future__ import annotations

import random
from pathlib import Path

GUARD_VERSION = "4.2.1-persistent-library"


def _patch_source(source: str) -> str:
    # ------------------------------------------------------------------
    # Persistent runtime data: Railway Volume -> /data.
    # ------------------------------------------------------------------
    old_data = 'DATA_DIR = Path(os.getenv("DATA_DIR", ".")).expanduser()'
    new_data = '''_railway = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))
_data_dir_env = os.getenv("DATA_DIR")
DATA_DIR = Path(_data_dir_env or ("/data" if _railway else ".")).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# One-time migration: if a deployment already has runtime data in the project
# directory, copy it into /data before the persistent store is opened.
if _railway and DATA_DIR.resolve() != Path(".").resolve():
    for _name in ("library.json", "state.json", "silentruins.db"):
        _src = Path(_name)
        _dst = DATA_DIR / _name
        if _src.exists() and not _dst.exists():
            try:
                _dst.write_bytes(_src.read_bytes())
            except Exception:
                pass
    _src_music = Path("music")
    _dst_music = DATA_DIR / "music"
    if _src_music.exists() and not _dst_music.exists():
        try:
            import shutil
            shutil.copytree(_src_music, _dst_music)
        except Exception:
            pass
'''
    if old_data in source:
        source = source.replace(old_data, new_data, 1)

    # ------------------------------------------------------------------
    # Music selector: total function + semantic matching + exploration.
    # ------------------------------------------------------------------
    start = source.index("def get_next_track(mood=None, peek=False):")
    end = source.index("\n\ndef consume_track(track):", start)
    replacement = '''def get_next_track(mood=None, peek=False):
    """Select music safely with semantic matching, exploration and cooldowns."""
    lib = load_library()
    tracks = [t for t in lib.get("tracks", []) if t and t.get("file_id")]
    if not tracks:
        return None

    state = load_state()
    recent_ids = [x for x in (state.get("recent_track_ids", []) or []) if x]
    cooldown_ids = set(recent_ids[-MUSIC_COOLDOWN_POSTS:])
    by_id = {t["file_id"]: t for t in tracks}

    def _play_count(track):
        try:
            row = DB.conn.execute(
                "SELECT play_count FROM tracks WHERE file_id=?",
                (track.get("file_id"),),
            ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _semantic_score(track):
        if not mood:
            return 0.60
        return track_match(track, mood, MOODS, MOOD_ALIASES)

    def _selection_score(track):
        semantic = _semantic_score(track)
        count = _play_count(track)
        exploration = 0.10 if count == 0 else (0.06 if count <= 1 else 0.025 if count <= 2 else 0.0)
        return semantic + exploration

    if peek:
        preview_recent = [x for x in (state.get("preview_recent_track_ids", []) or []) if x]
        preview_window = max(30, MAX_CANDIDATES * 3)
        preview_excluded = set(preview_recent[-preview_window:])
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

        ranked = sorted(pool, key=_selection_score, reverse=True)
        if mood and ranked:
            top_score = _selection_score(ranked[0])
            shortlist = [t for t in ranked if _selection_score(t) >= top_score - 0.13]
        else:
            shortlist = ranked
        if not shortlist:
            shortlist = ranked[:5]
        chosen = random.choice(shortlist[: min(6, len(shortlist))])
        preview_recent.append(chosen["file_id"])
        save_state({"preview_recent_track_ids": preview_recent[-preview_window:]})
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

    eligible_tracks = [by_id[fid] for fid in lib["unplayed"] if fid in by_id]
    if not eligible_tracks:
        return None

    ranked = sorted(eligible_tracks, key=_selection_score, reverse=True)
    chosen = None
    for track in ranked:
        if track["file_id"] not in cooldown_ids:
            chosen = track
            break
    if chosen is None:
        chosen = ranked[0]

    chosen_id = chosen["file_id"]
    if chosen_id in lib["unplayed"]:
        lib["unplayed"].remove(chosen_id)
        save_library(lib)
    return chosen
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
    # Image picker: cinematic darkness without unusable near-black images.
    # ------------------------------------------------------------------
    start = source.index("def _pick_dark_photo(photos, excluded_urls=None):")
    end = source.index("\n\ndef fetch_pexels_photo", start)
    replacement = '''def _pick_dark_photo(photos, excluded_urls=None):
    """Pick a dark cinematic image while protecting readability."""
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
