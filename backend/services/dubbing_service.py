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
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Optional

from config import DUBBING_DIR
from repositories.settings_repo import get_setting
from storage.db import get_connection

log = logging.getLogger(__name__)

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

    # ── Step 6: FFmpeg merge ──────────────────────────────────────────
    def _step_merge(self):
        _update_task(self.task_id, status=ST_MERGING, progress=92, current_step="Merging final video")

        # 6a. Concatenate dubbed segments with proper timing (silence padding)
        dubbed_concat = str(self.work_dir / "dubbed_full.wav")
        self._concat_dubbed_audio(dubbed_concat)

        # 6b. Mix dubbed voice with BGM
        mixed_audio = str(self.work_dir / "mixed_audio.wav")
        if os.path.exists(self.bgm_path):
            cmd = [
                "ffmpeg", "-y",
                "-i", self.bgm_path,
                "-i", dubbed_concat,
                "-filter_complex",
                "[0:a]volume=0.3[bgm];[1:a]volume=1.5[voice];[bgm][voice]amix=inputs=2:duration=longest:dropout_transition=2[aout]",
                "-map", "[aout]",
                mixed_audio,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                log.warning("[Dubbing] BGM mixing failed, using voice only: %s", r.stderr[:300])
                mixed_audio = dubbed_concat
        else:
            mixed_audio = dubbed_concat

        # 6c. Replace audio in original video
        src_video = self.task["source_video_path"]
        out_video = str(self.work_dir / f"dubbed_{self.task['target_language']}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-i", src_video,
            "-i", mixed_audio,
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
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

    def _concat_dubbed_audio(self, output_path: str):
        """Concatenate dubbed segments with silence padding to match original timing."""
        import torchaudio
        import torch

        # Load original audio to get total duration and sample rate
        orig_wav, sr = torchaudio.load(self.vocals_path)
        total_duration = orig_wav.shape[1] / sr

        # Create silent canvas
        canvas = torch.zeros(1, int(total_duration * sr) + sr)  # +1s buffer

        for seg in self.dubbed_files:
            try:
                dub_wav, dub_sr = torchaudio.load(seg["path"])
                # Resample if needed
                if dub_sr != sr:
                    dub_wav = torchaudio.functional.resample(dub_wav, dub_sr, sr)

                start_sample = int(seg["start"] * sr)
                dub_len = dub_wav.shape[1]
                end_sample = min(start_sample + dub_len, canvas.shape[1])

                if start_sample < canvas.shape[1]:
                    canvas[0, start_sample:end_sample] = dub_wav[0, :end_sample - start_sample]
            except Exception as exc:
                log.warning("[Dubbing] failed to place segment %s: %s", seg["path"], exc)

        torchaudio.save(output_path, canvas, sr)


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
