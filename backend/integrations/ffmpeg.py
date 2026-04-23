"""
FFmpeg integration - video concatenation and post-processing.
"""

import subprocess
import shutil
from pathlib import Path
from config import OUTPUTS_DIR


def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def concatenate_videos(video_paths: list[str], output_path: str) -> str:
    """
    Concatenate multiple video files into one using FFmpeg.
    Returns the output path.
    Raises RuntimeError if FFmpeg is not available.
    """
    if not is_ffmpeg_available():
        raise RuntimeError("FFmpeg is not installed or not in PATH")

    # Create concat file
    concat_content = "\n".join(f"file '{p}'" for p in video_paths)
    concat_file = Path(output_path).parent / "concat.txt"
    concat_file.write_text(concat_content)

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    concat_file.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr[:500]}")

    return output_path


def add_subtitles(video_path: str, subtitle_path: str, output_path: str) -> str:
    """
    Burn subtitles into video using FFmpeg.
    Returns the output path.
    """
    if not is_ffmpeg_available():
        raise RuntimeError("FFmpeg is not installed or not in PATH")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles={subtitle_path}",
        "-c:a", "copy",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg subtitle burn failed: {result.stderr[:500]}")

    return output_path
