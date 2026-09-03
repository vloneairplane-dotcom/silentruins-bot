import os
import json
import random
import re
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIG
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

CHANNEL = os.getenv("CHANNEL", "@songsandscars")
MUSIC_FOLDER = os.getenv("MUSIC_FOLDER", "music")
STATE_FILE = os.getenv("STATE_FILE", "state.json")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tehran")
SIGNATURE = "\n\n— silent ruins 🥀"

os.makedirs(MUSIC_FOLDER, exist_ok=True)

# =========================================================
# ADMIN IDS
# =========================================================

ADMIN_IDS = set()

for value in os.getenv("ADMIN_IDS", "").split(","):
    value = value.strip()
    if value.isdigit():
        ADMIN_IDS.add(int(value))

# =========================================================
# THEMES
# =========================================================

THEMES = {
    "midnight": {
        "emojis": ["🌑", "🌙", "🕯️", "🖤"],
        "queries": [
            "dark midnight street cinematic",
            "lonely night city cinematic",
            "dark bedroom window night",
            "midnight rain film photography",
            "lonely silhouette night",
        ],
        "texts": [
            "2:17 AM.\neveryone is asleep.\nmy mind isn't. 🌑",
            "the city sleeps.\nmy thoughts don't. 🌙",
            "some nights are too quiet\nto hide from yourself. 🕯️",
            "at night,\neverything you buried learns how to speak. 🖤",
            "it's always louder after midnight.\nthe memories.\nthe silence.\nme. 🌑",
        ],
    },
    "rain": {
        "emojis": ["🌧️", "☔", "🥀", "🖤"],
        "queries": [
            "lonely person rain cinematic",
            "rainy night street film photography",
            "person under rain dark aesthetic",
            "rain window lonely night",
            "city rain cinematic night",
        ],
        "texts": [
            "some nights,\nyou don't need someone.\nyou just need the rain to be louder. 🌧️",
            "the rain never asks\nwhy you're still awake. ☔",
            "i like rainy nights.\nthey make loneliness look beautiful. 🥀",
            "maybe that's why i love the rain.\nit knows how to fall apart quietly. 🌧️",
            "some memories sound like rain\nhitting a window at 3 AM. 🖤",
        ],
    },
    "cigarette": {
        "emojis": ["🚬", "🖤", "🌑", "🥀"],
        "queries": [
            "man cigarette night cinematic",
            "smoking alone night photography",
            "cigarette dark portrait film",
            "lonely smoker rainy night",
            "smoking silhouette night",
        ],
        "texts": [
            "one cigarette.\none memory.\nwhole night gone. 🚬",
            "some habits aren't addictions.\nsometimes they're reminders. 🖤",
            "i don't smoke to forget.\ni smoke because remembering got heavy. 🚬",
            "the room was quiet.\nthe cigarette wasn't. 🌑",
            "smoke disappears faster than people do. 🥀",
        ],
    },
    "night_drive": {
        "emojis": ["🚘", "🌃", "🌑", "🎧"],
        "queries": [
            "lonely night drive cinematic",
            "car driving night rain film",
            "empty highway night cinematic",
            "city lights car night",
            "night road lonely photography",
        ],
        "texts": [
            "sometimes you don't need a destination.\nyou just need to keep driving. 🚘",
            "the road was empty.\nmy head wasn't. 🌃",
            "late night drives fix things\nthat conversations can't. 🎧",
            "no calls.\nno messages.\njust music and headlights. 🌑",
            "i drove until the city disappeared\nand my thoughts finally got quiet. 🚘",
        ],
    },
    "neon_city": {
        "emojis": ["🌃", "💜", "🖤", "🌑"],
        "queries": [
            "neon city night lonely cinematic",
            "dark cyberpunk street photography",
            "neon lights rainy street",
            "lonely city night cinematic",
            "urban night neon film",
        ],
        "texts": [
            "millions of lights.\nstill somehow lonely. 🌃",
            "the city knows how to make loneliness look beautiful. 🖤",
            "everyone was somewhere.\ni was nowhere. 🌑",
            "neon lights.\nempty streets.\nthe same old thoughts. 💜",
            "the city never sleeps.\nsome people just become better at hiding. 🌃",
        ],
    },
    "empty_room": {
        "emojis": ["🕯️", "🪟", "🖤", "🥀"],
        "queries": [
            "empty dark room window cinematic",
            "lonely bedroom night photography",
            "dark room chair window rain",
            "empty room moody film photography",
            "lonely room lamp night",
        ],
        "texts": [
            "the room is empty.\nthe memories aren't. 🕯️",
            "some rooms remember people\nbetter than we do. 🪟",
            "silence feels different\nwhen nobody is coming back. 🖤",
            "i left the room.\nsomehow the memories followed. 🥀",
            "an empty room can still feel crowded\nwith everything you lost. 🕯️",
        ],
    },
    "moon": {
        "emojis": ["🌙", "🌌", "🖤", "✨"],
        "queries": [
            "moon night dark cinematic",
            "lonely person under moonlight",
            "moon clouds dark photography",
            "night sky lonely aesthetic",
            "silhouette moon cinematic",
        ],
        "texts": [
            "the moon has seen every version of me. 🌙",
            "some nights\ni only trust the sky. 🌌",
            "maybe loneliness isn't empty.\nmaybe it's just quiet. 🌙",
            "the moon stays.\npeople don't. 🖤",
            "same moon.\ndifferent life.\ndifferent me. ✨",
        ],
    },
    "breakup": {
        "emojis": ["🥀", "🩶", "🖤", "💔"],
        "queries": [
            "breakup cinematic photography",
            "sad couple silhouette night",
            "lost love dark cinematic",
            "person alone after breakup",
            "goodbye couple rainy night",
        ],
        "texts": [
            "the worst part wasn't losing you.\nit was losing myself trying to keep you. 🥀",
            "you didn't break my heart.\nyou changed what i expect from people. 🩶",
            "i still remember.\ni just stopped going back. 🖤",
            "some goodbyes happen\nlong before people actually leave. 💔",
            "you were a beautiful mistake\ni'm glad i survived. 🥀",
        ],
    },
    "nostalgia": {
        "emojis": ["📼", "🕯️", "🥀", "🌙"],
        "queries": [
            "nostalgic 35mm film photography",
            "old street rainy night vintage",
            "nostalgic childhood film aesthetic",
            "old room nostalgia photography",
            "vintage night city",
        ],
        "texts": [
            "we didn't know those were the good days.\nwe just thought they were normal. 🕯️",
            "one song can bring back a whole person. 🎧",
            "i miss the version of me\nthat didn't know how things end. 🥀",
            "some memories don't hurt.\nthey just refuse to leave. 🌙",
            "the past never knocks.\nit just walks in when a song starts. 📼",
        ],
    },
    "lonely_street": {
        "emojis": ["🚶", "🌑", "🖤", "🌃"],
        "queries": [
            "lonely person empty street cinematic",
            "walking alone city night",
            "empty street dark film photography",
            "alone man street night",
            "lonely silhouette urban night",
        ],
        "texts": [
            "i learned how to walk alone\nwithout looking back. 🚶",
            "some streets feel familiar\nbecause you've cried there before. 🌑",
            "the loneliest walks\nare the ones nobody knows about. 🖤",
            "i kept walking.\nnot because i knew where i was going.\nbecause stopping hurt more. 🚶",
            "empty streets understand people better than crowded rooms. 🌃",
        ],
    },
    "cold": {
        "emojis": ["🩶", "❄️", "🖤", "⛓️"],
        "queries": [
            "cold dark urban cinematic",
            "black white lonely man photography",
            "cold city night film",
            "hooded man dark street",
            "winter lonely cinematic",
        ],
        "texts": [
            "i don't have trust issues.\ni have memories. 🩶",
            "i became colder\nwhen being soft kept costing me. ❄️",
            "no anger.\nno revenge.\njust distance. ⛓️",
            "i remember who stayed.\ni remember who disappeared. 🖤",
            "i got harder to reach\nbecause i got tired of being easy to hurt. ⛓️",
        ],
    },
    "ocean_fog": {
        "emojis": ["🌊", "🌫️", "🖤", "🌙"],
        "queries": [
            "dark ocean fog cinematic",
            "lonely ocean night photography",
            "foggy sea dark aesthetic",
            "person ocean night cinematic",
            "dark beach lonely film",
        ],
        "texts": [
            "some feelings are like the ocean.\nyou can see them.\nyou just can't measure them. 🌊",
            "the fog made everything disappear.\nexcept the thoughts i wanted gone. 🌫️",
            "i stood by the ocean\nand let it keep my secrets. 🖤",
            "there's something honest about the sea.\nit never pretends to be calm. 🌊",
            "maybe i needed the horizon\nbecause everything behind me hurt. 🌙",
        ],
    },
    "dark_romance": {
        "emojis": ["🥀", "🖤", "🕯️", "🌹"],
        "queries": [
            "dark romance couple cinematic",
            "romantic shadows film photography",
            "dark couple silhouette night",
            "moody romantic photography",
            "couple candlelight dark aesthetic",
        ],
        "texts": [
            "i wanted forever.\nyou wanted something temporary. 🥀",
            "some people feel like home\nright before they become a memory. 🖤",
            "loving you was easy.\nforgetting you wasn't. 🌹",
            "you were my favorite place\nto get lost. 🕯️",
            "we looked beautiful together.\nthat doesn't mean we belonged together. 🥀",
        ],
    },
}

