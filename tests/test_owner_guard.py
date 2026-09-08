from pathlib import Path

from runtime_guard import _patch_source


def test_owner_patch_compiles():
    source = Path("bot.py").read_text(encoding="utf-8")
    patched = _patch_source(source)
    compile(patched, "bot.py (Owner Mode patched)", "exec")


def test_music_selector_has_total_fallback():
    source = Path("bot.py").read_text(encoding="utf-8")
    patched = _patch_source(source)
    assert "if not shortlist:" in patched
    assert "if chosen_id is None and lib[\"unplayed\"]:" in patched
    assert "return None" in patched


def test_preview_tracks_are_isolated():
    source = Path("bot.py").read_text(encoding="utf-8")
    patched = _patch_source(source)
    assert "preview_recent_track_ids" in patched
    assert "preview_excluded" in patched


def test_image_picker_rejects_near_black_results():
    source = Path("bot.py").read_text(encoding="utf-8")
    patched = _patch_source(source)
    assert "luminance" in patched
    assert "lum < 30" in patched
    assert "dark cinematic image" in patched
