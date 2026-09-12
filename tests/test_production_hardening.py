"""Regression tests for production hardening wrappers."""
import asyncio
import types

import bot
import production_hardening


class FakeBot:
    def __init__(self, fail_audio=False):
        self.fail_audio = fail_audio
        self.photos = []
        self.messages = []
        self.audios = []
        self.deleted = []

    async def send_photo(self, chat_id, photo, caption=None):
        self.photos.append(caption)
        return types.SimpleNamespace(message_id=11)

    async def send_message(self, chat_id, text=None, **kwargs):
        self.messages.append(text if text is not None else kwargs.get("caption"))
        return types.SimpleNamespace(message_id=12)

    async def send_audio(self, chat_id, audio, caption=None, title=None, performer=None):
        if self.fail_audio:
            raise RuntimeError("audio failed")
        self.audios.append(caption)
        return types.SimpleNamespace(message_id=13)

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


class Ctx:
    def __init__(self, fail_audio=False):
        self.bot = FakeBot(fail_audio)


def package():
    return {
        "mood": "night",
        "caption": "یک شب آرام",
        "track": {"file_id": "track-1", "title": "Night", "performer": "X"},
        "photo": {"url": "https://example.test/photo.jpg"},
        "score": {"overall": 90},
    }


def test_audio_failure_rolls_back_partial_publish(monkeypatch):
    monkeypatch.setattr(production_hardening.Hardening, "_download_photo", staticmethod(lambda _: b"jpg"))
    hardening = production_hardening.Hardening(bot)
    ctx = Ctx(fail_audio=True)

    try:
        asyncio.run(hardening.send_package(ctx, package()))
    except RuntimeError:
        pass
    else:
        raise AssertionError("audio failure must propagate")

    assert ctx.bot.photos == ["یک شب آرام\n\n— silent ruins 🥀"]
    assert ctx.bot.deleted == [(bot.CHANNEL_ID, 11)]


def test_preview_wrapper_restores_production_queue(monkeypatch):
    before = {"mood_queue": ["rain", "love", "night"], "preview_moods": []}
    after = {"mood_queue": ["love", "night"], "preview_moods": ["rain"]}
    calls = {"n": 0}

    monkeypatch.setattr(bot, "load_state", lambda: (before.copy() if calls["n"] == 0 else after.copy()))
    monkeypatch.setattr(bot, "save_state", lambda state: calls.__setitem__("saved", state))
    async def fake_preview(update, context):
        calls["n"] += 1
    monkeypatch.setattr(bot, "preview", fake_preview)

    hardening = production_hardening.Hardening(bot)
    asyncio.run(hardening.preview(types.SimpleNamespace(), types.SimpleNamespace()))
    assert calls["saved"]["mood_queue"] == before["mood_queue"]