# =========================================================
# KNOWN SONGS / THEME MATCHING
# =========================================================

SONGS = {
    "Lorde - Supercut": ["nostalgia", "breakup", "dark_romance"],
    "The Weeknd - Call Out My Name": ["breakup", "dark_romance", "midnight"],
    "Lorde - Writer in the Dark": ["breakup", "midnight", "dark_romance"],
    "Hozier - Unknown / Nth": ["breakup", "dark_romance", "cold"],
    "The Weeknd - Echoes of Silence": ["midnight", "empty_room", "breakup"],
    "Hozier - Cherry Wine (Live)": ["dark_romance", "nostalgia", "breakup"],
    "Hozier - Work Song": ["dark_romance", "nostalgia"],
    "Coldplay - Sparks": ["nostalgia", "dark_romance", "midnight"],
    "Lorde - Liability": ["lonely_street", "empty_room", "breakup"],
    "Bon Iver & St. Vincent - Roslyn": ["ocean_fog", "nostalgia", "midnight"],
    "The Cinematic Orchestra - To Build a Home": ["empty_room", "nostalgia", "dark_romance"],
    "Ludovico Einaudi - Nuvole Bianche": ["rain", "midnight", "ocean_fog"],
    "Cigarettes After Sex - Heavenly": ["dark_romance", "midnight", "nostalgia"],
    "Cigarettes After Sex - Sweet": ["dark_romance", "nostalgia"],
    "Daughter - Medicine": ["breakup", "rain", "midnight"],
    "Daughter - Smother": ["breakup", "empty_room", "dark_romance"],
    "Daughter - Youth": ["nostalgia", "breakup", "rain"],
    "AURORA - Runaway": ["lonely_street", "night_drive", "ocean_fog"],
    "Mitski - First Love / Late Spring": ["dark_romance", "nostalgia", "breakup"],
    "Mitski - I Bet on Losing Dogs": ["breakup", "lonely_street", "midnight"],
    "Mitski - Francis Forever": ["nostalgia", "breakup", "rain"],
    "Mitski - Class of 2013": ["nostalgia", "empty_room", "breakup"],
    "Adele - Love in the Dark": ["breakup", "dark_romance", "midnight"],
    "The Weeknd - Until I Bleed Out": ["midnight", "breakup", "cold"],
    "Arctic Monkeys - I Wanna Be Yours": ["dark_romance", "midnight"],
    "Joji - Slow Dancing in the Dark": ["dark_romance", "midnight", "breakup"],
    "Coldplay - The Scientist": ["nostalgia", "breakup", "rain"],
    "Arctic Monkeys - 505": ["night_drive", "dark_romance", "nostalgia"],
    "Arctic Monkeys - Do I Wanna Know?": ["dark_romance", "night_drive", "midnight"],
    "Arctic Monkeys - Why'd You Only Call Me When You're High?": ["night_drive", "neon_city", "midnight"],
    "Coldplay - Fix You": ["breakup", "rain", "dark_romance"],
    "Kodaline - All I Want": ["breakup", "dark_romance", "nostalgia"],
    "Ludovico Einaudi - Experience": ["night_drive", "rain", "ocean_fog"],
    "Cigarettes After Sex - Sunsetz": ["dark_romance", "nostalgia", "night_drive"],
    "Cigarettes After Sex - Cry": ["breakup", "dark_romance", "rain"],
    "Cigarettes After Sex - K.": ["dark_romance", "midnight", "nostalgia"],
    "Cigarettes After Sex - Nothing's Gonna Hurt You Baby": ["dark_romance", "midnight"],
    "Beach House - Space Song": ["moon", "ocean_fog", "midnight", "nostalgia"],
}

