from pathlib import Path
from typing import List, Dict, Any

def format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp format: H:MM:SS.cc"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis == 100:
        secs += 1
        centis = 0
    return f"{hrs}:{mins:02d}:{secs:02d}.{centis:02d}"

class SubtitleGenerator:
    def __init__(self, font_name: str = "DejaVu Sans", font_size: int = 44):
        self.font_name = font_name
        self.font_size = font_size

    def generate_ass(
        self,
        words_with_timestamps: List[Dict[str, Any]],
        output_path: Path,
        clip_start: float = 0.0,
        words_per_group: int = 3,
        highlight_color: str = "&H00FFFF&",  # Bright Yellow in BGR hex (&HBBGGRR&)
        base_color: str = "&HFFFFFF&",       # White
        outline_color: str = "&H000000&",    # Black
        platform: str = "instagram",
        margin_v: Optional[int] = None,
        margin_r: Optional[int] = None,
        margin_l: Optional[int] = None,
    ) -> Path:
        """
        Generates an ASS subtitle file with animated active-word karaoke styling.
        `words_with_timestamps` is a list of dicts: {'word': str, 'start': float, 'end': float}
        Timestamps are normalized relative to clip_start.
        Safe zones are tuned specifically to prevent Instagram Reels / TikTok UI overlapping.
        """
        # Instagram safe margins (avoids bottom captions, music marquee, and right-side action buttons)
        if margin_v is None:
            margin_v = 540 if platform == "instagram" else 490
        if margin_r is None:
            margin_r = 150 if platform == "instagram" else 120
        if margin_l is None:
            margin_l = 70

        # Filter and normalize words within clip range
        rel_words = []
        for w in words_with_timestamps:
            w_start = w["start"] - clip_start
            w_end = w["end"] - clip_start
            if w_end > 0:
                rel_words.append({
                    "word": w["word"].strip().upper(),
                    "start": max(0.0, w_start),
                    "end": max(0.0, w_end)
                })

        # Group words into 2-3 word chunks for fast, readable pacing
        groups = []
        for i in range(0, len(rel_words), words_per_group):
            group = rel_words[i : i + words_per_group]
            if group:
                groups.append(group)

        # Build ASS script with BT.709 color matrix and safe margins
        ass_header = f"""[Script Info]
Title: Instagram/Shorts Dynamic Karaoke Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{self.font_name},{self.font_size},{base_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,1,0,1,5,2.5,2,{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for group in groups:
            for idx, active_word in enumerate(group):
                ev_start = format_ass_time(active_word["start"])
                ev_end = format_ass_time(active_word["end"])
                
                # Assemble text with active word scale pop (\fscx112\fscy112)
                formatted_words = []
                for j, w in enumerate(group):
                    if j == idx:
                        formatted_words.append(r"{\c" + highlight_color + r"\fscx112\fscy112}" + w["word"] + r"{\r}")
                    else:
                        formatted_words.append(r"{\c" + base_color + r"}" + w["word"])
                
                line_text = " ".join(formatted_words)
                events.append(f"Dialogue: 0,{ev_start},{ev_end},Default,,0,0,0,,{line_text}")

        content = ass_header + "\n".join(events) + "\n"
        output_path.write_text(content, encoding="utf-8")
        return output_path
