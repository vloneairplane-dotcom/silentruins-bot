"""Compatibility launcher for old Railway start commands.
The v5 bot is self-contained; this file intentionally does no monkeypatching.
"""
from bot import main

if __name__ == "__main__":
    main()