# =========================================================
# STATE
# =========================================================

DEFAULT_STATE = {
    "paused": False,
    "post_count": 0,
    "music_count": 0,
    "text_used": [],
    "music_used": [],
    "photo_used": [],
    "last_post": None,
}

def load_state():
    if not os.path.exists(STATE_FILE):
        return json.loads(json.dumps(DEFAULT_STATE))

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        for key, value in DEFAULT_STATE.items():
            if key not in state:
                state[key] = json.loads(json.dumps(value))

        return state
    except Exception as error:
        print("State error:", error)
        return json.loads(json.dumps(DEFAULT_STATE))

def save_state(state):
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, STATE_FILE)

def is_admin(user_id):
    return user_id in ADMIN_IDS

# =========================================================
# THEME / TEXT
# =========================================================

def get_time_theme():
    hour = datetime.now(ZoneInfo(TIMEZONE)).hour

    if 0 <= hour < 6:
        return random.choice(["midnight", "rain", "cigarette", "moon", "empty_room"])
    if 6 <= hour < 12:
        return random.choice(["nostalgia", "ocean_fog", "lonely_street"])
    if 12 <= hour < 18:
        return random.choice(["cold", "lonely_street", "neon_city", "rain"])
    if 18 <= hour < 22:
        return random.choice(["dark_romance", "night_drive", "neon_city", "breakup"])
    return random.choice(["midnight", "breakup", "dark_romance", "night_drive", "cigarette"])

