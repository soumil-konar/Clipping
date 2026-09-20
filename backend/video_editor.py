import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple
import cv2
from backend.config import CLIPS_DIR, EXPORTS_DIR, DEFAULT_VIDEO_CODEC

def detect_face_x_center(video_path: Path, sample_seconds: float = 5.0) -> float:
    """
    Samples frames across the video to detect the primary speaker's horizontal center (0.0 to 1.0).
    Uses OpenCV's YuNet neural face detector for fast, reliable tracking.
    """
    try:
        onnx_path = Path(__file__).resolve().parent / "face_detection_yunet.onnx"
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return 0.5

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 100)
        step = max(1, int(fps * 0.5))  # Sample every 0.5 seconds

        detector = None
        x_centers = []
        frame_idx = 0
        while cap.isOpened() and frame_idx < min(total_frames, int(fps * 30)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            h, w = frame.shape[:2]
            if detector is None and onnx_path.exists() and hasattr(cv2, "FaceDetectorYN_create"):
                detector = cv2.FaceDetectorYN_create(str(onnx_path), "", (w, h), score_threshold=0.6)
            elif detector is not None:
                detector.setInputSize((w, h))

            if detector is not None:
                _, faces = detector.detect(frame)
                if faces is not None and len(faces) > 0:
                    # Pick largest face by area (w*h)
                    largest_face = max(faces, key=lambda f: f[2] * f[3])
                    fx, fy, fw, fh = largest_face[:4]
                    center_x = (fx + fw / 2.0) / w
                    x_centers.append(center_x)

            frame_idx += step

        cap.release()
        if x_centers:
            # Median center to reject outliers
            x_centers.sort()
            return float(x_centers[len(x_centers) // 2])
    except Exception as e:
        print(f"Face detection error: {e}")
    return 0.5

class VideoEditor:
    def __init__(self, output_dir: Path = CLIPS_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.codec = self._check_encoder()

    def _check_encoder(self) -> str:
        """Verify if h264_nvenc is available; otherwise fallback to libx264."""
        try:
            res = subprocess.run(
                ["ffmpeg", "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if "h264_nvenc" in res.stdout:
                return "h264_nvenc"
        except Exception:
            pass
        return "libx264"

    def render_clip(
        self,
        video_path: Path,
        start_time: float,
        end_time: float,
        output_name: str,
        layout_mode: str = "blur_bg",  # "blur_bg", "smart_crop", "split_screen"
        subtitles_path: Optional[Path] = None,
        custom_x_ratio: Optional[float] = None,
    ) -> Path:
        """
        Extracts, formats to 9:16 vertical (1080x1920), burns animated subtitles,
        and renders using GPU hardware acceleration.
        """
        output_file = self.output_dir / f"{output_name}.mp4"
        duration = end_time - start_time

        # Calculate crop position if smart_crop
        if layout_mode == "smart_crop":
            if custom_x_ratio is not None:
                x_ratio = max(0.1, min(0.9, custom_x_ratio))
            else:
                x_ratio = detect_face_x_center(video_path)
            
            # Crop box width for 9:16 is (ih * 9 / 16).
            # Center of crop box is x_ratio * iw.
            filter_chain = (
                f"[0:v]crop=w='ih*9/16':h='ih':"
                f"x='max(0, min(iw-ow, {x_ratio}*iw - ow/2))':y=0,"
                f"scale=1080:1920:flags=bicubic[v]"
            )
        elif layout_mode == "split_screen":
            # Top: Streamer facecam (cropped 1:1 or 4:3 from upper corner/detected face), Bottom: Gameplay
            x_ratio = custom_x_ratio if custom_x_ratio is not None else 0.82
            filter_chain = (
                # Streamer cam cropped to top half
                f"[0:v]crop=w='ih*0.5':h='ih*0.5':x='max(0, min(iw-ow, {x_ratio}*iw - ow/2))':y=0,scale=1080:860[cam];"
                # Gameplay / main content on bottom
                f"[0:v]crop=w='ih*16/9':h='ih':x='(iw-ow)/2':y=0,scale=1080:1060[game];"
                # Stack cam on top and game on bottom
                f"[cam][game]vstack=inputs=2[v]"
            )
        else:  # "blur_bg" (default high-reliability cinematic layout)
            filter_chain = (
                # Blurred background filled to 1080x1920
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                # Sharp foreground centered
                f"[0:v]scale=1080:-1:force_original_aspect_ratio=decrease[fg];"
                # Overlay foreground on blurred background
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
            )

        # If subtitles provided, append ASS subtitle burning
        if subtitles_path and subtitles_path.exists():
            # Escape path for FFmpeg filter syntax
            escaped_sub_path = str(subtitles_path).replace("\\", "/").replace(":", "\\:")
            filter_chain += f";[v]ass='{escaped_sub_path}'[v]"

        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start_time:.3f}",
            "-i", str(video_path),
            "-t", f"{duration:.3f}",
            "-filter_complex", filter_chain,
            "-map", "[v]",
            "-map", "0:a?",
            "-c:v", self.codec,
            "-b:v", "6M",
            "-maxrate", "8M",
            "-bufsize", "12M",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-movflags", "+faststart",
            str(output_file)
        ]

        # For NVENC, add preset p4 / fast
        if self.codec == "h264_nvenc":
            cmd.insert(cmd.index("-c:v") + 2, "-preset")
            cmd.insert(cmd.index("-c:v") + 3, "p4")

        print(f"Executing FFmpeg render: {' '.join(cmd)}")
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            print(f"FFmpeg error: {proc.stderr}")
            # Try fallback to libx264 if nvenc failed
            if self.codec == "h264_nvenc":
                print("Retrying with CPU encoder (libx264)...")
                cmd[cmd.index("h264_nvenc")] = "libx264"
                if "-preset" in cmd:
                    idx = cmd.index("-preset")
                    cmd[idx + 1] = "fast"
                proc2 = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if proc2.returncode != 0:
                    raise RuntimeError(f"FFmpeg render failed: {proc2.stderr}")

        return output_file
