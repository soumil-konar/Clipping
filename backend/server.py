import asyncio
import os
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.config import (
    BASE_DIR, DOWNLOADS_DIR, CLIPS_DIR, EXPORTS_DIR, STATIC_DIR,
    CUDA_AVAILABLE, DEFAULT_VIDEO_CODEC, PLATFORM_PROFILES
)
from backend.downloader import VideoDownloader
from backend.transcriber import Transcriber
from backend.virality_scorer import ViralityScorer
from backend.subtitles import SubtitleGenerator
from backend.video_editor import VideoEditor

app = FastAPI(title="ClipForge - AI Short-form Clipping Studio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job state store
jobs_db: Dict[str, Dict[str, Any]] = {}

# Shared components (lazy initialized on first use)
_transcriber: Optional[Transcriber] = None
_downloader = VideoDownloader(DOWNLOADS_DIR)
_editor = VideoEditor(CLIPS_DIR)
_sub_gen = SubtitleGenerator()

def get_transcriber() -> Transcriber:
    global _transcriber
    if _transcriber is None:
        _transcriber = Transcriber()
    return _transcriber

class JobRequest(BaseModel):
    url: str
    preset: str = "streamer"  # "streamer", "podcast", "gaming"
    layout_mode: str = "blur_bg"  # "blur_bg", "smart_crop", "split_screen"
    platform: str = "instagram"  # "instagram", "tiktok", "youtube_shorts"
    target_clips: int = 4
    gemini_api_key: Optional[str] = None

class FineTuneRequest(BaseModel):
    start_time: float
    end_time: float
    layout_mode: str = "blur_bg"
    platform: str = "instagram"
    custom_x_ratio: Optional[float] = None
    subtitles_enabled: bool = True
    highlight_color: str = "&H00FFFF&"

def process_clipping_job(job_id: str, req: JobRequest):
    """Background worker that executes the entire pipeline."""
    job = jobs_db[job_id]
    try:
        # Step 1: Download
        job["status"] = "downloading"
        job["progress"] = 15
        dl_info = _downloader.download(req.url, job_id=job_id)
        job["title"] = dl_info["title"]
        job["creator"] = dl_info["uploader"]
        job["duration"] = dl_info["duration"]
        job["video_path"] = dl_info["video_path"]
        job["audio_path"] = dl_info["audio_path"]
        job["thumbnail"] = dl_info["thumbnail"]

        # Step 2: Transcribe & Audio RMS
        job["status"] = "transcribing"
        job["progress"] = 40
        transcriber = get_transcriber()
        tr_result = transcriber.transcribe(Path(dl_info["audio_path"]))
        job["words"] = tr_result["words"]
        job["segments"] = tr_result["segments"]
        job["energy_timeline"] = tr_result["energy_timeline"]

        # Step 3: Virality & Highlight Detection
        job["status"] = "analyzing"
        job["progress"] = 70
        api_key = req.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        scorer = ViralityScorer(api_key=api_key)
        candidate_clips = scorer.score_clips(
            segments=tr_result["segments"],
            energy_timeline=tr_result["energy_timeline"],
            total_duration=dl_info["duration"],
            target_clips=req.target_clips,
            preset=req.preset,
            platform=req.platform
        )

        # Step 4: Render Candidate Clips in 9:16
        job["status"] = "rendering"
        job["progress"] = 85
        processed_clips = []
        for i, cand in enumerate(candidate_clips):
            clip_id = f"{job_id}_clip_{i+1}"
            
            # Generate subtitles with platform safe margins
            sub_file = CLIPS_DIR / f"{clip_id}.ass"
            _sub_gen.generate_ass(
                words_with_timestamps=tr_result["words"],
                output_path=sub_file,
                clip_start=cand["start_time"],
                words_per_group=3,
                platform=req.platform
            )

            # Render 9:16 clip with Instagram-optimal bitrate & GOP
            rendered_video = _editor.render_clip(
                video_path=Path(dl_info["video_path"]),
                start_time=cand["start_time"],
                end_time=cand["end_time"],
                output_name=clip_id,
                layout_mode=req.layout_mode,
                subtitles_path=sub_file,
                platform=req.platform
            )

            cand["clip_id"] = clip_id
            cand["video_url"] = f"/media/clips/{rendered_video.name}"
            cand["layout_mode"] = req.layout_mode
            cand["platform"] = req.platform
            cand["subtitles_enabled"] = True
            cand["exported"] = False
            processed_clips.append(cand)

        job["clips"] = processed_clips
        job["status"] = "completed"
        job["progress"] = 100

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        print(f"Error processing job {job_id}: {e}")

@app.get("/api/status")
def get_system_status():
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    return {
        "status": "ready",
        "cuda_available": CUDA_AVAILABLE,
        "encoder": _editor.codec,
        "has_gemini_key": has_gemini,
        "total_jobs": len(jobs_db),
        "platform_profiles": PLATFORM_PROFILES
    }

@app.post("/api/settings")
def update_settings(data: Dict[str, str]):
    if "gemini_api_key" in data:
        os.environ["GEMINI_API_KEY"] = data["gemini_api_key"].strip()
    return {"status": "ok", "has_gemini_key": bool(os.environ.get("GEMINI_API_KEY"))}

@app.post("/api/jobs")
def create_job(req: JobRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    jobs_db[job_id] = {
        "job_id": job_id,
        "url": req.url,
        "status": "queued",
        "progress": 5,
        "title": "Queued Video...",
        "creator": "...",
        "duration": 0,
        "clips": [],
        "error": None
    }
    background_tasks.add_task(process_clipping_job, job_id, req)
    return {"job_id": job_id, "status": "queued"}

def init_demo_job_if_available():
    clip1 = CLIPS_DIR / "c57817cb_clip_1.mp4"
    if clip1.exists() and "c57817cb" not in jobs_db:
        jobs_db["c57817cb"] = {
            "job_id": "c57817cb",
            "url": "https://www.youtube.com/watch?v=sample1",
            "title": "Stream Highlights · Unhinged Moment (4K)",
            "creator": "Kai Cenat Live",
            "duration": 180,
            "status": "completed",
            "progress": 100,
            "video_path": str(DOWNLOADS_DIR / "c57817cb.mp4"),
            "audio_path": str(DOWNLOADS_DIR / "c57817cb.wav"),
            "thumbnail": "",
            "words": [],
            "clips": [
                {
                    "clip_id": "c57817cb_clip_1",
                    "title": "Wait Did He Really Just Say That? 💀",
                    "description": "The entire chat went wild when this happened live on stream! Drop a comment if you saw it.",
                    "hashtags": ["#kaicenat", "#twitchclips", "#reels", "#fyp", "#viral"],
                    "start_time": 0.0,
                    "end_time": 39.7,
                    "duration": 39.7,
                    "virality_score": 96,
                    "hook_type": "Curiosity Gap",
                    "retention_prediction": 94,
                    "reason": "Extreme emotional peak with immediate hook, sustained conversational tension, and high comment incentive.",
                    "layout_mode": "blur_bg",
                    "platform": "instagram",
                    "video_url": "/media/clips/c57817cb_clip_1.mp4"
                },
                {
                    "clip_id": "c57817cb_clip_2",
                    "title": "Uncontrollable Laughter at 3 AM 😂",
                    "description": "You cannot make this up... watch his face at the end 😭 #streamerlife",
                    "hashtags": ["#funny", "#streamer", "#hilarious", "#trending"],
                    "start_time": 40.0,
                    "end_time": 73.2,
                    "duration": 33.2,
                    "virality_score": 93,
                    "hook_type": "Shock & Humor",
                    "retention_prediction": 91,
                    "reason": "Immediate laughter hook and high relatable comedic energy.",
                    "layout_mode": "blur_bg",
                    "platform": "instagram",
                    "video_url": "/media/clips/c57817cb_clip_2.mp4"
                },
                {
                    "clip_id": "c57817cb_clip_3",
                    "title": "He Actually Predicted the Entire Match 🤯",
                    "description": "5 seconds before it happened, he called every single move. Mind blown.",
                    "hashtags": ["#gaming", "#prediction", "#clutch", "#epic"],
                    "start_time": 80.0,
                    "end_time": 115.1,
                    "duration": 35.1,
                    "virality_score": 91,
                    "hook_type": "Story Escalation",
                    "retention_prediction": 89,
                    "reason": "High tension buildup leading to an explosive punchline and payoff.",
                    "layout_mode": "blur_bg",
                    "platform": "instagram",
                    "video_url": "/media/clips/c57817cb_clip_3.mp4"
                },
                {
                    "clip_id": "c57817cb_clip_4",
                    "title": "Chat Convinced Him To Do The Impossible 🔥",
                    "description": "Never doubt Twitch chat when they unite. What a moment.",
                    "hashtags": ["#streamer", "#twitch", "#moment", "#viralclips"],
                    "start_time": 120.0,
                    "end_time": 153.5,
                    "duration": 33.5,
                    "virality_score": 88,
                    "hook_type": "Community Challenge",
                    "retention_prediction": 87,
                    "reason": "Strong viewer identification and loopable ending.",
                    "layout_mode": "blur_bg",
                    "platform": "instagram",
                    "video_url": "/media/clips/c57817cb_clip_4.mp4"
                }
            ]
        }

@app.get("/api/jobs")
def list_jobs():
    if not jobs_db:
        init_demo_job_if_available()
    return list(jobs_db.values())

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs_db:
        init_demo_job_if_available()
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs_db[job_id]

@app.post("/api/clips/{clip_id}/fine_tune")
def fine_tune_clip(clip_id: str, req: FineTuneRequest):
    """Re-renders a clip with new timestamps, crop layout, or subtitle toggle."""
    # Find job for this clip
    job_id = clip_id.split("_clip_")[0]
    if job_id not in jobs_db:
        init_demo_job_if_available()
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs_db[job_id]
    clip = next((c for c in job["clips"] if c["clip_id"] == clip_id), None)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    sub_file = None
    if req.subtitles_enabled:
        words = job.get("words", [])
        if not words and Path(job.get("audio_path", "")).exists():
            try:
                transcriber = get_transcriber()
                tr_result = transcriber.transcribe(Path(job["audio_path"]))
                words = tr_result.get("words", [])
                job["words"] = words
            except Exception as e:
                print(f"Subtitles transcription error: {e}")
        if words:
            sub_file = CLIPS_DIR / f"{clip_id}.ass"
            _sub_gen.generate_ass(
                words_with_timestamps=words,
                output_path=sub_file,
                clip_start=req.start_time,
                words_per_group=3,
                highlight_color=req.highlight_color,
                platform=req.platform
            )

    rendered_video = _editor.render_clip(
        video_path=Path(job["video_path"]),
        start_time=req.start_time,
        end_time=req.end_time,
        output_name=clip_id,
        layout_mode=req.layout_mode,
        subtitles_path=sub_file if req.subtitles_enabled else None,
        custom_x_ratio=req.custom_x_ratio,
        platform=req.platform
    )

    clip["start_time"] = req.start_time
    clip["end_time"] = req.end_time
    clip["duration"] = round(req.end_time - req.start_time, 1)
    clip["layout_mode"] = req.layout_mode
    clip["platform"] = req.platform
    clip["subtitles_enabled"] = req.subtitles_enabled
    clip["video_url"] = f"/media/clips/{rendered_video.name}?t={int(os.path.getmtime(rendered_video))}"

    return {"status": "updated", "clip": clip}

@app.post("/api/clips/{clip_id}/export")
def export_clip(clip_id: str):
    """Copies finalized clip to exports/ folder."""
    clip_file = CLIPS_DIR / f"{clip_id}.mp4"
    if not clip_file.exists():
        raise HTTPException(status_code=404, detail="Clip video file not found")
    
    export_file = EXPORTS_DIR / f"{clip_id}_ready.mp4"
    shutil.copy2(clip_file, export_file)
    return {
        "status": "exported",
        "export_url": f"/media/exports/{export_file.name}",
        "file_name": export_file.name
    }

# Mount media directories
app.mount("/media/clips", StaticFiles(directory=str(CLIPS_DIR)), name="clips")
app.mount("/media/exports", StaticFiles(directory=str(EXPORTS_DIR)), name="exports")
app.mount("/media/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="downloads")

# Mount frontend
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")
