from pathlib import Path

from runtime_guard import _patch_source


def _patched():
    source = Path("bot.py").read_text(encoding="utf-8")
    return _patch_source(source)


def test_owner_patch_compiles():
    compile(_patched(), "bot.py (Owner Mode patched)", "exec")


def test_music_selector_has_total_fallback():
    patched = _patched()
    assert "if not pool:" in patched
    assert "if not shortlist:" in patched
    assert "return None" in patched


def test_music_selector_has_semantic_exploration():
    patched = _patched()
    assert "_semantic_score" in patched
    assert "_selection_score" in patched
    assert "play_count" in patched
    assert "exploration" in patched


def test_preview_tracks_are_isolated():
    patched = _patched()
    assert "preview_recent_track_ids" in patched
    assert "preview_excluded" in patched
    assert "preview_window = max(30" in patched


def test_audio_count_happens_after_send():
    patched = _patched()
    send_start = patched.index("async def send_track(context, chat_id, track, reply_to=None):")
    send_end = patched.index("\n\ndef delete_track_by_number", send_start)
    send_block = patched[send_start:send_end]
    assert send_block.index("await context.bot.send_audio") < send_block.index("DB.track_played")


def test_image_picker_rejects_near_black_results():
    patched = _patched()
    assert "luminance" in patched
    assert "lum < 30" in patched
    assert "dark cinematic image" in patched
