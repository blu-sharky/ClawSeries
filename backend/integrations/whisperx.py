"""
WhisperX integration - speech-to-text with word-level timestamps.
Used for subtitle generation.
"""

import subprocess
import shutil
from pathlib import Path


def is_whisperx_available() -> bool:
    return shutil.which("whisperx") is not None


def transcribe_audio(video_path: str, output_srt_path: str,
                     language: str = "zh") -> str:
    """
    Transcribe audio from video using WhisperX.
    Generates SRT subtitle file.
    Returns the SRT file path.
    Raises RuntimeError if WhisperX is not available.
    """
    if not is_whisperx_available():
        raise RuntimeError(
            "WhisperX is not installed. Install with: pip install whisperx"
        )

    cmd = [
        "whisperx",
        str(video_path),
        "--language", language,
        "--output_format", "srt",
        "--output_dir", str(Path(output_srt_path).parent),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"WhisperX failed: {result.stderr[:500]}")

    return output_srt_path
