"""SilentRuins v6 runtime.
Directly fixes the mood-selection integration point used by Preview and Auto Post.
The v5.6 visual/music/quality pipeline is preserved; only mood queue ownership is
reworked so one build consumes exactly one mood and the queue is persisted.
"""
from __future__ import annotations

import re
from pathlib import Path

ROTATION = ("rain", "love", "night", "lonely", "tired", "ruins")


def main():
    source = Path(__file__).with_name("v56_runtime.py").read_text(encoding="utf-8")

    choose_start = source.index("    def choose_mood(state, hour=None):")
    choose_end = source.index("\n    def visual_score(photo, mood):", choose_start)

    build_start = source.index("    def build(preview=False):")
    build_end = source.index("\n    bot.build_package = build", build_start)
    build_assign_end = build_end + len("\n    bot.build_package = build")

    choose_replacement = '''    def choose_mood(state, hour=None):
        # v6: read the queue without consuming it. Consumption happens exactly
        # once after a successful Preview or successfully published post.
        queue = [m for m in state.get("mood_queue", []) if m in ROTATION]
        if not queue:
            history = list(state.get("recent_moods", [])) + list(state.get("preview_moods", []))
            last = next((m for m in reversed(history) if m in ROTATION), None)
            start_index = (ROTATION.index(last) + 1) % len(ROTATION) if last else 0
            queue = list(ROTATION[start_index:]) + list(ROTATION[:start_index])
            state["mood_queue"] = queue
        return queue[0]
'''

    build_replacement = '''    def build(preview=False):
        state = bot.load_state()
        lib = profile_library(bot.load_library())
        gate = max(82, bot.QUALITY_THRESHOLD)
        blocked = list(state.get("recent_caption_hashes", []))[-25:] + list(state.get("preview_caption_hashes", []))[-25:]

        # CRITICAL: choose exactly one mood for this build. Quality attempts must
        # never consume additional moods from the editorial queue.
        mood = choose_mood(state)
        best = None
        best_key = (-1, -1, -1)

        for _ in range(max(30, bot.MAX_ATTEMPTS)):
            caption = e.choose_caption(mood, blocked)
            track = pick_music(lib["tracks"], mood, state, preview)
            photos = bot._photo_candidates(mood, state) if bot.SEND_PHOTOS else []
            photo = pick_photo(photos, mood)
            sc = quality(mood, caption, track, photo)
            pack = {"mood": mood, "caption": caption, "track": track, "photo": photo, "score": sc}
            key = (sc["overall"], sc["image"], sc["music"])
            if key > best_key:
                best, best_key = pack, key
            if sc["overall"] >= gate and sc["image"] >= 76 and sc["music"] >= 72 and sc["coherence"] >= 78:
                break

        if not best:
            return None

        sc = best["score"]
        if sc["image"] < 72 or sc["music"] < 72:
            return None
        if not preview and not (sc["overall"] >= gate and sc["image"] >= 76 and sc["music"] >= 72 and sc["coherence"] >= 78):
            return None

        if preview:
            preview_memory.append(best["mood"])
            del preview_memory[:-6:]
            s = bot.load_state()
            s["preview_moods"] = (s.get("preview_moods", []) + [best["mood"]])[-12:]
            if best.get("track"):
                s["preview_track_ids"] = (s.get("preview_track_ids", []) + [best["track"]["file_id"]])[-25:]
            h = hashlib.sha256(norm(best["caption"]).encode()).hexdigest()
            s["preview_caption_hashes"] = (s.get("preview_caption_hashes", []) + [h])[-25:]
            # Preview is a real editorial consumption: advance exactly once.
            queue = [m for m in s.get("mood_queue", []) if m in ROTATION]
            if not queue:
                queue = list(ROTATION)
            if queue and queue[0] == best["mood"]:
                queue.pop(0)
            else:
                queue = list(ROTATION)
                if best["mood"] in queue:
                    queue.remove(best["mood"])
            if not queue:
                queue = list(ROTATION)
            s["mood_queue"] = queue
            bot.save_state(s)
        return best
'''

    queue_commit = '''

    # Auto Post advances the queue only after Telegram delivery succeeds.
    original_commit_package = bot.commit_package

    def commit_with_queue(package):
        original_commit_package(package)
        s = bot.load_state()
        queue = [m for m in s.get("mood_queue", []) if m in ROTATION]
        if queue and queue[0] == package.get("mood"):
            queue.pop(0)
        elif package.get("mood") in ROTATION:
            queue = list(ROTATION)
            queue.remove(package["mood"])
        if not queue:
            queue = list(ROTATION)
        s["mood_queue"] = queue
        bot.save_state(s)

    bot.commit_package = commit_with_queue
'''

    patched = source[:choose_start] + choose_replacement + source[choose_end:build_start] + build_replacement + source[build_end:build_assign_end] + queue_commit + source[build_assign_end:]
    patched = re.sub(r'\nif __name__ == "__main__": main\(\)\s*$', '', patched)

    namespace = {
        "__name__": "silentruins_v56_embedded",
        "__file__": str(Path(__file__).with_name("v56_runtime.py")),
        "ROTATION": ROTATION,
    }
    exec(compile(patched, str(Path(__file__).with_name("v56_runtime.py")), "exec"), namespace)
    namespace["main"]()


if __name__ == "__main__":
    main()
