import os
import json
import random
import re
import threading
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)


# =========================================================
# CONFIG
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

CHANNEL = "@songsandscars"

MUSIC_FOLDER = "music"
STATE_FILE = "state.json"

TIMEZONE = "Asia/Tehran"

SIGNATURE = "\n\n— silent ruins 🥀"


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
            "lonely silhouette night"
        ],
        "texts": [
            "2:17 AM.\neveryone is asleep.\nmy mind isn't. 🌑",
            "the city sleeps.\nmy thoughts don't. 🌙",
            "some nights are too quiet\nto hide from yourself. 🕯️",
            "at night,\neverything you buried learns how to speak. 🖤",
            "it's always louder after midnight.\nthe memories.\nthe silence.\nme. 🌑",
            "another night.\nanother conversation with the thoughts i can't escape. 🌙"
        ]
    },

    "rain": {
        "emojis": ["🌧️", "☔", "🥀", "🖤"],
        "queries": [
            "lonely person rain cinematic",
            "rainy night street film photography",
            "person under rain dark aesthetic",
            "rain window lonely night",
            "city rain cinematic night"
        ],
        "texts": [
            "some nights,\nyou don't need someone.\nyou just need the rain to be louder. 🌧️",
            "the rain never asks\nwhy you're still awake. ☔",
            "i like rainy nights.\nthey make loneliness look beautiful. 🥀",
            "maybe that's why i love the rain.\nit knows how to fall apart quietly. 🌧️",
            "some memories sound like rain\nhitting a window at 3 AM. 🖤",
            "i watched the rain\nand remembered everything i was trying to forget. 🌧️"
        ]
    },

    "cigarette": {
        "emojis": ["🚬", "🖤", "🌑", "🥀"],
        "queries": [
            "man cigarette night cinematic",
            "smoking alone night photography",
            "cigarette dark portrait film",
            "lonely smoker rainy night",
            "smoking silhouette night"
        ],
        "texts": [
            "one cigarette.\none memory.\nwhole night gone. 🚬",
            "some habits aren't addictions.\nsometimes they're reminders. 🖤",
            "i don't smoke to forget.\ni smoke because remembering got heavy. 🚬",
            "the room was quiet.\nthe cigarette wasn't. 🌑",
            "smoke disappears faster than people do. 🥀",
            "some nights taste like smoke\nand things left unsaid. 🚬"
        ]
    },

    "night_drive": {
        "emojis": ["🚘", "🌃", "🌑", "🎧"],
        "queries": [
            "lonely night drive cinematic",
            "car driving night rain film",
            "empty highway night cinematic",
            "city lights car night",
            "night road lonely photography"
        ],
        "texts": [
            "sometimes you don't need a destination.\nyou just need to keep driving. 🚘",
            "the road was empty.\nmy head wasn't. 🌃",
            "late night drives fix things\nthat conversations can't. 🎧",
            "no calls.\nno messages.\njust music and headlights. 🌑",
            "i drove until the city disappeared\nand my thoughts finally got quiet. 🚘",
            "some roads only exist\nwhen you're trying to outrun yourself. 🖤"
        ]
    },

    "neon_city": {
        "emojis": ["🌃", "💜", "🖤", "🌑"],
        "queries": [
            "neon city night lonely cinematic",
            "dark cyberpunk street photography",
            "neon lights rainy street",
            "lonely city night cinematic",
            "urban night neon film"
        ],
        "texts": [
            "millions of lights.\nstill somehow lonely. 🌃",
            "the city knows how to make loneliness look beautiful. 🖤",
            "everyone was somewhere.\ni was nowhere. 🌑",
            "neon lights.\nempty streets.\nthe same old thoughts. 💜",
            "the city never sleeps.\nsome people just become better at hiding. 🌃",
            "surrounded by thousands of faces.\nstill looking for one. 🖤"
        ]
    },

    "empty_room": {
        "emojis": ["🕯️", "🪟", "🖤", "🥀"],
        "queries": [
            "empty dark room window cinematic",
            "lonely bedroom night photography",
            "dark room chair window rain",
            "empty room moody film photography",
            "lonely room lamp night"
        ],
        "texts": [
            "the room is empty.\nthe memories aren't. 🕯️",
            "some rooms remember people\nbetter than we do. 🪟",
            "silence feels different\nwhen nobody is coming back. 🖤",
            "i left the room.\nsomehow the memories followed. 🥀",
            "an empty room can still feel crowded\nwith everything you lost. 🕯️",
            "nothing changed in the room.\neverything changed in me. 🪟"
        ]
    },

    "moon": {
        "emojis": ["🌙", "🌌", "🖤", "✨"],
        "queries": [
            "moon night dark cinematic",
            "lonely person under moonlight",
            "moon clouds dark photography",
            "night sky lonely aesthetic",
            "silhouette moon cinematic"
        ],
        "texts": [
            "the moon has seen every version of me. 🌙",
            "some nights\ni only trust the sky. 🌌",
            "maybe loneliness isn't empty.\nmaybe it's just quiet. 🌙",
            "the moon stays.\npeople don't. 🖤",
            "same moon.\ndifferent life.\ndifferent me. ✨",
            "i looked at the sky\nand wondered who was looking at the same moon. 🌙"
        ]
    },

    "breakup": {
        "emojis": ["🥀", "🩶", "🖤", "💔"],
        "queries": [
            "breakup cinematic photography",
            "sad couple silhouette night",
            "lost love dark cinematic",
            "person alone after breakup",
            "goodbye couple rainy night"
        ],
        "texts": [
            "the worst part wasn't losing you.\nit was losing myself trying to keep you. 🥀",
            "you didn't break my heart.\nyou changed what i expect from people. 🩶",
            "i still remember.\ni just stopped going back. 🖤",
            "some goodbyes happen\nlong before people actually leave. 💔",
            "you were a beautiful mistake\ni'm glad i survived. 🥀",
            "i loved you.\nthen i learned how to love myself more. 🖤"
        ]
    },

    "nostalgia": {
        "emojis": ["📼", "🕯️", "🥀", "🌙"],
        "queries": [
            "nostalgic 35mm film photography",
            "old street rainy night vintage",
            "nostalgic childhood film aesthetic",
            "old room nostalgia photography",
            "vintage night city"
        ],
        "texts": [
            "we didn't know those were the good days.\nwe just thought they were normal. 🕯️",
            "one song can bring back a whole person. 🎧",
            "i miss the version of me\nthat didn't know how things end. 🥀",
            "some memories don't hurt.\nthey just refuse to leave. 🌙",
            "the past never knocks.\nit just walks in when a song starts. 📼",
            "i don't miss yesterday.\ni miss who i was in it. 🖤"
        ]
    },

    "lonely_street": {
        "emojis": ["🚶", "🌑", "🖤", "🌃"],
        "queries": [
            "lonely person empty street cinematic",
            "walking alone city night",
            "empty street dark film photography",
            "alone man street night",
            "lonely silhouette urban night"
        ],
        "texts": [
            "i learned how to walk alone\nwithout looking back. 🚶",
            "some streets feel familiar\nbecause you've cried there before. 🌑",
            "the loneliest walks\nare the ones nobody knows about. 🖤",
            "i kept walking.\nnot because i knew where i was going.\nbecause stopping hurt more. 🚶",
            "empty streets understand people better than crowded rooms. 🌃",
            "sometimes getting lost\nis the only way to find yourself. 🖤"
        ]
    },

    "cold": {
        "emojis": ["🩶", "❄️", "🖤", "⛓️"],
        "queries": [
            "cold dark urban cinematic",
            "black white lonely man photography",
            "cold city night film",
            "hooded man dark street",
            "winter lonely cinematic"
        ],
        "texts": [
            "i don't have trust issues.\ni have memories. 🩶",
            "i became colder\nwhen being soft kept costing me. ❄️",
            "no anger.\nno revenge.\njust distance. ⛓️",
            "i remember who stayed.\ni remember who disappeared. 🖤",
            "i don't hate people.\ni just know what they're capable of. 🩶",
            "i got harder to reach\nbecause i got tired of being easy to hurt. ⛓️"
        ]
    },

    "ocean_fog": {
        "emojis": ["🌊", "🌫️", "🖤", "🌙"],
        "queries": [
            "dark ocean fog cinematic",
            "lonely ocean night photography",
            "foggy sea dark aesthetic",
            "person ocean night cinematic",
            "dark beach lonely film"
        ],
        "texts": [
            "some feelings are like the ocean.\nyou can see them.\nyou just can't measure them. 🌊",
            "the fog made everything disappear.\nexcept the thoughts i wanted gone. 🌫️",
            "i stood by the ocean\nand let it keep my secrets. 🖤",
            "there's something honest about the sea.\nit never pretends to be calm. 🌊",
            "maybe i needed the horizon\nbecause everything behind me hurt. 🌙",
            "the ocean was loud enough\nto hide every word i couldn't say. 🌊"
        ]
    },

    "dark_romance": {
        "emojis": ["🥀", "🖤", "🕯️", "🌹"],
        "queries": [
            "dark romance couple cinematic",
            "romantic shadows film photography",
            "dark couple silhouette night",
            "moody romantic photography",
            "couple candlelight dark aesthetic"
        ],
        "texts": [
            "i wanted forever.\nyou wanted something temporary. 🥀",
            "some people feel like home\nright before they become a memory. 🖤",
            "loving you was easy.\nforgetting you wasn't. 🌹",
            "you were my favorite place\nto get lost. 🕯️",
            "we looked beautiful together.\nthat doesn't mean we belonged together. 🥀",
            "some love stories end.\nsome just stop being spoken about. 🖤"
        ]
    }
}


