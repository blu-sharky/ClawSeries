"""
VoxCPM2 TTS integration — voice cloning on Apple MPS.
Uses the modified VoxCPM from blu-sharky/VoxCPM-modified.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)

_voxcpm_model = None


def _get_model():
    """Lazy-load VoxCPM2 model (singleton)."""
    global _voxcpm_model
    if _voxcpm_model is not None:
        return _voxcpm_model

    import voxcpm

    log.info("[VoxCPM] loading model openbmb/VoxCPM2 ...")
    _voxcpm_model = voxcpm.VoxCPM.from_pretrained(
        "openbmb/VoxCPM2",
        load_denoiser=False,  # skip denoiser to save memory
        optimize=True,
    )
    log.info("[VoxCPM] model loaded")
    return _voxcpm_model


def clone_speech(
    text: str,
    reference_audio_path: str,
    reference_text: str = "",
    output_path: Optional[str] = None,
    cfg_value: float = 2.0,
    inference_timesteps: int = 10,
) -> str:
    """Generate speech by cloning the voice from *reference_audio_path*.

    Uses "Ultimate Cloning" mode (prompt_wav + prompt_text) when reference_text
    is provided, for maximum voice fidelity including emotion and prosody.

    Args:
        text: Target text to speak.
        reference_audio_path: Path to reference audio for voice cloning.
        reference_text: Transcript of the reference audio. If provided, uses
            Ultimate Cloning mode for best fidelity.
        output_path: Where to save the wav. If None, creates a temp file.
        cfg_value: Guidance scale.
        inference_timesteps: Flow-matching steps.

    Returns:
        Path to the generated wav file.
    """
    model = _get_model()

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".wav", prefix="voxcpm_")
        os.close(fd)

    kwargs = dict(
        text=text,
        cfg_value=cfg_value,
        inference_timesteps=inference_timesteps,
    )

    if reference_text:
        # Ultimate Cloning mode — best quality
        kwargs["prompt_wav_path"] = reference_audio_path
        kwargs["prompt_text"] = reference_text
    else:
        # Controllable cloning — reference only
        kwargs["reference_wav_path"] = reference_audio_path

    log.info("[VoxCPM] generating speech for: '%s' (%d chars)", text[:60], len(text))
    wav = model.generate(**kwargs)

    # wav is numpy array
    if isinstance(wav, np.ndarray):
        sr = model.tts_model.sample_rate
        sf.write(output_path, wav, sr)
    else:
        # fallback — shouldn't happen but be safe
        import torchaudio
        import torch
        sr = model.tts_model.sample_rate
        torchaudio.save(output_path, torch.from_numpy(wav).unsqueeze(0), sr)

    log.info("[VoxCPM] saved → %s", output_path)
    return output_path


def clone_speech_segment(
    text: str,
    full_audio_path: str,
    full_transcript: str,
    seg_start: float,
    seg_end: float,
    output_path: Optional[str] = None,
) -> str:
    """Clone speech for a single segment, extracting the reference from the
    full source audio. Uses the segment audio as reference for best emotion match.

    Args:
        text: Translated text to speak.
        full_audio_path: Path to full vocals audio.
        full_transcript: Full transcript (used as context).
        seg_start: Segment start time in seconds.
        seg_end: Segment end time in seconds.
        output_path: Where to save.

    Returns:
        Path to generated wav.
    """
    # Extract the segment audio as reference
    import torchaudio

    wav, sr = torchaudio.load(full_audio_path)
    start_sample = int(seg_start * sr)
    end_sample = int(seg_end * sr)
    # Clamp
    start_sample = max(0, start_sample)
    end_sample = min(wav.shape[1], end_sample)

    seg_wav = wav[:, start_sample:end_sample]

    # Save segment to temp file
    fd, seg_path = tempfile.mkstemp(suffix=".wav", prefix="seg_ref_")
    os.close(fd)
    torchaudio.save(seg_path, seg_wav, sr)

    try:
        # Use the segment as reference with Ultimate Cloning
        # Auto-transcribe the segment text from the full transcript
        result = clone_speech(
            text=text,
            reference_audio_path=seg_path,
            reference_text="",  # short segment — use controllable cloning
            output_path=output_path,
        )
        return result
    finally:
        # Clean up temp segment file
        try:
            os.unlink(seg_path)
        except OSError:
            pass
