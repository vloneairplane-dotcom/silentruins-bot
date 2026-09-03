import os
import json
import random
import re
import threading

from io import BytesIO
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# ==========================
# CONFIG
# ==========================

load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")

CHANNEL = os.getenv(
    "CHANNEL",
    "@songsandscars"
)

PEXELS_KEY = os.getenv(
    "PEXELS_API_KEY"
)


ADMIN_IDS = {
    int(x)
    for x in os.getenv(
        "ADMIN_IDS",
        ""
    ).split(",")
    if x.strip().isdigit()
}


MUSIC_FOLDER = "music"

STATE_FILE = "state.json"


SIGNATURE = "\n\n— silent ruins 🥀"


os.makedirs(
    MUSIC_FOLDER,
    exist_ok=True
)



# ==========================
# THEMES
# ==========================

THEMES = [

    {
        "name": "midnight",
        "query": "dark midnight street cinematic",
        "texts": [
            "2:17 AM.\neveryone is asleep.\nmy mind isn't. 🌑",
            "the city sleeps.\nmy thoughts don't. 🌙",
            "some nights are too quiet\nto hide from yourself. 🕯️"
        ]
    },


    {
        "name": "rain",
        "query": "rainy night street cinematic",
        "texts": [
            "some nights only the rain understands. 🌧️",
            "the rain hides things we can't say. 🥀",
            "some memories sound like rain. 🖤"
        ]
    },


    {
        "name": "lonely",
        "query": "lonely street night cinematic",
        "texts": [
            "walking alone doesn't mean being lost. 🖤",
            "some roads remember our pain. 🌑"
        ]
    },


    {
        "name": "dark",
        "query": "dark room cinematic",
        "texts": [
            "silence sounds different at night. 🕯️",
            "empty rooms remember everything. 🖤"
        ]
    }

]



# ==========================
# STATE
# ==========================

def load_state():

    if not os.path.exists(
        STATE_FILE
    ):

        return {
            "posts": 0,
            "music": 0
        }


    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)


    except:

        return {
            "posts": 0,
            "music": 0
        }



def save_state(data):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )



def is_admin(user_id):

    return user_id in ADMIN_IDS



# ==========================
# HELPERS
# ==========================

def clean_filename(name):

    name = re.sub(
        r'[\\/:*?"<>|]+',
        "_",
        name
    )

    return name.strip()



def get_music():

    if not os.path.exists(
        MUSIC_FOLDER
    ):
        return []


    return [

        x

        for x in os.listdir(
            MUSIC_FOLDER
        )

        if x.lower().endswith(
            (
                ".mp3",
                ".wav",
                ".m4a",
                ".ogg"
            )
        )

    ]



def choose_theme():

    return random.choice(
        THEMES
    )


def create_caption(theme):

    text = random.choice(
        theme["texts"]
    )

    return (
        text
        +
        SIGNATURE
    )# ==========================
# PEXELS PHOTO
# ==========================

def get_photo(theme):

    if not PEXELS_KEY:
        return None


    try:

        url = "https://api.pexels.com/v1/search"


        headers = {
            "Authorization": PEXELS_KEY
        }


        params = {

            "query": theme["query"],

            "per_page": 10,

            "orientation": "portrait"

        }


        response = requests.get(

            url,

            headers=headers,

            params=params,

            timeout=20

        )


        data = response.json()


        photos = data.get(

            "photos",

            []

        )


        if not photos:

            return None



        selected = random.choice(

            photos

        )


        image_url = selected["src"]["large"]



        image = requests.get(

            image_url,

            timeout=20

        ).content



        return BytesIO(image)



    except Exception as e:


        print(

            "Photo error:",

            e

        )


        return None




# ==========================
# POST SYSTEM
# ==========================


