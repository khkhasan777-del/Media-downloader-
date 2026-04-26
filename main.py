"""
main.py — Your Telegram Media Downloader Bot
Just run: python main.py
"""

import logging
import asyncio
import re
import random
import json
import time
import uuid
from pathlib import Path
from functools import wraps
from collections import defaultdict

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMember,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction
from telegram.error import TelegramError

import yt_dlp

# ═══════════════════════════════════════════════════════════════════════════════
#   CONFIG — Fill in your details here
# ═══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN = "8258016908:AAFxKdNXbDGW1HLw-Tiw_QN7OMKifIPH2Vg"
# Get from @BotFather on Telegram

ADMIN_IDS = [7578834050]
# Get your ID from @userinfobot on Telegram
# Multiple admins: [123456789, 987654321]

FORCE_JOIN_CHANNELS = ["@suvarq"]
# Channels users must join before using bot
# Multiple: ["@channel1", "@channel2"]
# Disable: []

SPOTIFY_CLIENT_ID     = "8c543f45cdf349e98158e3c41db64d34"
SPOTIFY_CLIENT_SECRET = "05af202b792e4df8afa8c497b64468f3"
# Get free from developer.spotify.com/dashboard
# Leave as "" if you don't want Spotify support

DONATION_QR = "assets/donation_qr.png"
# Put your QR photo in the assets/ folder named donation_qr.png

# ═══════════════════════════════════════════════════════════════════════════════
#   DON'T TOUCH ANYTHING BELOW — THE WHOLE BOT IS HERE
# ═══════════════════════════════════════════════════════════════════════════════

DOWNLOAD_DIR        = "downloads"
MAX_FILE_SIZE_MB    = 50
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW   = 60
CHANNELS_DB_PATH    = "data/channels.json"

# ── Folders ──────────────────────────────────────────────────────────────────
for folder in ["downloads", "data", "logs", "assets"]:
    Path(folder).mkdir(parents=True, exist_ok=True)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#   MESSAGES & UX
# ═══════════════════════════════════════════════════════════════════════════════

WELCOME_MESSAGE = """
👋 *Yo, {name}!* Welcome to the most *unhinged* download bot on Telegram! 🤖🔥

I can snatch videos and music from basically anywhere on the internet and drop them straight into your chat. Legal? Debatable. Impressive? Absolutely. 😏

*What I can grab for you:*
📺 YouTube — Videos & Music
📸 Instagram — Reels & Posts
🎵 TikTok — Viral stuff
👥 Facebook — Videos
🐦 Twitter/X — Videos & GIFs
🎧 Spotify — Tracks, Albums & Playlists

*How to use me:*
Just paste a link. That's literally it. I'll do the rest! 🚀
"""

HELP_MESSAGE = """
🤖 *Bot Help — What I Can Do*

*Supported Platforms:*
• YouTube, Instagram, TikTok
• Facebook, Twitter/X
• Spotify (tracks, albums, playlists)

*How to Download:*
1. Paste any supported URL
2. Choose format: 🎵 MP3 or 🎬 MP4
3. Wait for the magic ✨
4. Done!

*Spotify:*
• Tracks → Audio MP3
• Albums → All tracks one by one
• Playlists → Up to 50 tracks

*Limits:*
• Max file size: 50MB
• Rate limit: 5 requests/minute
"""

PROCESSING_MESSAGES = [
    "💻⚡ *Downloading like a hacker in a movie…*",
    "😎 *Hold tight… stealing bytes from the internet…*",
    "🍳 *Let me cook something for you real quick…*",
    "🔥 *Channeling my inner pirate… Arr!*",
    "🌐 *Sending tiny robots to fetch your file…*",
    "⏳ *This is going to be so worth the wait…*",
    "🎩 *Watch me pull a file out of thin air…*",
    "🕵️ *Operating in the shadows… downloading covertly…*",
    "🚀 *Launching download sequence… T-minus 3… 2… 1…*",
    "🧙 *Casting download spell… ✨*",
]

DONATION_MESSAGE = (
    "💙 *This bot is completely free to use.*\n\n"
    "If you found it helpful, consider supporting us to keep it running fast.\n"
    "Even a small contribution means a lot 🙏\n\n"
    "_Scan the QR code to donate. Thank you!_ ❤️"
)