def choose_text(theme_name, state):
    theme = THEMES[theme_name]
    used = set(state.get("text_used", []))

    available = []
    for text in theme["texts"]:
        text_id = f"{theme_name}::{text}"
        if text_id not in used:
            available.append((text_id, text))

    if not available:
        available = [(f"{theme_name}::{text}", text) for text in theme["texts"]]

    selected_id, selected_text = random.choice(available)
    state.setdefault("text_used", []).append(selected_id)

    return selected_text

# =========================================================
# MUSIC
# =========================================================

ALLOWED_AUDIO = (".mp3", ".m4a", ".flac", ".wav", ".ogg")

def get_music_files():
    if not os.path.exists(MUSIC_FOLDER):
        return []

    return sorted(
        filename
        for filename in os.listdir(MUSIC_FOLDER)
        if filename.lower().endswith(ALLOWED_AUDIO)
    )

def normalize_filename(filename):
    name = os.path.splitext(filename)[0]
    name = name.replace("_", " ").replace("–", "-").replace("—", "-")
    name = re.sub(r"\s+", " ", name).strip()

    # Remove common leading track numbers
    name = re.sub(r"^\s*\d+(?:\s*[-_.]\s*|\s+)", "", name)

    # Remove bitrate suffix
    name = re.sub(
        r"\s*[\(\[]?\b(128|192|256|320)\s*(kbps)?\b[\)\]]?\s*$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    return name.strip()

def get_song_metadata(filename):
    normalized = normalize_filename(filename)
    lower = normalized.lower()

    # Direct matching against known song names
    for key in SONGS:
        if key.lower() in lower:
            artist, title = key.split(" - ", 1)
            return title, artist

    # Common "title - artist" pattern
    parts = [x.strip() for x in re.split(r"\s+-\s+", normalized) if x.strip()]

    if len(parts) >= 2:
        return " - ".join(parts[1:]), parts[0]

    return normalized, "Unknown Artist"

def song_themes(filename):
    title, artist = get_song_metadata(filename)
    full = f"{artist} - {title}".lower()

    matches = []
    for song_name, themes in SONGS.items():
        if song_name.lower() in full or full in song_name.lower():
            matches.extend(themes)

    return set(matches)

def choose_music(theme_name, state):
    files = get_music_files()
    if not files:
        return None

    matched = [f for f in files if theme_name in song_themes(f)]

    # Prefer songs explicitly matched to this theme.
    candidates = matched if matched else files

    used = set(state.get("music_used", []))
    available = [f for f in candidates if f not in used]

    if not available:
        # Start a new cycle for these candidates.
        state["music_used"] = [x for x in used if x not in candidates]
        available = candidates[:]

    selected = random.choice(available)
    state.setdefault("music_used", []).append(selected)
    return selected

# =========================================================
# PEXELS
# =========================================================

def get_pexels_photo(theme_name, state):
    if not PEXELS_API_KEY:
        print("PEXELS_API_KEY missing.")
        return None

    query = random.choice(THEMES[theme_name]["queries"])

    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": query,
        "per_page": 30,
        "orientation": "portrait",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)

        if response.status_code != 200:
            print("Pexels error:", response.status_code, response.text[:300])
            return None

        photos = response.json().get("photos", [])
        if not photos:
            return None

        used = set(state.get("photo_used", []))
        fresh = [p for p in photos if str(p.get("id")) not in used]

        if not fresh:
            state["photo_used"] = []
            fresh = photos

        photo = random.choice(fresh)
        photo_id = str(photo.get("id"))
        state.setdefault("photo_used", []).append(photo_id)

        image_url = (
            photo.get("src", {}).get("large2x")
            or photo.get("src", {}).get("large")
            or photo.get("src", {}).get("portrait")
            or photo.get("src", {}).get("original")
        )

        if not image_url:
            return None

        image_response = requests.get(image_url, timeout=30)

        if image_response.status_code != 200:
            return None

        image = BytesIO(image_response.content)
        image.seek(0)
        return image

    except Exception as error:
        print("Pexels exception:", error)
        return None

