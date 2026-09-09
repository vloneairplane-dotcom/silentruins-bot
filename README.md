# SilentRuins Bot v5 🥀

SilentRuins is a Telegram channel bot for cinematic Persian sad-content: **one mood + one caption + one visual + one soundtrack**.

## v5 design

The bot was rebuilt around a single editorial pipeline instead of stacking patches on the old runtime:

1. Choose a mood from time-of-day and recent history.
2. Choose a fresh Persian caption from a larger curated library.
3. Choose music by mood compatibility + recent-use cooldown.
4. Search Pexels for an intentional cinematic scene.
5. Score the complete package: text, image, music and coherence.
6. Retry candidates and publish the strongest package.
7. Only after a successful Telegram send is production state consumed.

### Moods
- 🌧 بارون
- 🌃 شب
- 🚶 تنهایی
- 🥀 دلتنگی
- 🕯 خستگی
- 🏚 ویرونه

## Persistence

Runtime data lives under `DATA_DIR`. On Railway, the bot automatically uses the attached Volume mount path exposed as `RAILWAY_VOLUME_MOUNT_PATH`; `/data` is the expected mount path for this project.

The persistent store contains:
- `library.json` — music library and play-cycle state
- `state.json` — recent moods, captions, tracks and images
- `silentruins.db` — analytics
- `backups/` — bot backups

Railway Volume: mount `/data`.

## Environment

```env
BOT_TOKEN=
ADMIN_IDS=
CHANNEL=@yourchannel
PEXELS_API_KEY=
SEND_PHOTOS=true
PHOTO_CREDIT=false
TIMEZONE=Asia/Tehran
POST_TIMES=10:00,16:00,22:00,02:00
QUALITY_THRESHOLD=82
MAX_CANDIDATES=8
MUSIC_COOLDOWN_POSTS=8
GATE_MAX_REJECTIONS=2
GATE_EMERGENCY_FLOOR=70
CAPTION_EMOJI=true
```

## Commands

- `/start` — help
- `/preview` — private preview; does not consume production music/caption/image rotation
- `/post` — publish immediately
- `/panel` — admin controls
- `/songs` — music library
- `/music [mood]` — choose a mood, then send an MP3
- `/mood <mood>` — set the next music mood
- `/findsong <word>` — search library
- `/del <number>` — remove a track
- `/pause` / `/resume` — scheduler control
- `/stats` / `/report` — analytics
- `/schedule` — schedule settings
- `/jobs` — active jobs
- `/backup` — ZIP backup
- `/health` — persistence/runtime check

## Railway

`python bot.py` is the single entry point — it self-loads the music/coherence intelligence layers at the end of the module. `panel_runtime.py` is kept only as a thin compatibility shim (`import bot; bot.main()`) in case the Railway start command still points at it; the result is identical either way. No other runtime files exist.

Attach the existing `worker-volume` to the `worker` service with mount path `/data`. Do not create a second volume.

## Music

Telegram `file_id` values are stored in the persistent library, so MP3 files do not need to be re-uploaded after a restart or deployment when the Railway Volume is attached.

For public-channel distribution, only use music you have the rights or permission to distribute.
