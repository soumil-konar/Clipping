import os
import json
import hashlib
import subprocess
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs
import yt_dlp
from backend.config import DOWNLOADS_DIR

CACHE_INDEX_FILE = DOWNLOADS_DIR / "cache_index.json"

def normalize_url(url: str) -> str:
    """Normalizes video URLs to ensure consistent cache keys across slight variations."""
    url = url.strip()
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if "youtube.com" in netloc or "youtu.be" in netloc:
            video_id = None
            if "youtu.be" in netloc:
                video_id = parsed.path.lstrip("/").split("?")[0].split("/")[0]
            elif "youtube.com" in netloc:
                qs = parse_qs(parsed.query)
                if "v" in qs and qs["v"]:
                    video_id = qs["v"][0]
                elif parsed.path.startswith("/shorts/"):
                    video_id = parsed.path.split("/shorts/")[1].split("/")[0].split("?")[0]
                elif parsed.path.startswith("/live/"):
                    video_id = parsed.path.split("/live/")[1].split("/")[0].split("?")[0]
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"
        elif "twitch.tv" in netloc or "kick.com" in netloc:
            return f"{parsed.scheme}://{netloc}{parsed.path.rstrip('/')}"
    except Exception:
        pass
    return url

def get_cache_key_for_url(url: str) -> str:
    """Generates a stable filesystem-safe cache identifier from normalized URL."""
    norm_url = normalize_url(url)
    return "src_" + hashlib.sha256(norm_url.encode("utf-8")).hexdigest()[:16]

def load_cache_index() -> Dict[str, Any]:
    if CACHE_INDEX_FILE.exists():
        try:
            return json.loads(CACHE_INDEX_FILE.read_text())
        except Exception:
            return {}
    return {}

def save_cache_index(index: Dict[str, Any]):
    try:
        CACHE_INDEX_FILE.write_text(json.dumps(index, indent=2))
    except Exception as e:
        print(f"Warning: Failed to save download cache index: {e}")

def extract_audio_for_transcription(video_path: Path, audio_path: Path) -> bool:
    """Extracts a 16kHz mono PCM wav file for fast, accurate Whisper transcription."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(audio_path)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode == 0

class VideoDownloader:
    def __init__(self, output_dir: Path = DOWNLOADS_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_info(self, url: str) -> Dict[str, Any]:
        """Fetch video metadata without downloading."""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "id": info.get("id", str(uuid.uuid4())[:8]),
                "title": info.get("title", "Untitled Video"),
                "uploader": info.get("uploader") or info.get("channel", "Unknown Creator"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "description": (info.get("description") or "")[:500],
            }

    def download(self, url: str, job_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Download video up to 1080p and extract audio.
        Reuses existing downloaded files for previously submitted URLs.
        If the previous file was deleted from disk, automatically triggers a fresh re-download.
        """
        norm_url = normalize_url(url)
        cache_key = get_cache_key_for_url(norm_url)
        cache_index = load_cache_index()

        # Step 1: Check if this URL was previously downloaded AND the video file still physically exists
        cached_entry = cache_index.get(norm_url)
        existing_video_path: Optional[Path] = None

        if cached_entry and "video_path" in cached_entry:
            candidate = Path(cached_entry["video_path"])
            if candidate.exists() and candidate.is_file() and candidate.stat().st_size > 10240:
                existing_video_path = candidate

        # Also check directly in downloads folder using cache_key naming convention
        if not existing_video_path:
            for potential_ext in [".mp4", ".mkv", ".webm", ".mov"]:
                candidate = self.output_dir / f"{cache_key}{potential_ext}"
                if candidate.exists() and candidate.is_file() and candidate.stat().st_size > 10240:
                    existing_video_path = candidate
                    break

        # CASE 1: Cache Hit — previous video exists on disk!
        if existing_video_path is not None:
            print(f"⚡ Cache Hit: Reusing existing downloaded video for '{url}' -> {existing_video_path.name}")
            audio_path = self.output_dir / f"{cache_key}.wav"

            # Verify audio file exists; if user/cleaner deleted audio, re-extract from existing video
            if not audio_path.exists() or audio_path.stat().st_size < 1024:
                print(f"Extracted audio missing for cached video. Re-extracting from {existing_video_path.name}...")
                extract_audio_for_transcription(existing_video_path, audio_path)

            meta = cached_entry.get("meta") if cached_entry else None
            meta_file = self.output_dir / f"{cache_key}_meta.json"
            if not meta and meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                except Exception:
                    meta = None

            if not meta:
                try:
                    meta = self.get_info(url)
                    meta_file.write_text(json.dumps(meta, indent=2))
                except Exception:
                    meta = {
                        "title": "Cached Video",
                        "uploader": "Streamer",
                        "duration": 0,
                        "thumbnail": ""
                    }

            return {
                "job_id": job_id or cache_key,
                "cache_key": cache_key,
                "cached": True,
                "title": meta.get("title", "Untitled Video"),
                "uploader": meta.get("uploader", "Unknown Creator"),
                "duration": meta.get("duration", 0),
                "video_path": str(existing_video_path),
                "audio_path": str(audio_path),
                "thumbnail": meta.get("thumbnail", ""),
            }

        # CASE 2: Cache Miss or Previous File Deleted — Perform fresh download
        if cached_entry:
            print(f"⚠️ Previous file for '{url}' was deleted from disk. Re-downloading fresh copy...")
        else:
            print(f"⬇️ Downloading new video stream for '{url}' (Key: {cache_key})...")

        video_filename_template = f"{cache_key}.%(ext)s"
        target_template = self.output_dir / video_filename_template
        audio_path = self.output_dir / f"{cache_key}.wav"

        ydl_opts = {
            # Avoid YouTube Premium / restricted bitstreams (format 616, etc.) which return HTTP 403
            "format": "bestvideo[height<=1080][format_note!*=Premium]+bestaudio/best[height<=1080]/best",
            "outtmpl": str(target_template),
            "merge_output_format": "mp4",
            "quiet": False,
            "no_warnings": False,
        }
        if Path("/usr/bin/node").exists():
            ydl_opts["js_runtimes"] = {"node": {"path": "/usr/bin/node"}}

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Find the actual downloaded video file
            actual_video_path = self.output_dir / f"{cache_key}.mp4"
            if not actual_video_path.exists():
                potential_files = list(self.output_dir.glob(f"{cache_key}.*"))
                for pf in potential_files:
                    if pf.suffix.lower() in [".mp4", ".mkv", ".webm", ".mov"] and pf.stat().st_size > 10240:
                        actual_video_path = pf
                        break

            # Extract audio for whisper
            extract_audio_for_transcription(actual_video_path, audio_path)

            meta = {
                "title": info.get("title", "Untitled Video"),
                "uploader": info.get("uploader") or info.get("channel", "Unknown"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
            }

            # Save meta file
            meta_file = self.output_dir / f"{cache_key}_meta.json"
            try:
                meta_file.write_text(json.dumps(meta, indent=2))
            except Exception:
                pass

            # Update cache index
            cache_index[norm_url] = {
                "cache_key": cache_key,
                "video_path": str(actual_video_path),
                "audio_path": str(audio_path),
                "meta": meta
            }
            save_cache_index(cache_index)

            return {
                "job_id": job_id or cache_key,
                "cache_key": cache_key,
                "cached": False,
                "title": meta["title"],
                "uploader": meta["uploader"],
                "duration": meta["duration"],
                "video_path": str(actual_video_path),
                "audio_path": str(audio_path),
                "thumbnail": meta["thumbnail"],
            }