# =========================================================
# POST
# =========================================================

def create_caption(text, theme_name, title=None, artist=None):
    emoji = random.choice(THEMES[theme_name]["emojis"])

    if title and artist:
        return f"{emoji} {text}\n\n🎧 {title} — {artist}{SIGNATURE}"

    return f"{emoji} {text}{SIGNATURE}"

async def send_photo(context, image, caption):
    if image is None:
        await context.bot.send_message(chat_id=CHANNEL, text=caption)
        return False

    try:
        await context.bot.send_photo(
            chat_id=CHANNEL,
            photo=image,
            caption=caption,
        )
        return True
    except Exception as error:
        print("Photo send error:", error)
        await context.bot.send_message(chat_id=CHANNEL, text=caption)
        return False

async def publish_post(context):
    state = load_state()

    if state.get("paused"):
        print("Posting paused.")
        return False

    theme_name = get_time_theme()
    text = choose_text(theme_name, state)

    post_number = state.get("post_count", 0)
    is_music_post = post_number % 2 == 1

    music_file = None
    title = None
    artist = None

    if is_music_post:
        music_file = choose_music(theme_name, state)
        if music_file:
            title, artist = get_song_metadata(music_file)

    caption = create_caption(
        text=text,
        theme_name=theme_name,
        title=title,
        artist=artist,
    )

    image = get_pexels_photo(theme_name, state)
    await send_photo(context, image, caption)

    if music_file:
        music_path = os.path.join(MUSIC_FOLDER, music_file)

        try:
            with open(music_path, "rb") as audio:
                extension = os.path.splitext(music_file)[1].lower()
                music_caption = f"🎧 {title} — {artist}\n🥀 silent ruins"

                if extension in (".mp3", ".m4a", ".ogg", ".wav"):
                    await context.bot.send_audio(
                        chat_id=CHANNEL,
                        audio=audio,
                        caption=music_caption,
                        title=title,
                        performer=artist,
                    )
                else:
                    await context.bot.send_document(
                        chat_id=CHANNEL,
                        document=audio,
                        caption=music_caption,
                    )

            state["music_count"] = state.get("music_count", 0) + 1

        except Exception as error:
            print("Music send error:", error)

    state["post_count"] = state.get("post_count", 0) + 1
    state["last_post"] = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")

    save_state(state)

    print(
        f"Published | theme={theme_name} | "
        f"music={bool(music_file)} | post={state['post_count']}"
    )
    return True

