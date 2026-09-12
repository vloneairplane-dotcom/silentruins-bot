"""Production hardening for the SilentRuins Railway runtime.

This module keeps the existing editorial code intact while fixing runtime-level
failure modes: concurrent publishes, preview consuming the production mood
queue, partial Telegram publishes, and misleading manual-post confirmation.
"""
from __future__ import annotations

import asyncio
import io
from typing import Awaitable, Callable

import requests


class Hardening:
    def __init__(self, bot_module):
        self.bot = bot_module
        self.publish_lock = asyncio.Lock()
        self.original_post_once = bot_module.post_once
        self.original_preview = bot_module.preview

    async def send_package(self, context, package, preview=False):
        """Send the complete package; remove partial photo/text if audio fails."""
        bot = self.bot
        caption = bot._final_caption(package)
        photo = package.get("photo")
        track = package.get("track")
        first_message = None

        try:
            if photo:
                data = await asyncio.to_thread(self._download_photo, photo["url"])
                bio = io.BytesIO(data)
                bio.name = "silentruins.jpg"
                first_message = await context.bot.send_photo(bot.CHANNEL_ID, photo=bio, caption=caption)
            else:
                first_message = await context.bot.send_message(bot.CHANNEL_ID, caption=caption)

            if track:
                await context.bot.send_audio(
                    bot.CHANNEL_ID,
                    audio=track["file_id"],
                    caption=bot._audio_caption(track),
                    title=track.get("title"),
                    performer=track.get("performer"),
                )
            return True
        except Exception:
            if first_message is not None:
                try:
                    await context.bot.delete_message(bot.CHANNEL_ID, first_message.message_id)
                except Exception:
                    bot.log.exception("Could not roll back partial Telegram publish")
            raise

    @staticmethod
    def _download_photo(url: str) -> bytes:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.content

    async def post_once(self, context, force=False):
        async with self.publish_lock:
            before = self.bot.load_state().get("last_post_at", 0)
            await self.original_post_once(context, force=force)
            after = self.bot.load_state().get("last_post_at", 0)
            return after != before

    async def preview(self, update, context):
        async with self.publish_lock:
            state_before = self.bot.load_state()
            queue_before = list(state_before.get("mood_queue", []))
            await self.original_preview(update, context)
            state_after = self.bot.load_state()
            state_after["mood_queue"] = queue_before
            self.bot.save_state(state_after)


def apply(bot_module):
    """Install wrappers after bot.py has loaded all intelligence layers."""
    hardening = Hardening(bot_module)
    bot_module.send_package = hardening.send_package
    bot_module.post_once = hardening.post_once
    bot_module.preview = hardening.preview
    bot_module._production_hardening = hardening
    return hardening
