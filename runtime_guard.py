"""Railway compatibility launcher for the current SilentRuins runtime.

This launcher intentionally starts the direct v6 bot runtime instead of the
legacy v5.6 wrapper. Keeping one runtime prevents nested asyncio.run() calls
and preserves the persistent mood queue.
"""
from v6_image_guard import main


if __name__ == "__main__":
    main()
