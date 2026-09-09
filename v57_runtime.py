"""SilentRuins v6 runtime launcher.
Loads the proven v5.6 runtime and installs a deterministic editorial mood queue.
The queue is persisted in state so Preview and Auto Post share one rotation.
"""
from __future__ import annotations

import re
from pathlib import Path

ROTATION = ("rain", "love", "night", "lonely", "tired", "ruins")


def main():
    source = Path(__file__).with_name("v56_runtime.py").read_text(encoding="utf-8")
    start = source.index("    def choose_mood(state, hour=None):")
    end = source.index("\n    def visual_score(photo, mood):", start)

    replacement = '''    def choose_mood(state, hour=None):
        # v6: consume a persisted six-mood queue instead of selecting randomly.
        # The queue is shared by Preview and Auto Post and survives restarts.
        queue = list(state.get("mood_queue", []))
        queue = [m for m in queue if m in ROTATION]

        if not queue:
            last = None
            for item in reversed(list(state.get("recent_moods", [])) + list(state.get("preview_moods", []))):
                if item in ROTATION:
                    last = item
                    break
            if last in ROTATION:
                start_index = (ROTATION.index(last) + 1) % len(ROTATION)
            else:
                start_index = 0
            queue = list(ROTATION[start_index:])
            if not queue:
                queue = list(ROTATION)

        mood = queue.pop(0)
        state["mood_queue"] = queue
        return mood
'''

    patched = source[:start] + replacement + source[end:]
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
