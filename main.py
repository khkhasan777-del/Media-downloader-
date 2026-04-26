"""
main.py — Telegram Media Downloader Bot (Fixed for Railway)
"""

import logging
import asyncio
import re
import random
import json
import time
import uuid
import shutil
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
#   YOUR CONFIG — Fill in your details here
# ═══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN = "8258016908:AAFxKdNXbDGW1HLw-Tiw_QN7OMKifIPH2Vg"

ADMIN_IDS = [7578834050]

FORCE_JOIN_CHANNELS = ["@suvarq"]
# To disable: []

SPOTIFY_CLIENT_ID     = "8c543f45cdf349e98158e3c41db64d34"
SPOTIFY_CLIENT_SECRET = "05af202b792e4df8afa8c497b64468f3"

DONATION_QR = "assets/donation_qr.png"

# ═══════════════════════════════════════════════════════════════════════════════
#   DON'T TOUCH ANYTHING BELOW
# ═══════════════════════════════════════════════════════════════════════════════

DOWNLOAD_DIR        = "downloads"
MAX_FILE_SIZE_MB    = 45
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW   = 60
CHANNELS_DB_PATH    = "data/channels.json"

for folder in ["downloads", "data", "logs", "assets"]:
    Path(folder).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ── Find ffmpeg ───────────────────────────────────────────────────────────────
def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        logger.info(f"ffmpeg found: {found}")
        return found
    for path in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if Path(path).exists():
            logger.info(f"ffmpeg found: {path}")
            return path
    if Path("/nix/store").exists():
        matches = list(Path("/nix/store").glob("*/bin/ffmpeg"))
        if matches:
            logger.info(f"ffmpeg found: {matches[0]}")
            return str(matches[0])
    logger.warning("ffmpeg NOT FOUND — MP3 conversion limited")
    return None

FFMPEG_PATH = find_ffmpeg()

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

*Supported:* YouTube, Instagram, TikTok, Facebook, Twitter/X, Spotify

*How to Download:*
1. Paste any supported URL
2. Choose 🎵 MP3 or 🎬 MP4
3. Wait, then receive your file!

