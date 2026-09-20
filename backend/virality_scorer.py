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
        target_clips: int = 5,
        preset: str = "streamer",
        platform: str = "instagram"
    ) -> List[Dict[str, Any]]:
        """
        Evaluates transcript & audio dynamics to identify top viral candidate clips (25-50s).
        Uses Gemini Flash models if available, otherwise runs heuristic algorithm.
        """
        if self.client and len(segments) > 0:
            try:
                ai_clips = self._score_with_gemini(
                    segments=segments,
                    total_duration=total_duration,
                    target_clips=target_clips,
                    preset=preset,
                    platform=platform
                )
                if ai_clips:
                    return ai_clips
            except Exception as e:
                print(f"Gemini scoring failed, falling back to heuristics: {e}")

        return self._score_with_heuristics(
            segments=segments,
            energy_timeline=energy_timeline,
            total_duration=total_duration,
            target_clips=target_clips,
            preset=preset,
            platform=platform
        )

    def _score_with_gemini(
        self,
        segments: List[Dict[str, Any]],
        total_duration: float,
        target_clips: int,
        preset: str = "streamer",
        platform: str = "instagram"
    ) -> List[Dict[str, Any]]:
        """Use Gemini Flash models to extract high-retention viral moments optimized for Instagram Reels & TikTok."""
        # Format transcript with timestamps
        transcript_lines = []
        for s in segments:
            transcript_lines.append(f"[{s['start']:.1f}s - {s['end']:.1f}s]: {s['text']}")
        transcript_text = "\n".join(transcript_lines)

        # Preset-specific creative directive
        preset_directives = {
            "streamer": (
                "NICHE: Live Streamer Banter & Drama.\n"
                "Prioritize: Explosive creator reactions, chat roasting, unexpected incidents, funny misunderstandings, or wild unscripted confessions."
            ),
            "podcast": (
                "NICHE: Podcast & Deep Conversation.\n"
                "Prioritize: Mind-expanding revelations, contrarian life/business wisdom, taboo topics, heated debates, or secrets that challenge conventional thinking."
            ),
            "gaming": (
                "NICHE: Gaming & Esports.\n"
                "Prioritize: Clutch 1vX plays, hilarious glitches/fails, rage quit moments, toxic/funny teammate banter, and heart-stopping finishes."
            )
        }
        niche_directive = preset_directives.get(preset, preset_directives["streamer"])

        prompt = f"""You are an elite Lead Short-Form Video Producer, Viral Growth Engineer, and Retention Scientist who curates clips that generate 1M+ views on Instagram Reels, TikTok, and YouTube Shorts for clipping.net.

Your mission is to analyze this video transcript (total duration {total_duration:.1f} seconds) and identify the top {target_clips} most viral, high-converting candidate clips.

{niche_directive}
PLATFORM TARGET: {platform.upper()} (Priority: High visual clarity, safe-zone awareness, loopable pacing, and comment-driving discussion).

### THE 4 LAWS OF SHORT-FORM RETENTION (Instagram Reels & Shorts Algorithm):
1. **The 0-3s Hook Gatekeeper (Zero Dead Air):**
   - Viewers decide whether to swipe in 1.8 seconds.
   - The clip MUST open immediately with a powerful hook sentence.
   - Hook Archetypes:
     * *Curiosity Gap*: "You will never believe why this happened...", "The biggest lie we were told about..."
     * *Shock & High Stakes*: Immediate emotional shout, intense laughter, sudden revelation, or dramatic conflict.
     * *Contrarian Hot Take*: "Everyone gets this wrong...", "Stop doing this immediately..."
     * *Comedy Climax*: Instant relatable humor or ironic premise.
   - NEVER start with filler words ("um", "so yeah", "like", "you know"), throat clearing, or quiet intro pauses.

2. **Complete Three-Act Narrative Arc (Payoff & Closure):**
   - Clip structure MUST be:
     * Act I (0-3s): Irresistible Hook / Setup
     * Act II (4-25s): Escalation, context build-up, and tension
     * Act III (26-45s): The Payoff, punchline, mind-blown realization, or dramatic conclusion.
   - DO NOT cut off mid-thought, mid-word, or right before the punchline.

3. **Loopability & Pacing (25s - 45s):**
   - Instagram's algorithm heavily boosts videos with >85% average watch time.
   - Ideal clip length is 25 to 45 seconds (strictly <= 58s).
   - If possible, choose an ending where the last phrase naturally loops back into the opening hook.

4. **Comment-Driving CTAs & Captions:**
   - Comments are Instagram's #1 virality ranking factor.
   - Provide a caption ending in an open, debate-sparking question or Call-To-Action (e.g. "Would you have done this? 👇", "Tag someone who needs to hear this 👇").

Return a JSON array of objects adhering STRICTLY to this schema:
[
  {{
    "start_time": float,
    "end_time": float,
    "virality_score": int (1-100),
    "hook_text": "Exact opening 4-8 words spoken",
    "hook_type": "Curiosity Gap | Shock & High Stakes | Contrarian Take | Comedy Climax | Deep Revelation",
    "title": "Punchy viral title (under 45 chars, capitalize key impact words)",
    "description": "Engaging 1-2 sentence caption with comment-driving CTA",
    "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"],
    "retention_prediction": int (75-98),
    "reason": "Tactical analysis of why this hook retains viewers and sparks shares/comments"
  }}
]

Transcript:
{transcript_text[:35000]}
"""

        # Prioritize gemini-3.5-flash-lite (500 RPD on free tier), with fallback pool of 20 RPD models
        response = None
        for model_name in [
            "gemini-3.5-flash-lite",
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-3.8-flash",
            "gemini-3.6-flash"
        ]:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.35
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
            # Clamp timestamps and ensure valid bounds
            for c in data:
                c["start_time"] = max(0.0, float(c.get("start_time", 0.0)))
                c["end_time"] = min(total_duration, float(c.get("end_time", c["start_time"] + 45.0)))
                c["duration"] = round(c["end_time"] - c["start_time"], 1)
                c["retention_prediction"] = int(c.get("retention_prediction", c.get("virality_score", 85)))
                c["hook_type"] = c.get("hook_type", "Shock & Reaction")
            return sorted(data, key=lambda x: x.get("virality_score", 0), reverse=True)
        return []

    def _score_with_heuristics(
        self,
        segments: List[Dict[str, Any]],
        energy_timeline: List[Dict[str, float]],
        total_duration: float,
        target_clips: int,
        preset: str = "streamer",
        platform: str = "instagram"
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
            "look at", "listen", "literally", "crazy", "you won't believe", "stop",
            "the truth", "secret", "never", "always", "insane"
        ]

        # Preset-tailored hashtags
        if preset == "podcast":
            default_tags = ["#podcast", "#mindset", "#interview", "#reels", "#fyp"]
            cta_text = "What is your perspective on this? Drop a comment below 👇"
        elif preset == "gaming":
            default_tags = ["#gaming", "#gamer", "#clutch", "#reels", "#fyp"]
            cta_text = "Rate this play from 1-10 in the comments! 👇"
        else:
            default_tags = ["#reels", "#streamer", "#viral", "#trending", "#fyp"]
            cta_text = "What would you have done here? Tell us below 👇"

        scored_candidates = []

        # Sliding window across segments (aiming for 25s to 45s clips)
        for i, start_seg in enumerate(segments):
            start_t = max(0.0, start_seg["start"] - 0.5)
            text_acc = [start_seg["text"]]
            
            for end_seg in segments[i + 1:]:
                end_t = end_seg["end"] + 0.5
                dur = end_t - start_t
                text_acc.append(end_seg["text"])
                
                if 25.0 <= dur <= 50.0:
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

                    hook_type = "Shock & High Stakes" if has_energy_peak else ("Curiosity Gap" if "?" in first_sentence else "Deep Revelation")

                    scored_candidates.append({
                        "start_time": round(start_t, 2),
                        "end_time": round(end_t, 2),
                        "duration": round(dur, 2),
                        "virality_score": min(98, score),
                        "retention_prediction": min(96, max(76, score - 3)),
                        "hook_type": hook_type,
                        "hook_text": start_seg["text"][:60],
                        "title": cleaned_title or f"Clip at {int(start_t)}s",
                        "description": f"{cleaned_title}! {cta_text}",
                        "hashtags": default_tags,
                        "reason": f"High emotional engagement and dynamic dialogue flow with detected {preset} energy peaks"
                    })
                    break

        # Remove overlapping clips and select top candidates
        scored_candidates.sort(key=lambda x: x["virality_score"], reverse=True)
        final_clips: List[Dict[str, Any]] = []

        for cand in scored_candidates:
            # Check overlap with already picked clips (>12s overlap)
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
            clip_dur = min(total_duration, 40.0)
            final_clips.append({
                "start_time": 0.0,
                "end_time": clip_dur,
                "duration": clip_dur,
                "virality_score": 80,
                "retention_prediction": 85,
                "hook_type": "Curiosity Gap",
                "hook_text": "Opening hook moment",
                "title": "Top Viral Moment",
                "description": f"Highlight moment from stream! {cta_text}",
                "hashtags": default_tags,
                "reason": f"Top initial engagement and paced dialogue for {platform}"
            })

        return final_clips
