import json
import subprocess
import sys
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


def get_info(url):
    """Extract media info using yt-dlp"""
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--dump-json",
        "--no-playlist",
        "--no-warnings",
        "--quiet",
        url
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=25
    )

    if result.returncode != 0:
        raise Exception(result.stderr or "Failed to extract info")

    data = json.loads(result.stdout)
    return data


def format_duration(seconds):
    if not seconds:
        return None
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_views(n):
    if not n:
        return None
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def parse_formats(info):
    """Parse available formats from yt-dlp info"""
    extractor = info.get("extractor_key", "").lower()
    formats = info.get("formats", [])
    media_type = info.get("_type", "video")

    # Detect if it's an image post (Instagram image)
    if not formats and info.get("url"):
        url = info.get("url", "")
        if any(ext in url for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            return "image", ["image_jpg", "image_png"]

    # Check for video formats
    has_hd = any(
        f.get("height", 0) >= 720
        for f in formats
        if f.get("height")
    )
    has_sd = any(
        f.get("height", 0) and f.get("height", 0) < 720
        for f in formats
        if f.get("height")
    )

    available = []

    if has_hd or (not has_sd and formats):
        available.append("video_hd")

    if has_sd or formats:
        available.append("video_sd")

    # MP3 for audio-bearing videos
    if info.get("acodec") != "none" or any(
        f.get("acodec", "none") != "none" for f in formats
    ):
        available.append("mp3")

    if not available:
        available = ["video_hd", "video_sd", "mp3"]

    return "video", available


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        url = params.get("url", [None])[0]

        if not url:
            self.respond(400, {"error": "Missing url parameter"})
            return

        try:
            info = get_info(url)
            media_type, formats = parse_formats(info)

            result = {
                "title": info.get("title", "Unknown"),
                "uploader": info.get("uploader") or info.get("channel") or info.get("creator") or "Unknown",
                "duration": format_duration(info.get("duration")),
                "views": format_views(info.get("view_count")),
                "thumbnail": info.get("thumbnail") or (info.get("thumbnails") or [{}])[-1].get("url"),
                "type": media_type,
                "platform": info.get("extractor_key", "unknown").lower(),
                "formats": formats,
                "webpage_url": info.get("webpage_url", url)
            }

            self.respond(200, result)

        except subprocess.TimeoutExpired:
            self.respond(408, {"error": "Timeout — URL took too long to process"})
        except json.JSONDecodeError:
            self.respond(500, {"error": "Failed to parse media info"})
        except Exception as e:
            self.respond(500, {"error": str(e)})

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Suppress default logging
