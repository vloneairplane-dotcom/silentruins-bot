"""تست واحد برای SilentRuins v6 (بدون شبکه).

پوشش:
- چرخه‌ی قطعی ۶ موود فقط با commit جلو می‌ره
- عکس‌ها در هر build فقط یک‌بار fetch می‌شن (رگرسیون سهمیه‌ی Pexels)
- gate: رد پیاپی → نوتیفای ادمین → fallback اضطراری → ریست کنتور
- ایموجی آخر کپشن و فلگ CAPTION_EMOJI
"""
import asyncio
import random
import types

import bot
import content_engine as engine


# ---------------------------------------------------------------- helpers --
class FakeBot:
    def __init__(self):
        self.photos, self.audios, self.messages = [], [], []

    async def send_photo(self, chat_id, photo, caption=None):
        self.photos.append(caption)
        return types.SimpleNamespace(message_id=1)

    async def send_audio(self, chat_id, audio, caption=None, title=None, performer=None):
        self.audios.append(caption)
        return types.SimpleNamespace(message_id=2)

    async def send_message(self, chat_id, text=None, **kwargs):
        self.messages.append((chat_id, text if text is not None else kwargs.get("caption", "-")))
        return types.SimpleNamespace(message_id=3)


def published_count(ctx):
    """پست‌های واقعاً منتشرشده (کپشن دارای امضا) — چه عکس چه fallback متنی"""
    return sum(1 for _, t in ctx.bot.messages if bot.SIGNATURE in t) + len(ctx.bot.photos)


class FakeCtx:
    def __init__(self):
        self.bot = FakeBot()


def seed(tracks=None):
    tracks = tracks if tracks is not None else [
        {"file_id": "f1", "title": "Rainy Days", "performer": "Dep", "mood": None},
        {"file_id": "f2", "title": "Midnight Alone", "performer": "X", "mood": "night"},
        {"file_id": "f3", "title": "Deltangi", "performer": "Y", "mood": "love"},
    ]
    bot.save_library({"tracks": tracks, "unplayed": [t["file_id"] for t in tracks]})
    bot.save_state({"paused": False, "gate_rejects": 0})
    bot._photo_candidates = lambda mood, state: [
        {"url": f"https://img/{mood}/{i}.jpg", "alt": f"dark {mood}", "luminance": 22.0, "width": 800, "height": 1200}
        for i in range(6)
    ]


# ------------------------------------------------------------------ tests --
def test_deterministic_mood_rotation_covers_all():
    seed()
    random.seed(42)
    moods = []
    for _ in range(len(bot.ROTATION)):
        state = bot.load_state()
        pkg = bot.build_package(preview=False)
        assert pkg, "build_package returned None"
        assert pkg["mood"] == bot.choose_mood(state), "queue advanced too early"
        moods.append(pkg["mood"])
        bot.commit_package(pkg)
    assert sorted(moods) == sorted(bot.ROTATION)


def test_photos_fetched_once_per_build(monkeypatch):
    seed()
    calls = {"n": 0}
    real = bot._photo_candidates

    def counting(mood, state):
        calls["n"] += 1
        return real(mood, state)

    monkeypatch.setattr(bot, "_photo_candidates", counting)
    monkeypatch.setattr(bot, "MAX_ATTEMPTS", 24)
    bot.build_package(preview=False)
    assert calls["n"] == 1, f"photos fetched {calls['n']} times in one build!"


def test_gate_reject_notifies_then_emergency_posts(monkeypatch):
    seed()
    ctx = FakeCtx()
    monkeypatch.setattr(bot, "QUALITY_THRESHOLD", 9999)   # همیشه رد می‌شه
    monkeypatch.setattr(bot, "GATE_EMERGENCY_FLOOR", 9999)  # فعلاً کف هم دست‌نیافتنیه

    asyncio.run(bot.post_once(ctx))
    assert published_count(ctx) == 0, "should not publish on first reject"
    assert not ctx.bot.messages, "no DM on first reject"
    assert bot.load_state()["gate_rejects"] == 1

    asyncio.run(bot.post_once(ctx))
    assert published_count(ctx) == 0
    assert ctx.bot.messages and any("پشت‌سر رد" in m[1] for m in ctx.bot.messages), "admin must be notified after 2 rejects"
    assert bot.load_state()["gate_rejects"] == 2

    # fallback اضطراری: کف رو بیار پایین → باید منتشر بشه و کنتور ریست
    monkeypatch.setattr(bot, "GATE_EMERGENCY_FLOOR", 0)
    asyncio.run(bot.post_once(ctx))
    assert published_count(ctx) == 1, "emergency floor should publish"
    assert any("🆘" in m[1] for m in ctx.bot.messages), "emergency notice expected"
    assert bot.load_state()["gate_rejects"] == 0


def test_caption_emoji_toggle(monkeypatch):
    seed()
    pkg = bot.build_package(preview=False)
    body = pkg["caption"]
    mood = pkg["mood"]

    monkeypatch.setattr(bot, "CAPTION_EMOJI", True)
    with_emoji = bot._final_caption(pkg)
    head = with_emoji.rsplit("\n\n", 1)[0]
    assert any(e in head for e in engine.MOODS[mood].get("emojis", [engine.MOODS[mood]["emoji"]]))
    assert with_emoji.rsplit("\n\n", 1)[1] == bot.SIGNATURE

    monkeypatch.setattr(bot, "CAPTION_EMOJI", False)
    plain = bot._final_caption(pkg)
    assert plain == f"{body}\n\n{bot.SIGNATURE}"


def test_intelligence_layers_applied():
    # پس از import bot، لایه‌های هوش باید خودشون فعال باشن (ورودی واحد)
    import music_intelligence, coherence_intelligence  # noqa: F401
    assert bot.MAX_ATTEMPTS >= 24
