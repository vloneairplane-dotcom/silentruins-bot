"""SilentRuins v5.8 launcher.
Keeps the proven v5.6 runtime and replaces only mood selection with a
persistent deterministic editorial rotation. Visual, music, quality,
Telegram and persistence logic remain unchanged.
"""
from __future__ import annotations

import re
from pathlib import Path


ROTATION = ("rain", "love", "night", "lonely", "tired", "ruins")


def main():
    source_path = Path(__file__).with_name("v56_runtime.py")
    source = source_path.read_text(encoding="utf-8")
    start = source.index("    def choose_mood(state, hour=None):")
    end = source.index("\n    def visual_score(photo, mood):", start)

    replacement = '''    def choose_mood(state, hour=None):
        # v5.8 Editorial Rotation:
        # 1) all six moods stay eligible at every hour;
        # 2) least-used moods get priority for real coverage;
        # 3) ties follow a deterministic editorial cycle instead of random
        #    selection, preventing repeated lonely/night previews;
        # 4) time-of-day only acts as a tie-breaker among equally exposed moods.
        h = datetime.now().hour if hour is None else hour
        base = {m: 1.0 for m in e.MOODS}
        if h >= 22 or h < 5:
            base.update({"night": 1.12, "lonely": 1.04, "love": 1.00, "ruins": .98, "rain": .94, "tired": .92})
        elif h >= 17:
            base.update({"love": 1.12, "rain": 1.08, "lonely": 1.02, "night": .98, "ruins": .96, "tired": .94})
        else:
            base.update({"tired": 1.10, "rain": 1.08, "love": 1.02, "lonely": 1.00, "ruins": .96, "night": .92})

        recent = list(state.get("recent_moods", []))[-3:]
        previews = list(state.get("preview_moods", []))[-6:]
        process = preview_memory[-4:]
        history = recent + previews + process
        counts = {m: sum(1 for x in history if x == m) for m in e.MOODS}
        minimum = min(counts.values()) if counts else 0
        candidates = [m for m in ROTATION if m in e.MOODS and counts[m] == minimum]

        # Never use randomness to decide between equally underexposed moods.
        # The cycle gives the editorial system a predictable, auditable order.
        if candidates:
            cycle_pos = {m: i for i, m in enumerate(ROTATION)}
            last_seen = []
            for item in history:
                if item in cycle_pos:
                    last_seen.append(cycle_pos[item])
            anchor = last_seen[-1] if last_seen else -1
            ordered = sorted(
                candidates,
                key=lambda m: ((cycle_pos[m] - anchor) % len(ROTATION), -base[m])
            )
            return ordered[0]

        return min(e.MOODS, key=lambda m: (counts[m], -base[m]))
'''

    patched = source[:start] + replacement + source[end:]
    patched = re.sub(r'\nif __name__ == "__main__": main\(\)\s*$', '', patched)
    namespace = {
        "__name__": "silentruins_v56_embedded",
        "__file__": str(source_path),
    }
    exec(compile(patched, str(source_path), "exec"), namespace)
    namespace["main"]()


if __name__ == "__main__":
    main()
