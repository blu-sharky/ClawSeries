"""
Subtitle generation utility — converts WhisperX segments to SRT files.
"""


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list[dict], output_path: str) -> str:
    """Convert WhisperX segments to an SRT subtitle file.

    Args:
        segments: List of dicts with "text", "start", "end" keys.
                  Format from whisperx_stt.transcribe().
        output_path: Where to write the .srt file.

    Returns:
        The output_path.
    """
    lines = []
    for i, seg in enumerate(segments, start=1):
        text = seg.get("text", "").strip()
        if not text:
            continue
        start = seg.get("start", 0.0)
        end = seg.get("end", start + 1.0)
        lines.append(str(i))
        lines.append(f"{_format_timestamp(start)} --> {_format_timestamp(end)}")
        lines.append(text)
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path