async def publish(context):


    state = load_state()



    theme = choose_theme()



    caption = create_caption(

        theme

    )



    photo = get_photo(

        theme

    )



    try:


        if photo:


            photo.seek(0)


            await context.bot.send_photo(

                chat_id=CHANNEL,

                photo=photo,

                caption=caption

            )


        else:


            await context.bot.send_message(

                chat_id=CHANNEL,

                text=caption

            )




        songs = get_music()



        if songs:


            song = random.choice(

                songs

            )



            path = os.path.join(

                MUSIC_FOLDER,

                song

            )



            with open(

                path,

                "rb"

            ) as audio:



                await context.bot.send_audio(

                    chat_id=CHANNEL,

                    audio=audio,

                    caption="🎧 silent ruins 🥀"

                )



            state["music"] += 1





        state["posts"] += 1



        save_state(

            state

        )



        print(

            "Post sent"

        )



    except Exception as e:


        print(

            "Publish error:",

            e

        )# ==========================
# COMMANDS
# ==========================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🥀 SilentRuins Online"
    )



async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        str(
            update.effective_user.id
        )
    )



async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(
        update.effective_user.id
    ):
        return


    await publish(
        context
    )


    await update.message.reply_text(
        "✅ Posted"
    )



async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(
        update.effective_user.id
    ):
        return


    state = load_state()


    await update.message.reply_text(

        f"""
🥀 SilentRuins

Posts: {state.get("posts",0)}
Music: {state.get("music",0)}
Files: {len(get_music())}
"""

    )



# ==========================
# ADD SONG
# ==========================


async def addsong(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(
        update.effective_user.id
    ):
        return


    await update.message.reply_text(
        "🎧 آهنگ MP3 رو ارسال کن"
    )




async def receive_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(
        update.effective_user.id
    ):
        return



    audio = update.message.audio


    if not audio:

        return



    filename = audio.file_name



    if not filename:

        filename = (
            "song_"
            +
            audio.file_unique_id
            +
            ".mp3"
        )



    filename = clean_filename(
        filename
    )



    path = os.path.join(

        MUSIC_FOLDER,

        filename

    )



    number = 1



    while os.path.exists(path):


        name, ext = os.path.splitext(
            filename
        )


        path = os.path.join(

            MUSIC_FOLDER,

            f"{name}_{number}{ext}"

        )


        number += 1




    try:


        telegram_file = await audio.get_file()



        await telegram_file.download_to_drive(

            path

        )



        await update.message.reply_text(

            f"""
✅ ذخیره شد

🎧 {os.path.basename(path)}
"""

        )



        print(

            "New song:",

            path

        )



    except Exception as e:


        print(

            e

        )


        await update.message.reply_text(

            "❌ خطا در ذخیره آهنگ"

        )# ==========================
# RENDER WEB SERVER
# ==========================


class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.end_headers()

        self.wfile.write(
            b"SilentRuins is alive"
        )



def run_web_server():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )


    server = HTTPServer(

        (
            "0.0.0.0",
            port
        ),

        HealthHandler

    )


    print(
        f"Web server running on {port}"
    )


    server.serve_forever()



# ==========================
# MAIN
# ==========================


def main():


    if not BOT_TOKEN:

        raise Exception(
            "BOT_TOKEN missing"
        )



    threading.Thread(

        target=run_web_server,

        daemon=True

    ).start()




    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )


    # Commands


    app.add_handler(

        CommandHandler(

            "start",

            start

        )

    )



    app.add_handler(

        CommandHandler(

            "id",

            myid

        )

    )



    app.add_handler(

        CommandHandler(

            "post",

            post_now

        )

    )



    app.add_handler(

        CommandHandler(

            "stats",

            stats

        )

    )



    app.add_handler(

        CommandHandler(

            "addsong",

            addsong

        )

    )



    # Receive Music


    app.add_handler(

        MessageHandler(

            filters.AUDIO,

            receive_audio

        )

    )



    # Auto post every hour


    app.job_queue.run_repeating(

        publish,

        interval=3600,

        first=3600

    )



    print(
        """
========================

🥀 SilentRuins Started

Web Service: ON
Telegram: ON

========================
"""
    )



    app.run_polling()




if __name__ == "__main__":

    main()