# =========================================================
# COMMANDS
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🥀 SilentRuins Bot is online 🖤")

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 Your Telegram ID:\n{update.effective_user.id}"
    )

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Access denied.")
        return

    success = await publish_post(context)
    await update.message.reply_text(
        "✅ Post published 🥀" if success else "⏸️ Posting is paused."
    )

async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    state = load_state()
    state["paused"] = True
    save_state(state)
    await update.message.reply_text("⏸️ SilentRuins paused 🖤")

async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    state = load_state()
    state["paused"] = False
    save_state(state)
    await update.message.reply_text("▶️ SilentRuins resumed 🥀")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    state = load_state()

    status = "⏸️ Paused" if state.get("paused") else "▶️ Running"

    await update.message.reply_text(
        f"🖤 SilentRuins Stats\n\n"
        f"Status: {status}\n"
        f"📤 Posts: {state.get('post_count', 0)}\n"
        f"🎧 Music posts: {state.get('music_count', 0)}\n"
        f"🎵 Music files: {len(get_music_files())}\n"
        f"🌑 Themes: {len(THEMES)}\n"
        f"📝 Texts: {sum(len(x['texts']) for x in THEMES.values())}\n"
        f"🖼 Photos used: {len(state.get('photo_used', []))}\n"
        f"🕐 Timezone: {TIMEZONE}\n\n"
        f"Last post:\n{state.get('last_post') or 'Never'}"
    )

async def songs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    files = get_music_files()

    if not files:
        await update.message.reply_text("🎵 No music files found.")
        return

    lines = ["🎵 Music library:\n"]

    for index, filename in enumerate(files, start=1):
        title, artist = get_song_metadata(filename)
        lines.append(f"{index}. {title} — {artist}")

    text = "\n".join(lines)

    # Telegram message limit protection
    if len(text) > 3900:
        text = text[:3900] + "\n..."

    await update.message.reply_text(text)

async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "🥀 SilentRuins Control Panel\n\nchoose your move 🖤",
        reply_markup=panel_keyboard(),
    )

def panel_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 POST", callback_data="post"),
            InlineKeyboardButton("📊 STATS", callback_data="stats"),
        ],
        [
            InlineKeyboardButton("⏸️ PAUSE", callback_data="pause"),
            InlineKeyboardButton("▶️ RESUME", callback_data="resume"),
        ],
    ])

