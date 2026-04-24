"""
Demucs integration — vocal / background separation on Apple MPS (or CUDA).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import torch
import torchaudio

log = logging.getLogger(__name__)

_device = None
_model_cache = {}


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
    log.info("[Demucs] device = %s", _device)
    return _device


def _load_model(model_name: str = "htdemucs"):
    """Load demucs model (cached)."""
    if model_name in _model_cache:
        return _model_cache[model_name]

    from demucs.pretrained import get_model
    model = get_model(model_name)
    device = _get_device()
    model = model.to(device)
    model.eval()
    _model_cache[model_name] = model
    log.info("[Demucs] model %s loaded on %s", model_name, device)
    return model


def separate_vocals(
    audio_path: str,
    output_dir: str | None = None,
    model_name: str = "htdemucs",
) -> tuple[str, str]:
    """Separate *audio_path* into vocals and other (BGM).

    Returns (vocals_wav_path, bgm_wav_path).
    Uses the demucs low-level API for MPS support.
    """

    audio_path = str(audio_path)
    if output_dir is None:
        output_dir = str(Path(audio_path).parent / "demucs_out")

    os.makedirs(output_dir, exist_ok=True)

    device = _get_device()
    model = _load_model(model_name)

    # Load audio via torchaudio (more robust for edge-case formats)
    raw_wav, raw_sr = torchaudio.load(audio_path)
    # Resample to model's expected sample rate
    if raw_sr != model.samplerate:
        raw_wav = torchaudio.functional.resample(raw_wav, raw_sr, model.samplerate)
    # Convert to model's expected channel count
    target_ch = model.audio_channels
    if raw_wav.shape[0] > target_ch:
        raw_wav = raw_wav[:target_ch]
    elif raw_wav.shape[0] < target_ch:
        # Mix down to mono then expand
        raw_wav = raw_wav.mean(0, keepdim=True)
        if target_ch > 1:
            raw_wav = raw_wav.expand(target_ch, -1)
    wav = raw_wav

    # Move to device
    ref = wav.mean(0)  # reference for output
    wav = wav.to(device)

    with torch.no_grad():
        from demucs.apply import apply_model
        stems = apply_model(model, wav.unsqueeze(0), progress=False)[0]  # (sources, channels, samples)

    # stems order matches model.sources
    source_names = model.sources
    vocals_idx = source_names.index("vocals")

    vocals_tensor = stems[vocals_idx].cpu()
    bgm_tensors = [stems[i].cpu() for i in range(len(source_names)) if i != vocals_idx]
    bgm_tensor = sum(bgm_tensors) if bgm_tensors else torch.zeros_like(vocals_tensor)

    sr = model.samplerate

    vocals_path = os.path.join(output_dir, "vocals.wav")
    bgm_path = os.path.join(output_dir, "bgm.wav")

    torchaudio.save(vocals_path, vocals_tensor, sr)
    torchaudio.save(bgm_path, bgm_tensor, sr)

    log.info("[Demucs] vocals → %s  bgm → %s", vocals_path, bgm_path)
    return vocals_path, bgm_path