# ═══════════════════════════════════════════════════════════════════════════════
#   CHANNEL STORE — saves channels added via /addchannel
# ═══════════════════════════════════════════════════════════════════════════════

def get_all_channels() -> list:
    """Return force-join channels (config + dynamically added)."""
    dynamic = []
    try:
        with open(CHANNELS_DB_PATH) as f:
            dynamic = json.load(f)
    except Exception:
        pass
    combined = list(dict.fromkeys(FORCE_JOIN_CHANNELS + dynamic))
    return combined


def save_channel(channel: str) -> bool:
    try:
        with open(CHANNELS_DB_PATH) as f:
            channels = json.load(f)
    except Exception:
        channels = []
    if channel not in channels:
        channels.append(channel)
        with open(CHANNELS_DB_PATH, "w") as f:
            json.dump(channels, f, indent=2)
        return True
    return False


def delete_channel(channel: str) -> bool:
    try:
        with open(CHANNELS_DB_PATH) as f:
            channels = json.load(f)
        if channel in channels:
            channels.remove(channel)
            with open(CHANNELS_DB_PATH, "w") as f:
                json.dump(channels, f, indent=2)
            return True
    except Exception:
        pass
    return False


# ═══════════════════════════════════════════════════════════════════════════════
#   STATS STORE
# ═══════════════════════════════════════════════════════════════════════════════

STATS_FILE = Path("data/stats.json")
USERS_FILE = Path("data/users.json")


def get_stats() -> dict:
    try:
        return json.loads(STATS_FILE.read_text())
    except Exception:
        return {"total_users": 0, "total_downloads": 0,
                "audio_downloads": 0, "video_downloads": 0, "spotify_downloads": 0}


def increment_stat(key: str):
    s = get_stats()
    s[key] = s.get(key, 0) + 1
    s["total_downloads"] = s.get("audio_downloads", 0) + s.get("video_downloads", 0) + s.get("spotify_downloads", 0)
    STATS_FILE.write_text(json.dumps(s, indent=2))


def register_user(user_id: int):
    try:
        users = json.loads(USERS_FILE.read_text())
    except Exception:
        users = []
    if user_id not in users:
        users.append(user_id)
        USERS_FILE.write_text(json.dumps(users, indent=2))
        s = get_stats()
        s["total_users"] = len(users)
        STATS_FILE.write_text(json.dumps(s, indent=2))


def get_all_users() -> list:
    try:
        return json.loads(USERS_FILE.read_text())
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#   RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════════════

_requests: dict = defaultdict(list)


def rate_limit_allow(user_id: int) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    _requests[user_id] = [t for t in _requests[user_id] if t > window_start]
    if len(_requests[user_id]) >= RATE_LIMIT_REQUESTS:
        return False
    _requests[user_id].append(now)
    return True


# ═══════════════════════════════════════════════════════════════════════════════
#   FORCE JOIN MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════════

async def check_membership(bot, user_id: int) -> list:
    """Returns list of channels user has NOT joined."""
    not_joined = []
    for channel in get_all_channels():
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in (
                ChatMember.MEMBER,
                ChatMember.ADMINISTRATOR,
                ChatMember.OWNER,
            ):
                not_joined.append(channel)
        except TelegramError:
            pass  # If we can't check, don't block user
    return not_joined


async def send_join_prompt(update: Update, not_joined: list):
    """Block the user and show join buttons."""
    buttons = []
    for channel in not_joined:
        url = f"https://t.me/{channel.lstrip('@')}" if channel.startswith("@") else f"https://t.me/c/{str(channel).lstrip('-100')}"
        buttons.append([InlineKeyboardButton(f"📢 Join {channel}", url=url)])
    buttons.append([InlineKeyboardButton("✅ I Joined — Check Again!", callback_data="retry_join")])

    await update.effective_message.reply_text(
        "🚫 *Whoa there!*\n\n"
        "You need to join our channel(s) before using this bot.\n"
        "It takes 2 seconds and keeps this bot alive! 🙏\n\n"
        "👇 Join below, then tap *I Joined*:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#   DOWNLOADER
# ═══════════════════════════════════════════════════════════════════════════════

class DownloadError(Exception):
    pass


def _build_ydl_opts(fmt: str, output_template: str) -> dict:
    common = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
    }
    if fmt == "mp3":
        return {**common, "format": "bestaudio/best",
                "postprocessors": [{"key": "FFmpegExtractAudio",
                                    "preferredcodec": "mp3",
                                    "preferredquality": "320"}]}
    else:
        return {**common,
                "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best",
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}]}