# =========================================================
# SONG DATABASE
# =========================================================

SONGS = {
    "Lorde - Supercut": ["nostalgia", "breakup", "dark_romance"],
    "The Weeknd - Call Out My Name": ["breakup", "dark_romance", "midnight"],
    "Lorde - Writer in the Dark": ["breakup", "midnight", "dark_romance"],
    "Hozier - Unknown / Nth": ["breakup", "dark_romance", "cold"],
    "The Weeknd - Echoes of Silence": ["midnight", "empty_room", "breakup"],
    "Hozier - Cherry Wine (Live)": ["dark_romance", "nostalgia"],
    "Hozier - Work Song": ["dark_romance", "nostalgia"],
    "Coldplay - Sparks": ["nostalgia", "dark_romance", "midnight"],
    "Lorde - Liability": ["lonely_street", "empty_room"],
    "Bon Iver & St. Vincent - Roslyn": ["ocean_fog", "nostalgia", "midnight"],
    "The Cinematic Orchestra - To Build a Home": ["empty_room", "nostalgia", "dark_romance"],
    "Ludovico Einaudi - Nuvole Bianche": ["rain", "midnight", "ocean_fog"],
    "Cigarettes After Sex - Heavenly": ["dark_romance", "midnight", "nostalgia"],
    "Cigarettes After Sex - Sweet": ["dark_romance", "nostalgia"],
    "Daughter - Medicine": ["rain", "midnight"],
    "Daughter - Smother": ["empty_room", "dark_romance"],
    "Daughter - Youth": ["nostalgia", "rain"],
    "AURORA - Runaway": ["lonely_street", "night_drive", "ocean_fog"],
    "Mitski - First Love / Late Spring": ["dark_romance", "nostalgia"],
    "Mitski - I Bet on Losing Dogs": ["lonely_street", "midnight"],
    "Mitski - Francis Forever": ["nostalgia", "breakup", "rain"],
    "Mitski - Class of 2013": ["nostalgia", "empty_room"],
    "Adele - Love in the Dark": ["breakup", "dark_romance", "midnight"],
    "The Weeknd - Until I Bleed Out": ["midnight", "cold"],
    "Arctic Monkeys - I Wanna Be Yours": ["dark_romance", "midnight"],
    "Joji - Slow Dancing in the Dark": ["dark_romance", "midnight", "breakup"],
    "Coldplay - The Scientist": ["nostalgia", "breakup", "rain"],
    "Arctic Monkeys - 505": ["night_drive", "dark_romance", "nostalgia"],
    "Arctic Monkeys - Do I Wanna Know?": ["dark_romance", "night_drive", "midnight"],
    "Arctic Monkeys - Why'd You Only Call Me When You're High?": ["night_drive", "neon_city", "midnight"],
    "Coldplay - Fix You": ["rain", "dark_romance"],
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
        return DEFAULT_STATE.copy()

    try:

        with open(STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)

        for key, value in DEFAULT_STATE.items():

            if key not in state:
                state[key] = value

        return state

    except Exception as error:

        print(f"State error: {error}")

        return DEFAULT_STATE.copy()


def save_state(state):

    with open(STATE_FILE, "w", encoding="utf-8") as file:

        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2
        )