async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("🚫 Access denied.")
        return

    state = load_state()

    if query.data == "post":
        success = await publish_post(context)
        await query.edit_message_text(
            "✅ Post published 🥀" if success else "⏸️ Posting is paused.",
            reply_markup=panel_keyboard(),
        )

    elif query.data == "pause":
        state["paused"] = True
        save_state(state)
        await query.edit_message_text(
            "⏸️ Automatic posting paused.",
            reply_markup=panel_keyboard(),
        )

    elif query.data == "resume":
        state["paused"] = False
        save_state(state)
        await query.edit_message_text(
            "▶️ Automatic posting resumed.",
            reply_markup=panel_keyboard(),
        )

    elif query.data == "stats":
        await query.edit_message_text(
            f"📊 SilentRuins\n\n"
            f"📤 Posts: {state.get('post_count', 0)}\n"
            f"🎧 Music: {state.get('music_count', 0)}\n"
            f"🎵 Songs: {len(get_music_files())}\n"
            f"🌑 Themes: {len(THEMES)}\n"
            f"🖼 Photos used: {len(state.get('photo_used', []))}\n"
            f"Status: {'⏸️ Paused' if state.get('paused') else '▶️ Running'}\n\n"
            f"🕒 Last post:\n{state.get('last_post') or 'Never'}",
            reply_markup=panel_keyboard(),
        )

# =========================================================
# RECEIVE MP3 FROM TELEGRAM
# =========================================================

async def receive_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    message = update.effective_message
    audio = message.audio

    if not audio:
        return

    original_name = audio.file_name or f"telegram_{audio.file_unique_id}.mp3"

    base, ext = os.path.splitext(original_name)
    if not ext:
        ext = ".mp3"

    if ext.lower() not in ALLOWED_AUDIO:
        ext = ".mp3"

    safe_base = re.sub(r'[\\/:*?"<>|]+', "_", base).strip()
    if not safe_base:
        safe_base = f"telegram_{audio.file_unique_id}"

    filename = f"{safe_base}{ext.lower()}"
    destination = os.path.join(MUSIC_FOLDER, filename)

    # Avoid overwriting an existing file.
    counter = 1
    while os.path.exists(destination):
        filename = f"{safe_base}_{counter}{ext.lower()}"
        destination = os.path.join(MUSIC_FOLDER, filename)
        counter += 1

    try:
        telegram_file = await audio.get_file()
        await telegram_file.download_to_drive(destination)

        title = audio.title or os.path.splitext(filename)[0]
        artist = audio.performer or "Unknown Artist"

        await message.reply_text(
            f"✅ Song added to library 🥀\n\n"
            f"🎧 {title}\n"
            f"👤 {artist}\n"
            f"📁 {filename}\n\n"
            f"Use /songs to see your music library."
        )

        print(f"New music added: {filename}")

    except Exception as error:
        print("Audio download error:", error)
        await message.reply_text(
            "❌ Could not save this audio file."
        )

# =========================================================
# MAIN
# =========================================================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing.")

    if not PEXELS_API_KEY:
        raise RuntimeError("PEXELS_API_KEY is missing.")

    if not ADMIN_IDS:
        print("WARNING: ADMIN_IDS is empty.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("post", post_now))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("songs", songs))
    app.add_handler(CommandHandler("panel", panel))

    # Receive MP3/audio files sent directly to the bot.
    app.add_handler(MessageHandler(filters.AUDIO, receive_audio))

    app.add_handler(CallbackQueryHandler(panel_callback))

    # One automatic post every hour.
    app.job_queue.run_repeating(
        publish_post,
        interval=3600,
        first=3600,
    )

    print("=" * 60)
    print("🥀 SilentRuins Bot is running...")
    print(f"🖤 Channel: {CHANNEL}")
    print("⏱ Posting: EVERY 1 HOUR")
    print("🎧 Music: EVERY 2 HOURS")
    print("🖼 Pexels: ENABLED")
    print(f"🌑 Themes: {len(THEMES)}")
    print("🎵 Telegram MP3 upload: ENABLED")
    print("🎛 Admin panel: ENABLED")
    print("=" * 60)

    app.run_polling()
