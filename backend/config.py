import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
CLIPS_DIR = STORAGE_DIR / "clips"
EXPORTS_DIR = STORAGE_DIR / "exports"
STATIC_DIR = BASE_DIR / "frontend"

for directory in [STORAGE_DIR, DOWNLOADS_DIR, CLIPS_DIR, EXPORTS_DIR, STATIC_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Hardware & Model Settings
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

key_file = BASE_DIR / "key.txt"
if not os.environ.get("GEMINI_API_KEY") and key_file.exists():
    for line in key_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("AQ.") or line.startswith("AIzaSy"):
            os.environ["GEMINI_API_KEY"] = line
            break

CUDA_AVAILABLE = os.environ.get("USE_CUDA", "true").lower() == "true"
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")  # tiny, base, small, medium
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEFAULT_VIDEO_CODEC = os.environ.get("VIDEO_CODEC", "h264_nvenc")

# Video Formatting Defaults
DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_FPS = 30
