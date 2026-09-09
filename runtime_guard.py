"""Railway compatibility launcher for the direct v6 runtime."""
import asyncio
from telegram.ext import Application
import bot


async def _run_polling_inside_existing_loop(self, *args, **kwargs):
    await self.initialize()
    await self.start()
    if self.updater is None:
        raise RuntimeError("Telegram updater is unavailable")
    await self.updater.start_polling()
    try:
        await asyncio.Event().wait()
    finally:
        await self.updater.stop()
        await self.stop()
        await self.shutdown()


Application.run_polling = _run_polling_inside_existing_loop

if __name__ == "__main__":
    bot.main()