def _find_file(output_id: str, fmt: str) -> str | None:
    ext = "mp3" if fmt == "mp3" else "mp4"
    for f in Path(DOWNLOAD_DIR).glob(f"{output_id}_*.{ext}"):
        return str(f)
    for f in Path(DOWNLOAD_DIR).glob(f"{output_id}_*"):
        return str(f)
    return None


def _download_sync(url: str, fmt: str) -> tuple:
    output_id = uuid.uuid4().hex[:8]
    template = str(Path(DOWNLOAD_DIR) / f"{output_id}_%(title)s.%(ext)s")
    opts = _build_ydl_opts(fmt, template)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if "entries" in info:
                info = info["entries"][0]
            title = info.get("title", "Unknown")
            file_path = _find_file(output_id, fmt)
            if not file_path:
                raise DownloadError("File not found after download.")
            size_mb = Path(file_path).stat().st_size / (1024 * 1024)
            if size_mb > MAX_FILE_SIZE_MB:
                Path(file_path).unlink(missing_ok=True)
                raise DownloadError(f"File too large ({size_mb:.1f}MB). Max is {MAX_FILE_SIZE_MB}MB. Try MP3 or a shorter video.")
            return file_path, title
    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if "Private" in err:
            raise DownloadError("This video is private.")
        elif "age" in err.lower():
            raise DownloadError("This video has age restrictions.")
        elif "not available" in err.lower():
            raise DownloadError("Not available in this region.")
        raise DownloadError(f"Download failed: {err[:200]}")


async def download_media(url: str, fmt: str) -> tuple:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _download_sync, url, fmt)


async def download_by_search(query: str, fmt: str) -> tuple:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _download_sync, f"ytsearch1:{query}", fmt)


# ═══════════════════════════════════════════════════════════════════════════════
#   SPOTIFY RESOLVER
# ═══════════════════════════════════════════════════════════════════════════════

class SpotifyError(Exception):
    pass


def get_spotify_client():
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET or SPOTIFY_CLIENT_ID == "PASTE_SPOTIFY_CLIENT_ID_HERE":
        raise SpotifyError("Spotify credentials not configured in config section.")
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        return spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
        ))
    except ImportError:
        raise SpotifyError("spotipy not installed. Run: pip install spotipy")
    except Exception as e:
        raise SpotifyError(f"Spotify connection failed: {e}")


def detect_spotify_type(url: str) -> str:
    if "/track/" in url:   return "track"
    if "/album/" in url:   return "album"
    if "/playlist/" in url: return "playlist"
    return "unknown"


def extract_spotify_id(url: str) -> str:
    match = re.search(r"spotify\.com/(?:track|album|playlist)/([a-zA-Z0-9]+)", url)
    if not match:
        raise SpotifyError("Could not extract Spotify ID from URL.")
    return match.group(1)


async def get_track_info(url: str) -> dict:
    loop = asyncio.get_event_loop()
    def _get():
        sp = get_spotify_client()
        t = sp.track(extract_spotify_id(url))
        return {"name": t["name"], "artist": ", ".join(a["name"] for a in t["artists"]),
                "album": t["album"]["name"]}
    return await loop.run_in_executor(None, _get)


async def get_album_info(url: str) -> dict:
    loop = asyncio.get_event_loop()
    def _get():
        sp = get_spotify_client()
        a = sp.album(extract_spotify_id(url))
        tracks = [{"name": t["name"], "artist": ", ".join(x["name"] for x in t["artists"])}
                  for t in a["tracks"]["items"]]
        return {"name": a["name"], "artist": ", ".join(x["name"] for x in a["artists"]), "tracks": tracks}
    return await loop.run_in_executor(None, _get)


async def get_playlist_info(url: str) -> dict:
    loop = asyncio.get_event_loop()
    def _get():
        sp = get_spotify_client()
        p = sp.playlist(extract_spotify_id(url))
        tracks = []
        items = p["tracks"]["items"]
        while p["tracks"]["next"]:
            p["tracks"] = sp.next(p["tracks"])
            items.extend(p["tracks"]["items"])
        for item in items:
            t = item.get("track")
            if t:
                tracks.append({"name": t["name"], "artist": ", ".join(a["name"] for a in t["artists"])})
        return {"name": p["name"], "tracks": tracks[:50]}
    return await loop.run_in_executor(None, _get)


