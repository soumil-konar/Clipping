import os
import subprocess
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
import yt_dlp
from backend.config import DOWNLOADS_DIR

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
        """Download video up to 1080p and extract audio."""
        if not job_id:
            job_id = str(uuid.uuid4())[:8]

        video_filename = f"{job_id}.mp4"
        video_path = self.output_dir / video_filename
        audio_path = self.output_dir / f"{job_id}.wav"

        ydl_opts = {
            # Avoid YouTube Premium / restricted bitstreams (format 616, etc.) which return HTTP 403
            "format": "bestvideo[height<=1080][format_note!*=Premium]+bestaudio/best[height<=1080]/best",
            "outtmpl": str(video_path.with_suffix(".%(ext)s")),
            "merge_output_format": "mp4",
            "quiet": False,
            "no_warnings": False,
        }
        if Path("/usr/bin/node").exists():
            ydl_opts["js_runtimes"] = {"node": {"path": "/usr/bin/node"}}

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Find the actual downloaded file (yt-dlp may merge to .mp4)
            actual_video_path = video_path
            if not actual_video_path.exists():
                potential_files = list(self.output_dir.glob(f"{job_id}.*"))
                for pf in potential_files:
                    if pf.suffix in [".mp4", ".mkv", ".webm"]:
                        actual_video_path = pf
                        break

            # Extract audio for whisper
            extract_audio_for_transcription(actual_video_path, audio_path)

            return {
                "job_id": job_id,
                "title": info.get("title", "Untitled Video"),
                "uploader": info.get("uploader") or info.get("channel", "Unknown"),
                "duration": info.get("duration", 0),
                "video_path": str(actual_video_path),
                "audio_path": str(audio_path),
                "thumbnail": info.get("thumbnail", ""),
            }
