"""
WhisperX integration — speech-to-text with word-level timestamps on MPS.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import torch

log = logging.getLogger(__name__)

_device = None
_model_cache: dict = {}


def _get_device() -> str:
    global _device
    if _device is not None:
        return _device
    if torch.backends.mps.is_available():
        _device = "mps"
    elif torch.cuda.is_available():
        _device = "cuda"
    else:
        _device = "cpu"
    log.info("[WhisperX] device = %s", _device)
    return _device


def _load_model(model_name: str = "large-v3-turbo", language: Optional[str] = None):
    """Load (and cache) whisperx model."""
    key = (model_name, language)
    if key in _model_cache:
        return _model_cache[key]

    import whisperx  # lazy — heavy import

    # faster-whisper (CTranslate2) only supports CPU and CUDA, not MPS
    # Use CPU on Mac — faster-whisper is still fast with int8 quantization
    asr_device = "cpu"
    compute_type = "int8"

    log.info("[WhisperX] loading model=%s device=%s compute_type=%s", model_name, asr_device, compute_type)
    model = whisperx.load_model(model_name, asr_device, compute_type=compute_type, language=language)

    _model_cache[key] = model
    return model


def transcribe(
    audio_path: str,
    language: Optional[str] = None,
    model_name: str = "large-v3-turbo",
) -> list[dict]:
    """Transcribe *audio_path* and return segments with word-level timestamps.

    Returns list of dicts:
        [{"text": "...", "start": 0.0, "end": 2.5}, ...]
    """
    import whisperx

    device = _get_device()
    model = _load_model(model_name, language)

    audio = whisperx.load_audio(audio_path)
    result = model.transcribe(audio, batch_size=16, language=language)

    segments = result.get("segments", [])
    if not segments:
        return []

    # Align for word-level timestamps
    try:
        lang = result.get("language", language or "en")
        align_device = _get_device()  # alignment model can use MPS
        model_a, metadata = whisperx.load_align_model(lang, align_device)
        result_aligned = whisperx.align(
            result["segments"],
            model_a,
            metadata,
            audio,
            align_device,
            return_char_alignments=False,
        )
        segments = result_aligned.get("segments", segments)
    except Exception as exc:
        log.warning("[WhisperX] alignment failed (non-fatal): %s", exc)

    # Normalize segments
    out = []
    for seg in segments:
        words = seg.get("words", [])
        if words:
            out.append({
                "text": seg["text"].strip(),
                "start": words[0].get("start", seg.get("start", 0.0)),
                "end": words[-1].get("end", seg.get("end", 0.0)),
                "words": [
                    {"word": w.get("word", w.get("text", "")),
                     "start": w.get("start", 0.0),
                     "end": w.get("end", 0.0)}
                    for w in words
                ],
            })
        else:
            out.append({
                "text": seg["text"].strip(),
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
            })

    log.info("[WhisperX] transcribed %d segments from %s", len(out), audio_path)
    return out
