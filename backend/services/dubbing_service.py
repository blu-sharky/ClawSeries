"""
Dubbing pipeline service — orchestrates the full video dubbing workflow.

Pipeline:
  1. Extract audio from video (FFmpeg)
  2. Separate vocals / BGM (Demucs)
  3. Transcribe vocals (WhisperX)
  4. Translate transcript (LLM)
  5. Clone voice per segment (VoxCPM2)
  6. Merge: dubbed voice + BGM + video (FFmpeg)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from config import DUBBING_DIR
from repositories.settings_repo import get_setting
from storage.db import get_connection

log = logging.getLogger(__name__)

# ── YouDub speed-adjustment constants (copied verbatim) ────────────────
BASE_FACTOR_MIN = 0.8
BASE_FACTOR_MAX = 1.2
BASE_FACTOR_SAFETY = 0.99
LOCAL_FACTOR_MIN = 0.9
LOCAL_FACTOR_MAX = 1.1
SPEED_NOOP_EPSILON = 1e-2

# ── YouDub audio helpers (copied verbatim from audio.py) ───────────────

import numpy as np
from pathlib import Path as _Path


def _audio_duration(file: _Path) -> tuple[float, int]:
    """Return (duration_seconds, sample_rate) for an audio file."""
    import librosa
    y, sr = librosa.load(str(file), sr=None)
    return len(y) / sr, sr


def _base_speed_factor(translation: list[dict], tts_files: list[_Path]) -> float:
    cur_total = 0.0
    des_total = 0.0
    for segment, tts_file in zip(translation, tts_files):
        dur, _ = _audio_duration(tts_file)
        cur_total += dur
        des_total += max(0.0, (segment["end_time"] - segment["start_time"]) / 1000.0)
    if cur_total <= 0:
        return 1.0
    factor = des_total / cur_total * BASE_FACTOR_SAFETY
    return max(min(factor, BASE_FACTOR_MAX), BASE_FACTOR_MIN)


def _stretch_segment(audio_file: _Path, ratio: float, target_sec: float, cache_dir: _Path) -> tuple[np.ndarray, int]:
    import librosa
    from audiostretchy.stretch import stretch_audio

    if abs(ratio - 1.0) < SPEED_NOOP_EPSILON:
        y, sr = librosa.load(str(audio_file), sr=None)
        return y, sr
    out_path = cache_dir / audio_file.name
    stretch_audio(str(audio_file), str(out_path), ratio=ratio)
    y, sr = librosa.load(str(out_path), sr=None)
    return y[: int(target_sec * sr)], sr


def _local_factor(current_sec: float, base: float, desired_sec: float) -> float:
    first = current_sec * base
    if first <= 1e-3:
        return 1.0
    return max(min(desired_sec / first, LOCAL_FACTOR_MAX), LOCAL_FACTOR_MIN)


def _silence(seconds: float, sample_rate: int) -> np.ndarray:
    return np.zeros(int(seconds * sample_rate), dtype=np.float32)


# ── status constants ──────────────────────────────────────────────────
ST_PENDING = "pending"
ST_EXTRACTING = "extracting_audio"
ST_SEPARATING = "separating_vocals"
ST_TRANSCRIBING = "transcribing"
ST_TRANSLATING = "translating"
ST_GENERATING = "generating_speech"
ST_MERGING = "merging"
ST_COMPLETED = "completed"
ST_FAILED = "failed"

PIPELINE_STEPS = [
    (ST_EXTRACTING, "Extracting audio"),
    (ST_SEPARATING, "Separating vocals"),
    (ST_TRANSCRIBING, "Transcribing speech"),
    (ST_TRANSLATING, "Translating"),
    (ST_GENERATING, "Generating dubbed speech"),
    (ST_MERGING, "Merging final video"),
]

# ── DB helpers ────────────────────────────────────────────────────────

def _create_task(source_video: str, target_lang: str, source_lang: str | None) -> str:
    task_id = f"dub_{uuid.uuid4().hex[:12]}"
    conn = get_connection()
    conn.execute(
        "INSERT INTO dubbing_tasks (task_id, source_video_path, target_language, source_language, status, progress) "
        "VALUES (?, ?, ?, ?, 'pending', 0)",
        (task_id, source_video, target_lang, source_lang),
    )
    conn.commit()
    conn.close()
    return task_id


def _update_task(task_id: str, **kw):
    sets = ", ".join(f"{k} = ?" for k in kw)
    vals = list(kw.values()) + [task_id]
    conn = get_connection()
    conn.execute(f"UPDATE dubbing_tasks SET {sets} WHERE task_id = ?", vals)
    conn.commit()
    conn.close()


def get_task(task_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM dubbing_tasks WHERE task_id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_tasks() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM dubbing_tasks ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Pipeline implementation ───────────────────────────────────────────

class DubbingPipeline:
    """Stateful pipeline for a single dubbing task."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.task = get_task(task_id)
        self.work_dir = Path(DUBBING_DIR) / task_id
        self.work_dir.mkdir(parents=True, exist_ok=True)

    # ── public entry point (sync, meant to be run in a thread) ────────
    def run(self):
        try:
            self._step_extract_audio()
            self._step_separate_vocals()
            segments = self._step_transcribe()
            translated = self._step_translate(segments)
            self._step_generate_speech(translated)
            self._step_merge()
            _update_task(self.task_id, status=ST_COMPLETED, progress=100, current_step="Done")
        except Exception as exc:
            log.exception("[Dubbing] task %s failed", self.task_id)
            _update_task(self.task_id, status=ST_FAILED, error_message=str(exc))

    # ── Step 1: extract audio ─────────────────────────────────────────
    def _step_extract_audio(self):
        _update_task(self.task_id, status=ST_EXTRACTING, progress=5, current_step="Extracting audio from video")
        src = self.task["source_video_path"]
        out = str(self.work_dir / "audio.wav")
        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "44100", "-ac", "2",
            out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"FFmpeg audio extraction failed: {r.stderr[:500]}")
        self.audio_path = out
        log.info("[Dubbing] audio extracted → %s", out)

    # ── Step 2: demucs vocal separation ───────────────────────────────
    def _step_separate_vocals(self):
        _update_task(self.task_id, status=ST_SEPARATING, progress=15, current_step="Separating vocals from background")
        from integrations.demucs_sep import separate_vocals
        self.vocals_path, self.bgm_path = separate_vocals(
            self.audio_path,
            output_dir=str(self.work_dir / "demucs"),
        )
        log.info("[Dubbing] vocals=%s bgm=%s", self.vocals_path, self.bgm_path)

    # ── Step 3: whisperx transcription ────────────────────────────────
    def _step_transcribe(self) -> list[dict]:
        _update_task(self.task_id, status=ST_TRANSCRIBING, progress=30, current_step="Transcribing speech")
        from integrations.whisperx_stt import transcribe
        src_lang = self.task.get("source_language") or None

        # Convert vocals to 16kHz mono for whisperx
        import torchaudio
        vocals_16k = str(self.work_dir / "vocals_16k.wav")
        wav, sr = torchaudio.load(self.vocals_path)
        wav = torchaudio.functional.resample(wav, sr, 16000)
        if wav.shape[0] > 1:
            wav = wav.mean(0, keepdim=True)
        torchaudio.save(vocals_16k, wav, 16000)

        self.segments = transcribe(vocals_16k, language=src_lang)
        if not self.segments:
            raise RuntimeError("No speech detected in the source video")
        # Save segments
        with open(self.work_dir / "segments.json", "w", encoding="utf-8") as f:
            json.dump(self.segments, f, ensure_ascii=False, indent=2)
        log.info("[Dubbing] %d segments transcribed", len(self.segments))
        return self.segments

    # ── Step 4: LLM translation ───────────────────────────────────────
    def _step_translate(self, segments: list[dict]) -> list[dict]:
        _update_task(self.task_id, status=ST_TRANSLATING, progress=45, current_step="Translating transcript")

        target_lang = self.task["target_language"]
        # Build a batch of sentences for the LLM
        texts = [s["text"] for s in segments]
        joined = "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))

        from integrations.llm import call_llm
        lang_names = {
            "en": "English", "zh": "Chinese (Mandarin)", "ja": "Japanese",
            "ko": "Korean", "es": "Spanish", "fr": "French",
            "de": "German", "pt": "Portuguese", "hi": "Hindi",
            "th": "Thai", "ru": "Russian", "ar": "Arabic", "it": "Italian",
        }
        target_name = lang_names.get(target_lang, target_lang)

        system = (
            "You are a professional translator for film/TV dialogue. "
            "Translate each line into " + target_name + ". "
            "Preserve the emotional tone, urgency, and dramatic effect of each line. "
            "If a line is angry, translate it to sound angry. If sad, sound sad. "
            "Keep the same number of lines. Output ONLY the translations, one per line, "
            "with the same [index] prefix format."
        )
        user_msg = f"Translate these lines to {target_name}:\n\n{joined}"

        # Use sync call via asyncio.run — we're in a thread
        loop = asyncio.new_event_loop()
        try:
            result_text = loop.run_until_complete(
                call_llm([
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ], temperature=0.3, max_tokens=4096)
            )
        finally:
            loop.close()

        # Parse translations
        translated_lines = {}
        for line in result_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Try to extract [index]
            if line.startswith("["):
                bracket_end = line.index("]") if "]" in line else -1
                if bracket_end > 0:
                    try:
                        idx = int(line[1:bracket_end])
                        translated_lines[idx] = line[bracket_end + 1:].strip()
                    except (ValueError, IndexError):
                        pass

        # Fallback: if parsing failed, split by lines
        if not translated_lines:
            raw_lines = [l.strip() for l in result_text.strip().split("\n") if l.strip()]
            for i, tl in enumerate(raw_lines[:len(segments)]):
                translated_lines[i] = tl

        # Merge back
        result = []
        for i, seg in enumerate(segments):
            result.append({
                "original_text": seg["text"],
                "translated_text": translated_lines.get(i, seg["text"]),
                "start": seg["start"],
                "end": seg["end"],
            })

        with open(self.work_dir / "translated.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        log.info("[Dubbing] translated %d segments → %s", len(result), target_name)
        return result

    # ── Step 5: VoxCPM2 voice cloning per segment ─────────────────────
    def _step_generate_speech(self, translated: list[dict]):
        from integrations.voxcpm_tts import clone_speech_segment

        total = len(translated)
        dubbed_files = []

        for i, seg in enumerate(translated):
            pct = 55 + int(35 * (i / max(total, 1)))
            _update_task(
                self.task_id,
                status=ST_GENERATING,
                progress=pct,
                current_step=f"Generating speech {i + 1}/{total}",
            )

            out_path = str(self.work_dir / f"dub_{i:04d}.wav")
            clone_speech_segment(
                text=seg["translated_text"],
                full_audio_path=self.vocals_path,
                full_transcript="",
                seg_start=seg["start"],
                seg_end=seg["end"],
                output_path=out_path,
            )
            dubbed_files.append({
                "path": out_path,
                "start": seg["start"],
                "end": seg["end"],
            })

        self.dubbed_files = dubbed_files
        log.info("[Dubbing] generated %d dubbed segments", len(dubbed_files))

    # ── Step 6: FFmpeg merge (YouDub two-pass approach) ────────────────
    def _step_merge(self):
        _update_task(self.task_id, status=ST_MERGING, progress=92, current_step="Merging final video")

        # 6a. Merge TTS audio with speed adjustment (YouDub algorithm)
        dubbed_concat = str(self.work_dir / "audio_dubbing.wav")
        timings_path = str(self.work_dir / "timings.json")
        self._merge_tts_audio(dubbed_concat, timings_path)

        # 6b. Two-pass FFmpeg merge (YouDub approach)
        # Pass 1: Mix dubbing + BGM (amix with normalize=0)
        mixed_audio = str(self.work_dir / "audio_mixed.m4a")
        if os.path.exists(self.bgm_path):
            cmd = [
                "ffmpeg", "-y",
                "-i", dubbed_concat,
                "-i", self.bgm_path,
                "-filter_complex",
                "[0:a]volume=1.0[a0];[1:a]volume=0.30[a1];[a0][a1]amix=inputs=2:duration=longest:normalize=0[aout]",
                "-map", "[aout]",
                "-c:a", "aac",
                mixed_audio,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                log.warning("[Dubbing] BGM mixing failed, using voice only: %s", r.stderr[:300])
                mixed_audio = dubbed_concat
        else:
            mixed_audio = dubbed_concat

        # Pass 2: Video + mixed audio
        src_video = self.task["source_video_path"]
        out_video = str(self.work_dir / f"dubbed_{self.task['target_language']}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-i", src_video,
            "-i", mixed_audio,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-movflags", "+faststart",
            "-shortest",
            out_video,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"FFmpeg merge failed: {r.stderr[:500]}")

        _update_task(
            self.task_id,
            status=ST_COMPLETED,
            progress=100,
            current_step="Done",
            output_video_path=out_video,
        )
        log.info("[Dubbing] final video → %s", out_video)

    # ── YouDub merge_tts_audio (copied verbatim, adapted for our data format) ─
    def _merge_tts_audio(self, output_path: str, timings_path: str):
        """Merge TTS segments with YouDub speed-adjustment algorithm.

        Our translated segments use seconds for timestamps; YouDub uses milliseconds.
        We convert to ms internally to keep the algorithm identical.
        """
        import librosa
        import numpy as np
        import soundfile as sf
        from audiostretchy.stretch import stretch_audio

        # Build translation list in YouDub format (milliseconds)
        translation = []
        for seg in self.dubbed_files:
            translation.append({
                "start_time": int(seg["start"] * 1000),  # seconds → ms
                "end_time": int(seg["end"] * 1000),
            })

        tts_files = [Path(seg["path"]) for seg in self.dubbed_files]

        for p in tts_files:
            if not p.exists():
                raise FileNotFoundError(f"Missing TTS segment: {p}")

        _, sample_rate = _audio_duration(tts_files[0])
        base = _base_speed_factor(translation, tts_files)

        # Create cache dir for stretched files
        cache_dir = self.work_dir / "stretched"
        cache_dir.mkdir(parents=True, exist_ok=True)

        final_audio = np.zeros(0, dtype=np.float32)
        last_end_ms = 0.0

        for segment, tts_file in zip(translation, tts_files):
            last_end_ms = final_audio.shape[0] / sample_rate * 1000.0
            real_start_ms = max(float(segment["start_time"]), last_end_ms)

            if real_start_ms > last_end_ms:
                final_audio = np.concatenate(
                    [final_audio, _silence((real_start_ms - last_end_ms) / 1000.0, sample_rate)]
                )

            current_sec, _ = _audio_duration(tts_file)
            desired_sec = (segment["end_time"] - real_start_ms) / 1000.0
            speed = base * _local_factor(current_sec, base, desired_sec)
            target_sec = current_sec * speed
            y, _ = _stretch_segment(tts_file, speed, target_sec, cache_dir)

            adjusted_sec = len(y) / sample_rate
            real_end_ms = max(real_start_ms + adjusted_sec * 1000.0, float(segment["end_time"]))
            final_audio = np.concatenate([final_audio, y])
            segment["actual_start_time"] = int(real_start_ms)
            segment["actual_end_time"] = int(real_end_ms)

        sf.write(output_path, final_audio, sample_rate)

        with open(timings_path, "w", encoding="utf-8") as f:
            json.dump({"translation": translation}, f, ensure_ascii=False, indent=2)

        log.info("[Dubbing] merged %d TTS segments → %s (base_speed=%.3f)",
                 len(translation), output_path, base)


# ── Public API ────────────────────────────────────────────────────────

def start_dubbing(source_video: str, target_language: str, source_language: str | None = None) -> str:
    """Create a dubbing task and start it in a background thread.

    Returns task_id.
    """
    task_id = _create_task(source_video, target_language, source_language)

    def _run():
        pipeline = DubbingPipeline(task_id)
        pipeline.run()

    import threading
    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return task_id