# =========================================================
# ADMIN
# =========================================================

def is_admin(user_id):

    return user_id in ADMIN_IDS


# =========================================================
# TIME THEME
# =========================================================

def get_time_theme():

    hour = datetime.now(
        ZoneInfo(TIMEZONE)
    ).hour

    if 0 <= hour < 6:

        return random.choice([
            "midnight",
            "rain",
            "cigarette",
            "moon",
            "empty_room"
        ])

    if 6 <= hour < 12:

        return random.choice([
            "nostalgia",
            "ocean_fog",
            "lonely_street"
        ])

    if 12 <= hour < 18:

        return random.choice([
            "cold",
            "lonely_street",
            "neon_city",
            "rain"
        ])

    if 18 <= hour < 22:

        return random.choice([
            "dark_romance",
            "night_drive",
            "neon_city",
            "breakup"
        ])

    return random.choice([
        "midnight",
        "breakup",
        "dark_romance",
        "night_drive",
        "cigarette"
    ])


# =========================================================
# TEXT
# =========================================================

def choose_text(theme_name, state):

    theme = THEMES[theme_name]

    used = set(state.get("text_used", []))

    available = []

    for text in theme["texts"]:

        text_id = f"{theme_name}::{text}"

        if text_id not in used:

            available.append((text_id, text))

    if not available:

        available = [
            (f"{theme_name}::{text}", text)
            for text in theme["texts"]
        ]

    selected_id, selected_text = random.choice(available)

    state["text_used"].append(selected_id)

    return selected_text


