import json
import os
import re
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from backend.config import GEMINI_API_KEY

class ViralityScorer:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or GEMINI_API_KEY
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"Warning: Failed to initialize Gemini Client: {e}")

    def score_clips(
        self,
        segments: List[Dict[str, Any]],
        energy_timeline: List[Dict[str, float]],
        total_duration: float,
        target_clips: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Evaluates transcript & audio dynamics to identify the top viral candidate clips (30-60s).
        Uses Gemini 2.5 Flash if available, otherwise runs heuristic algorithm.
        """
        if self.client and len(segments) > 0:
            try:
                ai_clips = self._score_with_gemini(segments, total_duration, target_clips)
                if ai_clips:
                    return ai_clips
            except Exception as e:
                print(f"Gemini scoring failed, falling back to heuristics: {e}")

        return self._score_with_heuristics(segments, energy_timeline, total_duration, target_clips)

    def _score_with_gemini(
        self,
        segments: List[Dict[str, Any]],
        total_duration: float,
        target_clips: int
    ) -> List[Dict[str, Any]]:
        """Use Gemini 2.5 Flash to pick the most viral moments."""
        # Format transcript with timestamps
        transcript_lines = []
        for s in segments:
            transcript_lines.append(f"[{s['start']:.1f}s - {s['end']:.1f}s]: {s['text']}")
        transcript_text = "\n".join(transcript_lines)

        prompt = f"""You are an elite short-form content producer who makes viral TikToks, YouTube Shorts, and Instagram Reels for top streamers and brands on clipping.net.

Analyze the transcript of this video (total duration {total_duration:.1f} seconds) and identify the top {target_clips} most viral, engaging clips.

Key Criteria for Short-form Virality:
1. Strong 0-3s Hook: The clip must start with an intriguing question, sudden reaction, high-stakes statement, or sudden drama.
2. Self-Contained Story: A complete thought, joke, punchline, debate, or climax that makes sense without needing 10 minutes of prior context.
3. Optimal Duration: Between 30 and 60 seconds (strictly under 60s for Shorts/TikTok monetization).
4. No dead silence or prolonged throat-clearing at the start.

Return a JSON array of objects with the following schema:
[
  {{
    "start_time": float,
    "end_time": float,
    "virality_score": int (1-100),
    "hook_text": "First 3-5 words / opening hook sentence",
    "title": "Punchy viral title (under 50 chars)",
    "description": "Engaging 1-sentence caption",
    "hashtags": ["#tag1", "#tag2", "#tag3"],
    "reason": "Why this will perform well on TikTok/Shorts"
  }}
]

Transcript:
{transcript_text[:35000]}
"""

        # Prioritize gemini-3.5-flash-lite (500 RPD on free tier vs 20 RPD on standard flash)
        for model_name in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.6-flash"]:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.4
                    )
                )
                if response and response.text:
                    break
            except Exception as e:
                print(f"Model {model_name} failed: {e}")

        if not response or not response.text:
            return []

        raw_json = response.text.strip()
        data = json.loads(raw_json)
        if isinstance(data, list):
            # Clamp timestamps
            for c in data:
                c["start_time"] = max(0.0, float(c.get("start_time", 0.0)))
                c["end_time"] = min(total_duration, float(c.get("end_time", c["start_time"] + 45.0)))
                c["duration"] = round(c["end_time"] - c["start_time"], 1)
            return sorted(data, key=lambda x: x.get("virality_score", 0), reverse=True)
        return []

    def _score_with_heuristics(
        self,
        segments: List[Dict[str, Any]],
        energy_timeline: List[Dict[str, float]],
        total_duration: float,
        target_clips: int
    ) -> List[Dict[str, Any]]:
        """Heuristic highlight detector using audio energy peaks and conversational triggers."""
        # Find peak energy moments
        peak_times = set()
        if energy_timeline:
            sorted_by_rms = sorted(energy_timeline, key=lambda x: x["rms"], reverse=True)
            top_n = max(5, int(len(sorted_by_rms) * 0.1))
            for item in sorted_by_rms[:top_n]:
                peak_times.add(item["timestamp"])

        hook_keywords = [
            "wait", "bro", "no way", "what the", "why did", "how did", "omg",
            "look at", "listen", "literally", "crazy", "you won't believe", "stop"
        ]

        scored_candidates = []

        # Sliding window across segments (aiming for 30s to 50s clips)
        for i, start_seg in enumerate(segments):
            start_t = max(0.0, start_seg["start"] - 0.5)
            text_acc = [start_seg["text"]]
            
            for end_seg in segments[i + 1:]:
                end_t = end_seg["end"] + 0.5
                dur = end_t - start_t
                text_acc.append(end_seg["text"])
                
                if 28.0 <= dur <= 55.0:
                    combined_text = " ".join(text_acc)
                    score = 50
                    
                    # Bonus for hook keywords in the first 5 seconds
                    first_sentence = start_seg["text"].lower()
                    if any(kw in first_sentence for kw in hook_keywords):
                        score += 20
                    if "?" in first_sentence:
                        score += 15
                    if "!" in combined_text:
                        score += 10
                    
                    # Bonus if an audio energy peak happens during this window
                    has_energy_peak = any(start_t <= pt <= end_t for pt in peak_times)
                    if has_energy_peak:
                        score += 25

                    # Create a title from the opening hook
                    cleaned_title = re.sub(r"[^\w\s]", "", start_seg["text"]).strip().title()
                    if len(cleaned_title) > 40:
                        cleaned_title = cleaned_title[:37] + "..."

                    scored_candidates.append({
                        "start_time": round(start_t, 2),
                        "end_time": round(end_t, 2),
                        "duration": round(dur, 2),
                        "virality_score": min(98, score),
                        "hook_text": start_seg["text"][:60],
                        "title": cleaned_title or f"Clip at {int(start_t)}s",
                        "description": f"Highlight moment from {int(start_t)}s to {int(end_t)}s",
                        "hashtags": ["#shorts", "#fyp", "#viral", "#trending", "#clip"],
                        "reason": "High emotional engagement and dynamic dialogue flow"
                    })
                    break

        # Remove overlapping clips and select top candidates
        scored_candidates.sort(key=lambda x: x["virality_score"], reverse=True)
        final_clips: List[Dict[str, Any]] = []

        for cand in scored_candidates:
            # Check overlap with already picked clips (>15s overlap)
            overlaps = False
            for picked in final_clips:
                if not (cand["end_time"] <= picked["start_time"] + 10 or cand["start_time"] >= picked["end_time"] - 10):
                    overlaps = True
                    break
            if not overlaps:
                final_clips.append(cand)
            if len(final_clips) >= target_clips:
                break

        # Fallback if no clips found (e.g. very short video)
        if not final_clips:
            clip_dur = min(total_duration, 45.0)
            final_clips.append({
                "start_time": 0.0,
                "end_time": clip_dur,
                "duration": clip_dur,
                "virality_score": 75,
                "hook_text": "Opening hook",
                "title": "Highlight Moment",
                "description": "Top moment from stream",
                "hashtags": ["#fyp", "#viral", "#shorts"],
                "reason": "Top initial engagement"
            })

        return final_clips