*Note:* Instagram public posts/reels only. Private accounts won't work.
*Limit:* Max 45MB per file. Rate limit: 5 requests/minute.
"""

PROCESSING_MESSAGES = [
    "💻⚡ *Downloading like a hacker in a movie…*",
    "😎 *Hold tight… stealing bytes from the internet…*",
    "🍳 *Let me cook something for you real quick…*",
    "🔥 *Channeling my inner pirate… Arr!*",
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
#   CHANNEL STORE
# ═══════════════════════════════════════════════════════════════════════════════

def get_all_channels():
    dynamic = []
    try:
        with open(CHANNELS_DB_PATH) as f:
            dynamic = json.load(f)
    except Exception:
        pass
    return list(dict.fromkeys(FORCE_JOIN_CHANNELS + dynamic))

def save_channel(channel):
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

def delete_channel(channel):
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
#   STATS
# ═══════════════════════════════════════════════════════════════════════════════

STATS_FILE = Path("data/stats.json")
USERS_FILE = Path("data/users.json")

def get_stats():
    try:
        return json.loads(STATS_FILE.read_text())
    except Exception:
        return {"total_users": 0, "total_downloads": 0, "audio_downloads": 0, "video_downloads": 0, "spotify_downloads": 0}

def increment_stat(key):
    s = get_stats()
    s[key] = s.get(key, 0) + 1
    s["total_downloads"] = s.get("audio_downloads", 0) + s.get("video_downloads", 0) + s.get("spotify_downloads", 0)
    STATS_FILE.write_text(json.dumps(s, indent=2))

def register_user(user_id):
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

def get_all_users():
    try:
        return json.loads(USERS_FILE.read_text())
    except Exception:
        return []

# ═══════════════════════════════════════════════════════════════════════════════
#   RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════════════

_req_log = defaultdict(list)

def rate_limit_allow(user_id):
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW
    _req_log[user_id] = [t for t in _req_log[user_id] if t > cutoff]
    if len(_req_log[user_id]) >= RATE_LIMIT_REQUESTS:
        return False
    _req_log[user_id].append(now)
    return True

# ═══════════════════════════════════════════════════════════════════════════════
#   FORCE JOIN
# ═══════════════════════════════════════════════════════════════════════════════

async def check_membership(bot, user_id):
    not_joined = []
    for channel in get_all_channels():
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER):
                not_joined.append(channel)
        except TelegramError:
            pass
    return not_joined

async def send_join_prompt(update, not_joined):
    buttons = []
    for channel in not_joined:
        url = f"https://t.me/{channel.lstrip('@')}" if channel.startswith("@") else f"https://t.me/c/{str(channel).lstrip('-100')}"
        buttons.append([InlineKeyboardButton(f"📢 Join {channel}", url=url)])
    buttons.append([InlineKeyboardButton("✅ I Joined — Check Again!", callback_data="retry_join")])
    await update.effective_message.reply_text(
        "🚫 *Whoa there!*\n\nYou need to join our channel(s) before using this bot.\nIt takes 2 seconds! 🙏\n\n👇 Join below, then tap *I Joined*:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

# ═══════════════════════════════════════════════════════════════════════════════
#   DOWNLOADER
# ═══════════════════════════════════════════════════════════════════════════════

class DownloadError(Exception):
    pass

def _build_opts(fmt, template):
    common = {
        "outtmpl": template,
        "quiet": False,
        "no_warnings": False,
        "socket_timeout": 60,
        "retries": 5,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
    }
    if FFMPEG_PATH:
        common["ffmpeg_location"] = str(Path(FFMPEG_PATH).parent)

    if fmt == "mp3":
        if FFMPEG_PATH:
            return {**common, "format": "bestaudio/best",
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]}
        else:
            return {**common, "format": "bestaudio/best"}
    else:
        if FFMPEG_PATH:
            return {**common,
                    "format": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                    "merge_output_format": "mp4"}
        else:
            return {**common, "format": "best[ext=mp4]/best"}

def _find_file(output_id):
    for f in Path(DOWNLOAD_DIR).glob(f"{output_id}_*"):
        if f.is_file():
            return str(f)
    return None

def _download_sync(url, fmt):
    output_id = uuid.uuid4().hex[:8]
    template  = str(Path(DOWNLOAD_DIR) / f"{output_id}_%(title).80s.%(ext)s")
    opts      = _build_opts(fmt, template)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            logger.info(f"Downloading: {url} [{fmt}]")
            info = ydl.extract_info(url, download=True)
            if info and "entries" in info:
                info = info["entries"][0]
            title     = info.get("title", "Unknown") if info else "Unknown"
            file_path = _find_file(output_id)
            if not file_path:
                raise DownloadError("File not found after download. This might be a private or region-blocked post.")
            size_mb = Path(file_path).stat().st_size / (1024 * 1024)
            logger.info(f"Downloaded: {title} ({size_mb:.1f}MB)")
            if size_mb > MAX_FILE_SIZE_MB:
                Path(file_path).unlink(missing_ok=True)
                raise DownloadError(f"File is {size_mb:.1f}MB — too large for Telegram (max {MAX_FILE_SIZE_MB}MB).\nTry MP3 instead, or use a shorter video.")
            return file_path, title
    except DownloadError:
        raise
    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        logger.error(f"yt-dlp error: {err}")
        if "private" in err.lower():
            raise DownloadError("❌ This post is private. Only public content works.")
        elif "login" in err.lower() or "sign in" in err.lower():
            raise DownloadError("❌ This content requires login. Only public posts work.")
        elif "age" in err.lower():
            raise DownloadError("❌ Age-restricted content can't be downloaded.")
        elif "not available" in err.lower() or "unavailable" in err.lower():
            raise DownloadError("❌ Content unavailable or region-blocked.")
        elif "instagram" in err.lower():
            raise DownloadError("❌ Instagram download failed.\nOnly public posts/reels work. Private accounts and stories don't.")
        else:
            raise DownloadError(f"❌ Download failed:\n`{err[:250]}`")
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        raise DownloadError(f"❌ Error: {str(e)[:200]}")

async def download_media(url, fmt):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _download_sync, url, fmt)

async def download_by_search(query, fmt):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _download_sync, f"ytsearch1:{query}", fmt)

# ═══════════════════════════════════════════════════════════════════════════════
#   SPOTIFY
# ═══════════════════════════════════════════════════════════════════════════════

class SpotifyError(Exception):
    pass

def get_spotify_client():
    if not SPOTIFY_CLIENT_ID or "PASTE" in SPOTIFY_CLIENT_ID:
        raise SpotifyError("Spotify credentials not configured.\nEdit main.py and fill in SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET.")
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        return spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))
    except ImportError:
        raise SpotifyError("spotipy not installed.")
    except Exception as e:
        raise SpotifyError(f"Spotify connection failed: {e}")

def detect_spotify_type(url):
    if "/track/"    in url: return "track"
    if "/album/"    in url: return "album"
    if "/playlist/" in url: return "playlist"
    return "unknown"

def extract_spotify_id(url):
    match = re.search(r"spotify\.com/(?:track|album|playlist)/([a-zA-Z0-9]+)", url)
    if not match:
        raise SpotifyError("Could not extract Spotify ID.")
    return match.group(1)

async def get_track_info(url):
    loop = asyncio.get_event_loop()
    def _get():
        sp = get_spotify_client()
        t  = sp.track(extract_spotify_id(url))
        return {"name": t["name"], "artist": ", ".join(a["name"] for a in t["artists"]), "album": t["album"]["name"]}
    return await loop.run_in_executor(None, _get)

async def get_album_info(url):
    loop = asyncio.get_event_loop()
    def _get():
        sp = get_spotify_client()
        a  = sp.album(extract_spotify_id(url))
        return {"name": a["name"], "artist": ", ".join(x["name"] for x in a["artists"]),
                "tracks": [{"name": t["name"], "artist": ", ".join(x["name"] for x in t["artists"])} for t in a["tracks"]["items"]]}
    return await loop.run_in_executor(None, _get)

async def get_playlist_info(url):
    loop = asyncio.get_event_loop()
    def _get():
        sp = get_spotify_client()
        p  = sp.playlist(extract_spotify_id(url))
        items = p["tracks"]["items"]
        while p["tracks"]["next"]:
            p["tracks"] = sp.next(p["tracks"])
            items.extend(p["tracks"]["items"])
        tracks = [{"name": t["track"]["name"], "artist": ", ".join(a["name"] for a in t["track"]["artists"])}
                  for t in items if t.get("track")]
        return {"name": p["name"], "tracks": tracks[:50]}
    return await loop.run_in_executor(None, _get)

# ═══════════════════════════════════════════════════════════════════════════════
#   DONATION QR
# ═══════════════════════════════════════════════════════════════════════════════

async def send_donation_qr(bot, chat_id):
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
            logger.warning(f"Donation QR not found: {qr}")
    except Exception as e:
        logger.error(f"Donation QR error: {e}")

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
PLATFORM_EMOJI = {"youtube": "📺", "instagram": "📸", "tiktok": "🎵", "facebook": "👥", "twitter": "🐦", "spotify": "🎧"}

def detect_platform(url):
    for platform, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(url):
            return platform
    return None

# ═══════════════════════════════════════════════════════════════════════════════
#   ADMIN DECORATOR
# ═══════════════════════════════════════════════════════════════════════════════

def admin_only(func):
    @wraps(func)
    async def wrapper(update, context):
        user = update.effective_user
        if not user or user.id not in ADMIN_IDS:
            return
        return await func(update, context)
    return wrapper

# ═══════════════════════════════════════════════════════════════════════════════
#   COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id)
    await update.message.reply_text(WELCOME_MESSAGE.format(name=user.first_name or "legend"), parse_mode="Markdown")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MESSAGE, parse_mode="Markdown")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id)

    not_joined = await check_membership(context.bot, user.id)
    if not_joined:
        await send_join_prompt(update, not_joined)
        return

    if not rate_limit_allow(user.id):
        await update.message.reply_text(f"⏳ Slow down! Max {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW}s.")
        return

    text = update.message.text.strip()
    urls = re.findall(r"https?://\S+", text)
    if not urls:
        await update.message.reply_text("🤔 No link found. Send me a YouTube, Instagram, TikTok, Facebook, Twitter, or Spotify URL!")
        return

    url      = urls[0]
    platform = detect_platform(url)
    if not platform:
        await update.message.reply_text("😕 Unsupported link.\nSupported: YouTube, Instagram, TikTok, Facebook, Twitter/X, Spotify")
        return

    if platform == "spotify":
        await handle_spotify(update, context, url)
    else:
        emoji   = PLATFORM_EMOJI.get(platform, "🌐")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎵 MP3 (Audio)", callback_data=f"fmt_mp3_{url}"),
            InlineKeyboardButton("🎬 MP4 (Video)", callback_data=f"fmt_mp4_{url}"),
        ]])
        await update.message.reply_text(
            f"{emoji} *{platform.capitalize()} link detected!*\n\nChoose your format 👇",
            parse_mode="Markdown", reply_markup=keyboard,
        )

async def handle_format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        return
    fmt, url    = parts[1], parts[2]
    status_msg  = await query.edit_message_text(
        f"Format: *{fmt.upper()}*\n{random.choice(PROCESSING_MESSAGES)}", parse_mode="Markdown"
    )
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.UPLOAD_VOICE if fmt == "mp3" else ChatAction.UPLOAD_VIDEO,
    )
    try:
        file_path, title = await download_media(url, fmt)
        await status_msg.edit_text(f"📤 Uploading *{title[:50]}*…", parse_mode="Markdown")
        with open(file_path, "rb") as f:
            if fmt == "mp4":
                await context.bot.send_video(chat_id=update.effective_chat.id, video=f,
                    caption=f"🎬 *{title[:100]}*", parse_mode="Markdown", supports_streaming=True)
            else:
                aw
