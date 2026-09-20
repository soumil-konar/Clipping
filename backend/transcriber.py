import math
import struct
import wave
from pathlib import Path
from typing import Dict, Any, List, Optional
import torch
import whisper
from backend.config import WHISPER_MODEL

def calculate_audio_energy(wav_path: Path, window_seconds: float = 1.0) -> List[Dict[str, float]]:
    """Calculates RMS audio energy per time window to detect volume/laughter/screaming peaks."""
    energy_points = []
    try:
        with wave.open(str(wav_path), "rb") as wf:
            framerate = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            chunk_size = int(framerate * window_seconds)
            
            time_offset = 0.0
            while True:
                frames = wf.readframes(chunk_size)
                if not frames:
                    break
                
                # Unpack 16-bit PCM
                count = len(frames) // (sampwidth * n_channels)
                if count == 0:
                    break
                
                fmt = f"<{count * n_channels}h"
                samples = struct.unpack(fmt, frames)
                
                # Compute RMS
                sum_sq = sum(s ** 2 for s in samples)
                rms = math.sqrt(sum_sq / len(samples)) if samples else 0.0
                
                energy_points.append({
                    "timestamp": round(time_offset, 2),
                    "rms": round(rms, 2)
                })
                time_offset += window_seconds
    except Exception as e:
        print(f"Warning: Failed to calculate audio energy: {e}")
    return energy_points

class Transcriber:
    def __init__(self, model_name: str = WHISPER_MODEL):
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading Whisper model '{model_name}' on device: {self.device}...")
        self.model = whisper.load_model(model_name, device=self.device)

    def transcribe(self, audio_path: Path) -> Dict[str, Any]:
        """
        Transcribes the audio file and extracts segments with word-level timestamps.
        Reuses cached transcription if audio file has not changed.
        """
        transcript_cache = audio_path.with_suffix(".transcript.json")
        if transcript_cache.exists() and transcript_cache.is_file() and transcript_cache.stat().st_size > 50:
            try:
                # Ensure audio was not replaced after the cache was generated
                if transcript_cache.stat().st_mtime >= audio_path.stat().st_mtime:
                    cached_data = json.loads(transcript_cache.read_text())
                    if "words" in cached_data and "segments" in cached_data and "energy_timeline" in cached_data:
                        print(f"⚡ Cache Hit: Reusing existing transcript from {transcript_cache.name}")
                        return cached_data
            except Exception as e:
                print(f"Transcript cache read error: {e}, re-transcribing...")

        print(f"Transcribing {audio_path}...")
        result = self.model.transcribe(
            str(audio_path),
            word_timestamps=True,
            verbose=False,
            fp16=(self.device == "cuda")
        )

        all_words: List[Dict[str, Any]] = []
        segments: List[Dict[str, Any]] = []

        for seg in result.get("segments", []):
            segments.append({
                "id": seg.get("id"),
                "start": seg.get("start"),
                "end": seg.get("end"),
                "text": seg.get("text", "").strip(),
            })
            for w in seg.get("words", []):
                all_words.append({
                    "word": w.get("word", "").strip(),
                    "start": w.get("start"),
                    "end": w.get("end"),
                    "probability": w.get("probability", 1.0)
                })

        energy_timeline = calculate_audio_energy(audio_path)

        output = {
            "text": result.get("text", ""),
            "language": result.get("language", "en"),
            "segments": segments,
            "words": all_words,
            "energy_timeline": energy_timeline
        }

        try:
            transcript_cache.write_text(json.dumps(output, indent=2))
        except Exception:
            pass

        return output
