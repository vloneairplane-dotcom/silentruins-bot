"""SilentRuins Editorial Engine v5.

One principle: a post is a story, not three independent random assets.
Mood -> scene -> caption -> soundtrack -> final editorial score.
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SIGNATURE = "— silent ruins 🥀"

MOODS: dict[str, dict[str, Any]] = {
    "rain": {
        "fa": "بارون", "emoji": "🌧",
        "emojis": ["🌧", "☔", "🖤"], "visual": ["rain", "window", "wet", "street", "umbrella", "reflection"],
        "music": ["rain", "melancholy", "missing", "memories", "emotional", "night"],
        "queries": ["rainy window lonely cinematic", "person umbrella rainy street night", "rain reflection empty street", "rain window silhouette night"],
        "captions": [
            "باران که می‌گیرد، شهر آرام‌تر می‌شود و فکرها بلندتر.",
            "بعضی خاطره‌ها فقط با صدای باران برمی‌گردند.",
            "پشت این پنجره، خیلی چیزها گذشته؛ بعضی دلتنگی‌ها نه.",
            "باران می‌بارد و چیزی درون آدم دوباره بیدار می‌شود.",
            "گاهی فقط صدای باران می‌ماند و فکرهایی که تمام نمی‌شوند.",
            "بعضی شب‌ها، باران بیشتر از آدم‌ها حرف می‌زند.",
            "شهر خیس می‌شود؛ خاطره‌ها اما خیس نمی‌خورند.",
            "باران می‌آید تا سکوت، کمی قابل‌تحمل‌تر شود.",
            "هر پنجره‌ی خیس، انگار یک خاطره را دوباره نشان می‌دهد.",
            "امشب باران می‌بارد و دلم هیچ توضیحی نمی‌خواهد.",
            "صدای باران گاهی شبیه صدای کسی‌ست که دیگر نیست.",
            "خیابان خیس بود و من هنوز دنبال یک خاطره می‌گشتم.",
            "بعضی عصرها فقط یک پنجره و کمی باران کم دارند.",
            "باران همه‌چیز را می‌شوید، جز چیزهایی که در ذهن مانده‌اند.",
            "امشب حتی باران هم نتوانست این فکر را از سرم ببرد.",
        ],
    },
    "night": {
        "fa": "شب", "emoji": "🌃",
        "emojis": ["🌙", "🌃", "🖤"], "visual": ["night", "moon", "dark", "city", "silhouette", "neon", "street"],
        "music": ["night", "dark", "melancholy", "loneliness", "emotional", "memories"],
        "queries": ["lonely person city night cinematic", "moon silhouette dark night", "empty road night lone figure", "woman window city night dark"],
        "captions": [
            "شب، جایی‌ست که فکرهای نگفته فرصت برگشتن پیدا می‌کنند.",
            "نیمه‌شب که می‌رسد، بعضی نبودن‌ها واضح‌تر می‌شوند.",
            "همه خوابیده‌اند و ذهن تو هنوز با گذشته حرف می‌زند.",
            "بعضی شب‌ها برای خواب نیستند؛ برای فکر کردن‌اند.",
            "چراغ‌های شهر روشن‌اند، اما بعضی دل‌ها هنوز تاریک‌اند.",
            "شب همیشه آرام نیست؛ گاهی فقط ساکت است.",
            "ساعت از نیمه‌شب گذشته و یک خاطره هنوز بیدار است.",
            "گاهی سکوت شب، تمام حرف‌هایی‌ست که نگفتی.",
            "شب که طولانی می‌شود، آدم بیشتر خودش را می‌شنود.",
            "بعضی فکرها فقط بعد از خاموش شدن همه‌چیز شروع می‌شوند.",
            "در تاریکی شب، نبودن بعضی آدم‌ها بیشتر دیده می‌شود.",
            "شهر بیدار بود و من هنوز با یک خاطره کلنجار می‌رفتم.",
            "نیمه‌شب برای بعضی‌ها پایان روز است؛ برای بعضی‌ها شروع فکرها.",
            "چراغ‌ها روشن بودند، اما هیچ‌کدام راه برگشت را نشان نمی‌دادند.",
            "بعضی شب‌ها فقط می‌خواهی کسی بگوید هنوز اینجاست.",
        ],
    },
    "lonely": {
        "fa": "تنهایی", "emoji": "🚶",
        "emojis": ["🚶", "🌫", "🖤"], "visual": ["alone", "lonely", "silhouette", "empty", "bench", "room", "window", "distance"],
        "music": ["loneliness", "lonely", "missing", "emotional", "dark", "memories", "night"],
        "queries": ["person alone window cinematic", "lonely silhouette empty room", "single person bench fog night", "person walking alone dark street"],
        "captions": [
            "تنهایی همیشه نبودن آدم‌ها نیست؛ گاهی نبودنِ یک نفر است.",
            "میان آدم‌های زیادی بودم، اما هیچ‌کس شبیه خانه نبود.",
            "بعضی سکوت‌ها از جایی شروع می‌شوند که دیگر حرف زدنت فایده ندارد.",
            "آدم به تنهایی عادت نمی‌کند؛ فقط یاد می‌گیرد پنهانش کند.",
            "گاهی دلت نمی‌خواهد کسی بیاید؛ فقط می‌خواهی کسی بماند.",
            "سخت‌ترین بخش تنهایی، عادت کردن به نداشتنِ یک نفر است.",
            "همه‌چیز سر جایش بود، جز کسی که باید کنارم می‌بود.",
            "تنهایی یعنی هزار حرف داشته باشی و هیچ‌کس را صدا نزنی.",
            "بعضی آدم‌ها می‌روند و بعد، سکوت جای صدایشان را می‌گیرد.",
            "گاهی آدم فقط دلش یک حضور ساده می‌خواهد؛ نه یک معجزه.",
            "آدم می‌تواند وسط شلوغی هم صدای تنهایی خودش را بشنود.",
            "بدترین قسمت تنهایی، نبودن کسی نیست؛ عادت کردن به نبودنش است.",
            "گاهی فقط یک صندلی خالی کافی‌ست تا همه‌چیز یادت بیاید.",
            "کسی نپرسید چه شد؛ من هم کم‌کم یاد گرفتم چیزی نگویم.",
            "بعضی شب‌ها دلت برای یک نفر تنگ نیست؛ برای حسِ بودنش تنگ است.",
        ],
    },
    "love": {
        "fa": "دلتنگی", "emoji": "🥀",
        "emojis": ["🥀", "💔", "🖤"], "visual": ["rose", "letter", "photograph", "distance", "empty bed", "goodbye", "memory"],
        "music": ["heartbreak", "missing", "breakup", "regret", "romantic", "unrequited love", "betrayal", "emotional", "memories"],
        "queries": ["withered rose dark cinematic", "old photograph lonely dark room", "letter candle empty room", "person looking out window heartbreak"],
        "captions": [
            "دلتنگی از جایی سخت می‌شود که دیگر راهی برای برگشتن نیست.",
            "بعضی آدم‌ها می‌روند، اما عادتِ دوست داشتنشان می‌ماند.",
            "گاهی دلت برای خودِ آدم تنگ نیست؛ برای روزهایی‌ست که با او داشتی.",
            "فاصله همیشه بین دو شهر نیست؛ گاهی بین دو آدم است.",
            "بعضی آهنگ‌ها هنوز همان جایی تمام می‌شوند که تو را یاد او می‌اندازند.",
            "تمام شد، اما بعضی چیزها بلد نیستند تمام شوند.",
            "دلتنگی آرام نمی‌آید؛ وسط یک شب معمولی پیدایش می‌شود.",
            "بعضی خاطره‌ها قدیمی می‌شوند، اما بی‌اهمیت نه.",
            "گاهی باید با نبودنِ کسی کنار بیایی، نه با فراموش کردنش.",
            "آخر بعضی رابطه‌ها، فقط یک جای خالی باقی می‌ماند.",
            "هنوز بعضی آهنگ‌ها مرا به جایی می‌برند که تو آنجا بودی.",
            "دو نفر می‌توانند از هم دور شوند، قبل از اینکه خداحافظی کنند.",
            "گاهی چیزی که دلت برایش تنگ شده، خودِ گذشته است.",
            "بعضی اسم‌ها بعد از رفتنشان هم از ذهن پاک نمی‌شوند.",
            "کاش بعضی خاطره‌ها فقط خاطره می‌ماندند و دوباره درد نمی‌گرفتند.",
        ],
    },
    "tired": {
        "fa": "خستگی", "emoji": "🕯",
        "emojis": ["🕯", "🌫", "🖤"], "visual": ["tired", "eyes", "head down", "candle", "hood", "exhausted", "smoke"],
        "music": ["breakdown", "depression", "emotional", "loneliness", "melancholy", "regret"],
        "queries": ["tired person dark room cinematic", "head down silhouette night", "candle dark room lonely", "person sitting alone exhausted"],
        "captions": [
            "بعضی خستگی‌ها با خواب خوب نمی‌شوند؛ با آرام شدنِ ذهن چرا.",
            "گاهی فقط دوام آوردن، بیشتر از چیزی که فکر می‌کنی انرژی می‌گیرد.",
            "از توضیح دادن خسته که می‌شوی، سکوت ساده‌ترین جواب می‌شود.",
            "بعضی شب‌ها فقط می‌خواهی همه‌چیز برای چند ساعت ساکت شود.",
            "فکر زیاد، حتی یک شب آرام را هم طولانی می‌کند.",
            "گاهی آدم خسته نیست؛ فقط دیگر توانِ وانمود کردن ندارد.",
            "حرف‌های نگفته گاهی از خودِ خستگی سنگین‌ترند.",
            "بعضی روزها هیچ اتفاق بدی نمی‌افتد؛ فقط خودت دیگر توان نداری.",
            "سکوت همیشه آرامش نیست؛ گاهی شکلِ خستگی‌ست.",
            "گاهی فاصله گرفتن از همه، تنها راه شنیدن صدای خودت است.",
            "امروز چیزی نشکست؛ فقط من کمی بیشتر از دیروز خسته‌ام.",
            "گاهی حتی جواب دادن به یک پیام هم انرژی زیادی می‌خواهد.",
            "خستگیِ واقعی وقتی‌ست که حتی توضیح دادنش هم سخت باشد.",
            "بعضی روزها فقط باید از خودت انتظار کمتری داشته باشی.",
            "ذهن شلوغ، حتی در آرام‌ترین اتاق هم جای استراحت نمی‌گذارد.",
        ],
    },
    "ruins": {
        "fa": "ویرونه", "emoji": "🏚",
        "emojis": ["🏚", "🍂", "🌫"], "visual": ["ruins", "abandoned", "fog", "old", "broken", "forest", "gothic"],
        "music": ["melancholy", "dark", "memories", "depression", "night", "emotional"],
        "queries": ["abandoned house fog cinematic", "old ruins moonlight dark", "misty forest abandoned place", "broken window abandoned building"],
        "captions": [
            "بعضی چیزها یک‌باره خراب نمی‌شوند؛ کم‌کم از درون خالی می‌شوند.",
            "هر ویرانه‌ای زمانی جای زندگیِ کسی بوده است.",
            "در بعضی خرابه‌ها، خاطره هنوز از دیوارها محکم‌تر است.",
            "گذشته از بعضی جاها می‌رود، اما ردش روی دیوارها می‌ماند.",
            "جایی که چراغی نمانده، هنوز می‌شود ردِ زندگی را پیدا کرد.",
            "بعضی پایان‌ها شبیه خانه‌ای متروک‌اند؛ ساکت، اما پر از ردپا.",
            "زمان همه‌چیز را نمی‌برد؛ بعضی چیزها را فقط خاموش می‌کند.",
            "گاهی آدم شبیه یک خانه‌ی قدیمی می‌شود؛ ساکت و پر از خاطره.",
            "مه که می‌آید، فاصله‌ی میان گذشته و امروز کمتر می‌شود.",
            "ویرانه‌ها یادآوری می‌کنند که حتی زیباترین چیزها هم ممکن است تغییر کنند.",
            "بعضی دیوارها فرو ریخته‌اند، اما خاطره هنوز ایستاده است.",
            "جای بعضی آدم‌ها در زندگی، شبیه خانه‌ای‌ست که کلیدش دیگر به هیچ دری نمی‌خورد.",
            "چیزی که خراب شده همیشه بی‌ارزش نیست؛ گاهی فقط تمام شده است.",
            "در سکوت یک جای متروک، گذشته هنوز نفس می‌کشد.",
            "بعضی ویرانه‌ها از آدم‌ها بیشتر راز نگه می‌دارند.",
        ],
    },
}

MOOD_ALIASES = {
    "rain": ["rain", "بارون", "باران", "barun", "baran", "baroon"],
    "night": ["night", "شب", "shab", "midnight"],
    "lonely": ["lonely", "تنها", "تنهایی", "tanha", "tanhai"],
    "love": ["love", "دلتنگ", "عشق", "خاطره", "جدایی", "deltang", "eshgh", "khatere"],
    "tired": ["tired", "خسته", "خستگی", "khaste"],
    "ruins": ["ruins", "ویرونه", "خرابه", "مه", "virane", "kharabe"],
}

MOOD_MUSIC_MAP = {
    "heartbreak": {"love", "lonely", "night"}, "breakup": {"love", "lonely"},
    "missing": {"love", "lonely", "night", "rain"}, "memories": {"love", "lonely", "night", "rain", "ruins"},
    "emotional": {"night", "lonely", "love", "tired", "rain"}, "romantic": {"love"},
    "unrequited love": {"love", "lonely"}, "regret": {"love", "tired", "lonely"},
    "betrayal": {"love", "lonely", "tired"}, "distance": {"love", "lonely", "night"},
    "breakdown": {"tired", "lonely", "night"}, "depression": {"tired", "lonely", "ruins", "night"},
    "sadness": {"rain", "tired", "lonely", "night"}, "melancholy": {"rain", "night", "lonely", "ruins", "tired"},
    "dark": {"night", "ruins", "lonely"}, "loneliness": {"lonely", "night", "ruins"},
    "lonely": {"lonely", "night"}, "night": {"night", "lonely"}, "rain": {"rain", "night"},
}

BAD_VISUAL = {"party", "festival", "wedding", "birthday", "selfie", "influencer", "vacation", "bunny", "rabbit ears", "toy", "costume", "cartoon"}
GOOD_VISUAL = {"person", "silhouette", "alone", "lonely", "window", "night", "rain", "street", "shadow", "empty", "moon", "fog", "room", "reflection"}


def normalize(value: str | None) -> str:
    s = (value or "").lower().replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    s = re.sub(r"[\u200c\u200f\u200e]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(value: str | None) -> set[str]:
    return set(re.findall(r"[\w\u0600-\u06ff-]+", normalize(value)))


def _contains(text: str, words: list[str] | set[str]) -> int:
    return sum(1 for w in words if normalize(w) and normalize(w) in text)


def choose_mood(state: dict, hour: int | None = None) -> str:
    hour = datetime.now().hour if hour is None else hour
    if 22 <= hour or hour < 5:
        base = ["night", "lonely", "love", "ruins"]
    elif 17 <= hour < 22:
        base = ["love", "lonely", "night", "rain", "ruins"]
    elif 12 <= hour < 17:
        base = ["tired", "love", "rain", "lonely"]
    else:
        base = ["rain", "tired", "love", "lonely"]
    recent = list(state.get("recent_moods", []))[-3:]
    choices = [m for m in base if m not in recent[-1:]] or base
    return random.choice(choices)


def caption_score(caption: str, mood: str) -> float:
    text = normalize(caption)
    score = 0.72
    n = len(text)
    if 35 <= n <= 125: score += 0.10
    elif n < 22 or n > 170: score -= 0.10
    if 6 <= len(tokens(text)) <= 22: score += 0.06
    if _contains(text, MOOD_ALIASES[mood]) >= 1: score += 0.08
    if text.count("!") > 1 or text.count("#"): score -= 0.08
    return max(0, min(1, score))


def music_score(track: dict | None, mood: str) -> float:
    if not track: return 0.30
    tagged = normalize(track.get("mood"))
    if tagged == mood: return 1.0
    if mood in MOOD_MUSIC_MAP.get(tagged, set()): return 0.94
    combined = normalize(f"{track.get('title','')} {track.get('performer','')} {tagged}")
    hits = _contains(combined, MOOD_ALIASES[mood])
    return min(0.84, 0.52 + hits * 0.10)


def image_score(photo: dict | None, mood: str) -> float:
    if not photo: return 0.40
    text = normalize(f"{photo.get('query','')} {photo.get('alt','')}")
    good = _contains(text, GOOD_VISUAL)
    bad = _contains(text, BAD_VISUAL)
    visual = _contains(text, MOODS[mood]["visual"])
    score = 0.58 + min(.15, good*.025) + min(.16, visual*.04) - min(.25, bad*.09)
    lum = photo.get("luminance")
    if isinstance(lum, (int,float)):
        if 40 <= lum <= 85: score += .10
        elif lum < 28: score -= .12
        elif lum > 145: score -= .08
    return max(0, min(1, score))


def coherence(caption: str, mood: str, track: dict | None, photo: dict | None) -> float:
    text = normalize(caption)
    mood_signal = min(1, .55 + _contains(text, MOOD_ALIASES[mood])*.10)
    return max(0, min(1, mood_signal*.32 + music_score(track,mood)*.36 + image_score(photo,mood)*.32))


def quality_score(mood: str, caption: str, track: dict | None, photo: dict | None) -> dict:
    t = caption_score(caption,mood); m = music_score(track,mood); i = image_score(photo,mood); c = coherence(caption,mood,track,photo)
    overall = round((t*.30+i*.22+m*.30+c*.18)*100)
    return {"text":round(t*100),"image":round(i*100),"music":round(m*100),"coherence":round(c*100),"overall":max(0,min(100,overall))}


def signature(mood: str, caption: str, track: dict | None, image_url: str | None) -> str:
    raw = "|".join([mood, normalize(caption), str((track or {}).get("file_id","")), str(image_url or "")])
    return hashlib.sha256(raw.encode()).hexdigest()


def choose_caption(mood: str, recent_hashes: list[str]) -> str:
    pool = MOODS[mood]["captions"][:]
    random.shuffle(pool)
    for caption in pool:
        h = hashlib.sha256(normalize(caption).encode()).hexdigest()
        if h not in set(recent_hashes[-20:]): return caption
    return random.choice(pool)


def choose_music(tracks: list[dict], mood: str, recent_ids: list[str], preview_ids: list[str] | None = None) -> dict | None:
    if not tracks: return None
    blocked = set(recent_ids[-8:]) | set((preview_ids or [])[-20:])
    fresh = [t for t in tracks if t.get("file_id") not in blocked] or [t for t in tracks if t.get("file_id") not in set(recent_ids[-8:])] or tracks[:]
    ranked = sorted(fresh, key=lambda t: music_score(t,mood), reverse=True)
    top = ranked[:min(8,len(ranked))]
    return random.choice(top)
