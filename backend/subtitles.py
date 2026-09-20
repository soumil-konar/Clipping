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
    ) -> Path:
        """
        Generates an ASS subtitle file with animated active-word karaoke styling.
        `words_with_timestamps` is a list of dicts: {'word': str, 'start': float, 'end': float}
        Timestamps are normalized relative to clip_start.
        """
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

        # Group words into 2-4 word chunks
        groups = []
        for i in range(0, len(rel_words), words_per_group):
            group = rel_words[i : i + words_per_group]
            if group:
                groups.append(group)

        # Build ASS script
        ass_header = f"""[Script Info]
Title: TikTok/Shorts Dynamic Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{self.font_name},{self.font_size},{base_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,1,0,1,5,2,2,40,40,480,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for group in groups:
            # Group start is the first word start, end is the last word end
            # For each word's active duration, we generate a dialogue line highlighting that active word
            for idx, active_word in enumerate(group):
                ev_start = format_ass_time(active_word["start"])
                ev_end = format_ass_time(active_word["end"])
                
                # Assemble text with highlighted active word
                formatted_words = []
                for j, w in enumerate(group):
                    if j == idx:
                        # Highlight active word with scale pop and highlight color
                        formatted_words.append(r"{\c" + highlight_color + r"\fscx108\fscy108}" + w["word"] + r"{\r}")
                    else:
                        formatted_words.append(r"{\c" + base_color + r"}" + w["word"])
                
                line_text = " ".join(formatted_words)
                events.append(f"Dialogue: 0,{ev_start},{ev_end},Default,,0,0,0,,{line_text}")

        content = ass_header + "\n".join(events) + "\n"
        output_path.write_text(content, encoding="utf-8")
        return output_path
