"""SilentRuins v5.7 launcher.
Loads the proven v5.6 runtime and replaces only mood selection with an editorial
coverage rotation. Visual, music, quality, Telegram and persistence logic stay
on the v5.6 implementation.
"""
from __future__ import annotations

import re
from pathlib import Path


def main():
    source = Path(__file__).with_name("v56_runtime.py").read_text(encoding="utf-8")
    start = source.index("    def choose_mood(state, hour=None):")
    end = source.index("\n    def visual_score(photo, mood):", start)

    replacement = '''    def choose_mood(state, hour=None):
        # v5.7 Editorial Rotation: all six moods remain eligible.
        # Time only breaks ties; recent usage controls coverage.
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
        underexposed = [m for m in e.MOODS if counts[m] == minimum]

        # Pick from the least-used moods. This creates a real editorial
        # rotation without hard-coding a fixed sequence.
        if underexposed:
            return random.choices(underexposed, weights=[base[m] for m in underexposed], k=1)[0]
        return min(e.MOODS, key=lambda m: (counts[m], -base[m]))
'''

    patched = source[:start] + replacement + source[end:]
    patched = re.sub(r'\nif __name__ == "__main__": main\(\)\s*$', '', patched)
    namespace = {"__name__": "silentruins_v56_embedded", "__file__": str(Path(__file__).with_name("v56_runtime.py"))}
    exec(compile(patched, str(Path(__file__).with_name("v56_runtime.py")), "exec"), namespace)
    namespace["main"]()


if __name__ == "__main__":
    main()
