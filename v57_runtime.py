"""SilentRuins v5.9 launcher.
Loads the proven v5.6 runtime and replaces mood selection with a deterministic
editorial rotation. The rotation is shared by Preview and Auto Post so content
coverage stays balanced across restarts when state is persisted.
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
        # v5.9 Editorial Rotation: deterministic six-mood cycle.
        # Preview and Auto Post use the same persisted mood history.
        recent = list(state.get("recent_moods", []))
        previews = list(state.get("preview_moods", []))
        history = recent + previews
        last = history[-1] if history else None

        if last in ROTATION:
            return ROTATION[(ROTATION.index(last) + 1) % len(ROTATION)]

        # If old state has no valid mood, start from rain.
        return ROTATION[0]
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