# ═══════════════════════════════════════════════════════════════════════════════
#   DONATION QR SENDER
# ═══════════════════════════════════════════════════════════════════════════════

async def send_donation_qr(bot, chat_id: int):
    try:
        qr = DONATION_QR
        if not qr:
            return
        if qr.startswith("http"):
            await bot.send_photo(chat_id=chat_id, photo=qr, caption=DONATION_MESSAGE, parse_mode="Markdown")
        elif Path(qr).exists():
            with open(qr, "rb") as f:
                await bot.send_photo(chat_id=chat_id, photo=f, caption=DONATION_MESSAGE, parse_mode="Markdown")
        else:
            logger.warning(f"Donation QR not found at: {qr}")
    except Exception as e:
        logger.error(f"Failed to send donation QR: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#   URL DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

PLATFORM_PATTERNS = {
    "youtube":   re.compile(r"(youtube\.com|youtu\.be)", re.I),
    "instagram": re.compile(r"instagram\.com", re.I),
    "tiktok":    re.compile(r"tiktok\.com", re.I),
    "facebook":  re.compile(r"(facebook\.com|fb\.watch)", re.I),
    "twitter":   re.compile(r"(twitter\.com|x\.com|t\.co)", re.I),
    "spotify":   re.compile(r"open\.spotify\.com", re.I),
}

PLATFORM_EMOJI = {
    "youtube": "📺", "instagram": "📸", "tiktok": "🎵",
    "facebook": "👥", "twitter": "🐦", "spotify": "🎧",
}


def detect_platform(url: str) -> str | None:
    for platform, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(url):
            return platform
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#   ADMIN DECORATOR
# ═══════════════════════════════════════════════════════════════════════════════

def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id not in ADMIN_IDS:
            return  # Silently ignore non-admins
        return await func(update, context)
    return wrapper


# ═══════════════════════════════════════════════════════════════════════════════
#   HANDLERS — /start  /help
# ═══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id)
    await update.message.reply_text(
        WELCOME_MESSAGE.format(name=user.first_name or "legend"),
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MESSAGE, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════════════════
#   HANDLERS — URL MESSAGE
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id)

    # ── Force join check ──
    not_joined = await check_membership(context.bot, user.id)
    if not_joined:
        await send_join_prompt(update, not_joined)
        return

    # ── Rate limit check ──
    if not rate_limit_allow(user.id):
        await update.message.reply_text(
            f"⏳ Slow down! Max {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW} seconds."
        )
        return

    # ── Extract URL ──
    text = update.message.text.strip()
    urls = re.findall(r"https?://\S+", text)
    if not urls:
        await update.message.reply_text(
            "🤔 That doesn't look like a link. Send me a YouTube, Instagram, TikTok, Facebook, Twitter, or Spotify URL!"
        )
        return

    url = urls[0]
    platform = detect_platform(url)
    if not platform:
        await update.message.reply_text(
            "😕 Unsupported link.\n\nSupported: YouTube, Instagram, TikTok, Facebook, Twitter/X, Spotify"
        )
        return

    # ── Route to Spotify or show format picker ──
    if platform == "spotify":
        await handle_spotify(update, context, url)
    else:
        emoji = PLATFORM_EMOJI.get(platform, "🌐")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎵 MP3 (Audio)", callback_data=f"fmt_mp3_{url}"),
            InlineKeyboardButton("🎬 MP4 (Video)", callback_data=f"fmt_mp4_{url}"),
        ]])
        await update.message.reply_text(
            f"{emoji} *{platform.capitalize()} link detected!*\n\nChoose your format 👇",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#   HANDLERS — FORMAT CHOICE CALLBACK
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_", 2)
    if len(parts) < 3:
        return

    fmt = parts[1]   # mp3 or mp4
    url = parts[2]

    await query.edit_message_text(
        f"Format: *{fmt.upper()}*\n{random.choice(PROCESSING_MESSAGES)}",
        parse_mode="Markdown",
    )

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.UPLOAD_VOICE if fmt == "mp3" else ChatAction.UPLOAD_VIDEO,
    )

    try:
        file_path, title = await download_media(url, fmt)

        await query.edit_message_text(f"📤 Uploading *{title[:50]}*…", parse_mode="Markdown")

        with open(file_path, "rb") as f:
            if fmt == "mp4":
                await context.bot.send_video(
                    chat_id=update.effective_chat.id, video=f,
                    caption=f"🎬 *{title}*", parse_mode="Markdown",
                )
            else:
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id, audio=f,
                    title=title, caption=f"🎵 *{title}*", parse_mode="Markdown",
                )

        await query.delete_message()
        Path(file_path).unlink(missing_ok=True)

        increment_stat("video_downloads" if fmt == "mp4" else "audio_downloads")
        await send_donation_qr(context.bot, update.effective_chat.id)

    except DownloadError as e:
        await query.edit_message_text(f"❌ *Download failed!*\n\n{e}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        await query.edit_message_text("😵 Something broke. Please try again!")


# ═══════════════════════════════════════════════════════════════════════════════
#   HANDLERS — FORCE JOIN RETRY
# ═══════════════════════════════════════════════════════════════════════════════

async def retry_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔍 Checking your membership…")

    not_joined = await check_membership(context.bot, query.from_user.id)
    if not_joined:
        await query.edit_message_text(
            "😅 Still not joined! Please join the channel(s) then try again.",
            reply_markup=query.message.reply_markup,
        )
    else:
        await query.edit_message_text(
            "🎉 *You're in! Welcome!*\n\nNow send me any YouTube, Instagram, TikTok, Spotify link!",
            parse_mode="Markdown",
        )


# ═══════════════════════════════════════════════════════════════════════════════
#   HANDLERS — SPOTIFY
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_spotify(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    msg = await update.message.reply_text("🎧 Spotify link detected! Fetching info…")

    try:
        url_type = detect_spotify_type(url)

        if url_type == "track":
            track = await get_track_info(url)
            await msg.edit_text(
                f"🎵 *{track['name']}* by *{track['artist']}*\n{random.choice(PROCESSING_MESSAGES)}",
                parse_mode="Markdown",
            )
            file_path, _ = await download_by_search(f"{track['name']} {track['artist']} official audio", "mp3")
            with open(file_path, "rb") as f:
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id, audio=f,
                    title=track["name"], performer=track["artist"],
                    caption=f"🎵 *{track['name']}* — {track['artist']}", parse_mode="Markdown",
                )
            await msg.delete()
            Path(file_path).unlink(missing_ok=True)
            increment_stat("spotify_downloads")
            await send_donation_qr(context.bot, update.effective_chat.id)

        elif url_type == "album":
            album = await get_album_info(url)
            tracks = album["tracks"]
            await msg.edit_text(
                f"💿 *Album:* {album['name']}\n🎵 {len(tracks)} tracks — downloading…",
                parse_mode="Markdown",
            )
            for i, track in enumerate(tracks, 1):
                try:
                    await msg.edit_text(f"💿 Track {i}/{len(tracks)}: *{track['name']}*", parse_mode="Markdown")
                    file_path, _ = await download_by_search(f"{track['name']} {track['artist']} official audio", "mp3")
                    with open(file_path, "rb") as f:
                        await context.bot.send_audio(
                            chat_id=update.effective_chat.id, audio=f,
                            title=track["name"], performer=track["artist"],
                        )
                    Path(file_path).unlink(missing_ok=True)
                    await asyncio.sleep(1)
                except Exception:
                    await context.bot.send_message(update.effective_chat.id, f"⚠️ Skipped: {track['name']}")
            await msg.edit_text(f"✅ Album done! All {len(tracks)} tracks sent.", parse_mode="Markdown")
            increment_stat("spotify_downloads")
            await send_donation_qr(context.bot, update.effective_chat.id)

        elif url_type == "playlist":
            playlist = await get_playlist_info(url)
            tracks = playlist["tracks"]
            await msg.edit_text(
                f"📋 *Playlist:* {playlist['name']}\n🎵 {len(tracks)} tracks — downloading…",
                parse_mode="Markdown",
            )
            for i, track in enumerate(tracks, 1):
                try:
                    await msg.edit_text(f"📋 Track {i}/{len(tracks)}: *{track['name']}*", parse_mode="Markdown")
                    file_path, _ = await download_by_search(f"{track['name']} {track['artist']} official audio", "mp3")
                    with open(file_path, "rb") as f:
                        await context.bot.send_audio(
                            chat_id=update.effective_chat.id, audio=f,
                            title=track["name"], performer=track["artist"],
                        )
                    Path(file_path).unlink(missing_ok=True)
                    await asyncio.sleep(1)
                except Exception:
                    pass
            await msg.edit_text(f"✅ Playlist done! {len(tracks)} tracks sent.")
            increment_stat("spotify_downloads")
            await send_donation_qr(context.bot, update.effective_chat.id)

        else:
            await msg.edit_text("❓ Only Spotify tracks, albums, and playlists are supported.")

    except SpotifyError as e:
        await msg.edit_text(f"❌ Spotify Error: {e}")
    except Exception as e:
        logger.error(f"Spotify error: {e}", exc_info=True)
        await msg.edit_text("😵 Something went wrong with Spotify. Try again!")


# ═══════════════════════════════════════════════════════════════════════════════
#   HANDLERS — ADMIN COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

@admin_only
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = get_all_channels()
    stats = get_stats()
    ch_list = "\n".join(f"  • `{c}`" for c in channels) or "  _(none)_"
    await update.message.reply_text(
        "🛡️ *ADMIN PANEL*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Users: `{stats.get('total_users', 0)}`\n"
        f"📥 Downloads: `{stats.get('total_downloads', 0)}`\n"
        f"🎵 Audio: `{stats.get('audio_downloads', 0)}`\n"
        f"🎬 Video: `{stats.get('video_downloads', 0)}`\n"
        f"🎧 Spotify: `{stats.get('spotify_downloads', 0)}`\n\n"
        f"📢 *Force-join channels:*\n{ch_list}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "*Commands:*\n"
        "`/addchannel @name` — Add channel\n"
        "`/removechannel @name` — Remove channel\n"
        "`/broadcast message` — Message all users\n",
        parse_mode="Markdown",
    )


@admin_only
async def cmd_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/addchannel @channelname`", parse_mode="Markdown")
        return
    channel = context.args[0].strip()
    try:
        chat = await context.bot.get_chat(channel)
        save_channel(channel)
        await update.message.reply_text(f"✅ Added *{chat.title or channel}* to force-join!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Could not access `{channel}`.\nMake sure the bot is admin of that channel.\n\n`{e}`", parse_mode="Markdown")


@admin_only
async def cmd_removechannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/removechannel @channelname`", parse_mode="Markdown")
        return
    channel = context.args[0].strip()
    if delete_channel(channel):
        await update.message.reply_text(f"✅ Removed `{channel}` from force-join.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ `{channel}` not found in dynamic list.\n\nIf it's in the config at the top, edit it there directly.", parse_mode="Markdown")


@admin_only
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/broadcast Your message here`", parse_mode="Markdown")
        return
    text = " ".join(context.args)
    users = get_all_users()
    if not users:
        await update.message.reply_text("No users yet.")
        return
    status = await update.message.reply_text(f"📡 Broadcasting to {len(users)} users…")
    success, failed = 0, 0
    for uid in users:
        try:
            await context.bot.send_message(uid, f"📢 *Announcement*\n\n{text}", parse_mode="Markdown")
            success += 1
        except Exception:
            failed += 1
    await status.edit_text(f"📡 Done!\n✅ Sent: {success}\n❌ Failed: {failed}")


# ═══════════════════════════════════════════════════════════════════════════════
#   ERROR HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Error:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "😵 Something broke! The gremlins have been notified. Try again in a moment!"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#   MAIN — START THE BOT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    logger.info("🚀 Starting bot...")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",         cmd_start))
    app.add_handler(CommandHandler("help",          cmd_help))
    app.add_handler(CommandHandler("admin",         cmd_admin))
    app.add_handler(CommandHandler("addchannel",    cmd_addchannel))
    app.add_handler(CommandHandler("removechannel", cmd_removechannel))
    app.add_handler(CommandHandler("broadcast",     cmd_broadcast))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    # Callbacks
    app.add_handler(CallbackQueryHandler(retry_join_callback,  pattern="^retry_join$"))
    app.add_handler(CallbackQueryHandler(handle_format_choice, pattern="^fmt_"))

    # Errors
    app.add_error_handler(error_handler)

    logger.info("✅ Bot is live and ready to cook! 🍳")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
