"""تنظیمات مشترک تست‌ها — env ساختگی + دیتای موقت، قبل از import bot."""
import os
import tempfile

os.environ.setdefault("BOT_TOKEN", "123:FAKE")
os.environ.setdefault("ADMIN_IDS", "111")
os.environ.setdefault("CHANNEL", "@test")
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="srtests-")