# =========================================================
# MUSIC FILES
# =========================================================

def get_music_files():

    if not os.path.exists(MUSIC_FOLDER):
        return []

    allowed = (
        ".mp3",
        ".m4a",
        ".flac",
        ".wav",
        ".ogg"
    )

    return sorted([
        filename
        for filename in os.listdir(MUSIC_FOLDER)
        if filename.lower().endswith(allowed)
    ])


# =========================================================
# SONG METADATA
# =========================================================

def get_song_metadata(filename):

    name = os.path.splitext(filename)[0]

    name = name.replace("_", " ")
    name = name.replace("–", "-")
    name = name.replace("—", "-")

    name = re.sub(r"\s+", " ", name).strip()

    # حذف شماره ابتدای فایل
    name = re.sub(
        r"^\s*\d+\s*[-_.]?\s*",
        "",
        name
    )

    # حذف کیفیت
    name = re.sub(
        r"\s*\(?\b(128|192|256|320)\s*(kbps)?\)?\s*$",
        "",
        name,
        flags=re.IGNORECASE
    )

    # تطبیق مستقیم با بانک آهنگ‌ها
    normalized = name.lower()

    for song_name in SONGS:

        if song_name.lower() == normalized:

            artist, title = song_name.split(" - ", 1)

            return title, artist

    # تطبیق تقریبی
    for song_name in SONGS:

        if song_name.lower() in normalized:

            artist, title = song_name.split(" - ", 1)

            return title, artist

    # حالت Artist - Title
    parts = [
        x.strip()
        for x in re.split(r"\s+-\s+", name)
        if x.strip()
    ]

    if len(parts) >= 2:

        return " - ".join(parts
