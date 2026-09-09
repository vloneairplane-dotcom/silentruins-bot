"""SilentRuins v6 image anti-repetition guard.
Keeps the proven bot runtime intact and adds persistent Preview image memory.
"""
from __future__ import annotations

import json
from pathlib import Path

import bot

_original_photo_candidates = bot._photo_candidates
_original_build_package = bot.build_package
_original_preview = bot.preview
_last_package = None


def _preview_image_file() -> Path:
    return bot.DATA_DIR / "preview_images.json"


def _load_preview_images() -> list[str]:
    path = _preview_image_file()
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, list):
                return [str(x) for x in value if x]
    except Exception:
        bot.log.exception("Cannot read preview image history")
    return []


def _save_preview_images(images: list[str]):
    path = _preview_image_file()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(images[-30:], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _photo_candidates(mood: str, state: dict) -> list[dict]:
    # Exclude both production images and images already shown by Preview.
    blocked = set(state.get("recent_images", [])[-12:])
    blocked.update(_load_preview_images()[-30:])
    result = []
    seen = set(blocked)
    for photo in _original_photo_candidates(mood, state):
        url = photo.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(photo)
    return result


def build_package(preview=False):
    global _last_package
    package = _original_build_package(preview)
    _last_package = package
    return package


async def preview(update, context):
    global _last_package
    before = len(bot.load_state().get("preview_moods", []))
    _last_package = None
    await _original_preview(update, context)
    after = len(bot.load_state().get("preview_moods", []))

    # The original Preview handler records history only after successful delivery.
    # Therefore a changed preview_moods length is our success signal.
    if after > before and _last_package:
        photo = _last_package.get("photo")
        url = photo.get("url") if photo else None
        if url:
            images = _load_preview_images()
            if url not in images:
                images.append(url)
                _save_preview_images(images)


def main():
    bot._photo_candidates = _photo_candidates
    bot.build_package = build_package
    bot.preview = preview
    bot.main()


if __name__ == "__main__":
    main()
