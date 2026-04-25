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
import re
import uuid
from pathlib import Path
from typing import Optional

from config import DUBBING_DIR
from repositories.settings_repo import get_setting
from storage.db import get_connection

log = logging.getLogger(__name__)

# ── TransVideo-style audio helpers ─────────────────────────────────────
import shutil
from pydub import AudioSegment


def _get_audio_duration_pydub(audio_file: str) -> float:
    """Get audio duration in seconds using pydub."""
    try:
        audio = AudioSegment.from_file(audio_file)
        return len(audio) / 1000.0
    except Exception:
        return 0.0


def _adjust_audio_speed(input_file: str, output_file: str, speed_factor: float) -> bool:
    """Adjust audio speed without pitch change using ffmpeg atempo filter.
    Chains multiple filters if speed_factor > 2.0 (FFmpeg limit)."""
    if abs(speed_factor - 1.0) < 0.01:
        shutil.copy2(input_file, output_file)
        return True

    filters = []
    temp_factor = speed_factor
    while temp_factor > 2.0:
        filters.append("atempo=2.0")
        temp_factor /= 2.0
    if temp_factor < 0.5:
        while temp_factor < 0.5:
            filters.append("atempo=0.5")
            temp_factor /= 0.5
    filters.append(f"atempo={temp_factor}")
    filter_str = ",".join(filters)

    cmd = ['ffmpeg', '-y', '-i', input_file, '-filter:a', filter_str, '-ar', '44100', '-ac', '2', output_file]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        log.warning("[Dubbing] FFmpeg speed adjustment failed: %s", e)
        shutil.copy2(input_file, output_file)
        return False


def _char_weight(text: str) -> float:
    total = 0.0
    for ch in str(text):
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF or 0x3040 <= code <= 0x30FF or 0xFF01 <= code <= 0xFF5E:
            total += 1.75
        elif 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF:
            total += 1.5
        else:
            total += 1.0
    return total


def _split_dialogue_text(text: str, max_weight: int = 32) -> list[str]:
    parts = re.split(r'(?<=[。！？!?；;])|(?<=[，,、])', str(text).strip())
    chunks = []
    current = ""
    for part in [p.strip() for p in parts if p.strip()]:
        if current and _char_weight(current + part) > max_weight:
            chunks.append(current)
            current = part
        else:
            current += part
    if current:
        chunks.append(current)
    return chunks or [str(text).strip()]


def _split_segment_by_text(seg: dict, text_key: str = "translated_text") -> list[dict]:
    chunks = _split_dialogue_text(seg.get(text_key, ""))
    if len(chunks) <= 1:
        return [seg]

    start = float(seg["start"])
    end = float(seg["end"])
    duration = max(0.0, end - start)
    total_weight = sum(_char_weight(chunk) for chunk in chunks) or len(chunks)
    cursor = start
    result = []
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            chunk_end = end
        else:
            chunk_end = cursor + duration * (_char_weight(chunk) / total_weight)
        item = dict(seg)
        item[text_key] = chunk
        item["start"] = cursor
        item["end"] = chunk_end
        result.append(item)
        cursor = chunk_end
    return result

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
            item = {
                "original_text": seg["text"],
                "translated_text": translated_lines.get(i, seg["text"]),
                "start": seg["start"],
                "end": seg["end"],
            }
            result.extend(_split_segment_by_text(item))

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

    # ── Step 6: FFmpeg merge (TransVideo chunk-based approach) ────────────
    def _step_merge(self):
        _update_task(self.task_id, status=ST_MERGING, progress=92, current_step="Merging final video")

        # Merge TTS audio with BGM (TransVideo chunk-based mixing)
        dubbed_concat = str(self.work_dir / "audio_dubbing.wav")
        timings_path = str(self.work_dir / "timings.json")
        self._merge_tts_audio(dubbed_concat, timings_path)

        # Combine video + mixed audio (BGM is already mixed in)
        src_video = self.task["source_video_path"]
        out_video = str(self.work_dir / f"dubbed_{self.task['target_language']}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-i", src_video,
            "-i", dubbed_concat,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-movflags", "+faststart",
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

    # ── TransVideo chunk-based merge ───────────────────────────────────
    def _merge_tts_audio(self, output_path: str, timings_path: str):
        """Chunk-based audio mixing (TransVideo algorithm).

        Groups segments into chunks by gaps > 0.5s, applies uniform speed
        adjustment per chunk using FFmpeg atempo, overlays onto BGM using pydub.
        """
        segments = self.dubbed_files  # [{path, start, end}, ...]

        # Build segment list in TransVideo format
        seg_list = []
        for i, seg in enumerate(segments):
            seg_list.append({
                'index': i,
                'start': seg['start'],
                'end': seg['end'],
                'tts_file': seg['path'],
            })

        # Load BGM
        bg = AudioSegment.from_file(self.bgm_path)
        # Background gain (+1.5 dB)
        if bg.dBFS != float("-inf"):
            bg = bg.apply_gain(1.5)

        vocal = AudioSegment.silent(duration=len(bg))
        placement_map = []

        # 1. Group segments into chunks (TOLERANCE = 0.5s gap)
        TOLERANCE = 0.5
        chunks = []
        current_chunk = []

        for i, seg in enumerate(seg_list):
            current_chunk.append(seg)
            if i + 1 < len(seg_list):
                gap = seg_list[i + 1]['start'] - seg['end']
                if gap > TOLERANCE:
                    chunks.append(current_chunk)
                    current_chunk = []
            else:
                chunks.append(current_chunk)

        # 2. Process each chunk
        for chunk_idx, chunk in enumerate(chunks):
            if not chunk:
                continue

            chunk_start_sec = chunk[0]['start']
            chunk_end_sec = chunk[-1]['end']
            absolute_limit_sec = chunk_end_sec + 0.5

            # Find next chunk start for absolute limit
            next_chunk_idx = chunk_idx + 1
            while next_chunk_idx < len(chunks):
                if chunks[next_chunk_idx]:
                    absolute_limit_sec = chunks[next_chunk_idx][0]['start']
                    break
                next_chunk_idx += 1

            available_total_dur = absolute_limit_sec - chunk_start_sec

            # Calculate actual TTS durations
            actual_tts_durations = []
            valid_chunk_segs = []
            for seg in chunk:
                if os.path.exists(seg['tts_file']):
                    actual_tts_durations.append(_get_audio_duration_pydub(seg['tts_file']))
                    valid_chunk_segs.append(seg)

            if not valid_chunk_segs:
                continue

            total_actual_tts_dur = sum(actual_tts_durations)
            internal_gaps = []
            for j in range(len(valid_chunk_segs) - 1):
                internal_gaps.append(valid_chunk_segs[j + 1]['start'] - valid_chunk_segs[j]['end'])
            total_internal_gap = sum(internal_gaps)

            # 3. Calculate speed factor
            speed_factor = 1.0
            keep_gaps = True
            if available_total_dur > 0:
                speed_factor = (total_actual_tts_dur + total_internal_gap) / available_total_dur
                if speed_factor > 1.2:
                    speed_factor = total_actual_tts_dur / available_total_dur
                    keep_gaps = False

            speed_factor = min(max(0.9, speed_factor), 1.35)

            log.info("[Dubbing] Chunk %03d | speed=%.2fx | tts=%.2fs | available=%.2fs",
                     chunk_idx, speed_factor, total_actual_tts_dur, available_total_dur)

            # 4. Reconstruct timeline and overlay
            current_time_ms = int(chunk_start_sec * 1000)
            cache_dir = self.work_dir / "adjusted"
            cache_dir.mkdir(parents=True, exist_ok=True)

            for j, seg in enumerate(valid_chunk_segs):
                tts_file = seg['tts_file']
                idx = seg['index']
                processed_file = str(cache_dir / f"adj_{idx:04d}.wav")

                _adjust_audio_speed(tts_file, processed_file, speed_factor)
                seg_audio = AudioSegment.from_file(processed_file)
                target_ms = max(1, int((seg['end'] - seg['start']) * 1000))
                if len(seg_audio) > target_ms * 1.2:
                    seg_audio = seg_audio[:target_ms]

                vocal = vocal.overlay(seg_audio, position=current_time_ms)

                seg_dur_ms = len(seg_audio)
                placement_map.append({
                    'segment_index': idx,
                    'actual_start': current_time_ms / 1000.0,
                    'actual_end': (current_time_ms + seg_dur_ms) / 1000.0,
                })

                current_time_ms += seg_dur_ms
                if keep_gaps and j < len(internal_gaps):
                    current_time_ms += int((internal_gaps[j] / speed_factor) * 1000)

        # 5. Mix: vocals -3.5dB, overlay onto BGM
        if vocal.dBFS != float("-inf"):
            vocal = vocal.apply_gain(-3.5)

        final_audio = bg.overlay(vocal)
        final_audio.export(output_path, format="wav")

        # Save timings
        with open(timings_path, "w", encoding="utf-8") as f:
            json.dump({"placement_map": placement_map}, f, ensure_ascii=False, indent=2)

        log.info("[Dubbing] mixed %d chunks, %d segments → %s",
                 len(chunks), len(placement_map), output_path)


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


def get_completed_projects_for_dubbing() -> list[dict]:
    """Return all completed projects with their episodes and existing dubbing tasks."""
    from repositories import project_repo

    projects = project_repo.get_all_projects()
    completed = [p for p in projects if p.get("status") == "completed"]

    result = []
    for proj in completed:
        episodes = project_repo.get_episodes(proj["project_id"])
        ep_list = []
        for ep in episodes:
            video_url = ep.get("video_url")
            if not video_url:
                continue

            # Find existing dubbing tasks for this episode's video
            conn = get_connection()
            rows = conn.execute(
                "SELECT * FROM dubbing_tasks WHERE source_video_path LIKE ? ORDER BY created_at DESC LIMIT 5",
                (f"%{ep['episode_id']}%",)
            ).fetchall()
            conn.close()

            dub_tasks = [dict(r) for r in rows]
            ep_list.append({
                "episode_id": ep["episode_id"],
                "episode_number": ep.get("episode_number", 0),
                "title": ep.get("title", ""),
                "video_url": video_url,
                "dubbing_tasks": dub_tasks,
            })

        if ep_list:
            result.append({
                "project_id": proj["project_id"],
                "title": proj.get("title", ""),
                "episodes": ep_list,
            })

    return result


def start_batch_dubbing(
    project_id: str,
    target_language: str,
    episode_ids: list[str] | None = None,
    source_language: str | None = None,
) -> list[dict]:
    """Start dubbing for selected episodes of a completed project.

    Returns list of {task_id, episode_id, status}.
    """
    from repositories import project_repo
    from config import OUTPUTS_DIR

    episodes = project_repo.get_episodes(project_id)
    if episode_ids:
        episodes = [ep for ep in episodes if ep["episode_id"] in episode_ids]

    tasks = []
    for ep in episodes:
        video_url = ep.get("video_url")
        if not video_url:
            continue

        # Resolve actual video path from URL
        # video_url format: /videos/{project_id}/{episode_id}.mp4
        actual_path = str(OUTPUTS_DIR / video_url.replace("/videos/", ""))
        if not os.path.exists(actual_path):
            # Fallback: try old flat path
            actual_path = str(OUTPUTS_DIR / f"{ep['episode_id']}.mp4")
            if not os.path.exists(actual_path):
                log.warning("[Dubbing] episode video not found: %s", ep["episode_id"])
                continue

        task_id = start_dubbing(actual_path, target_language, source_language)
        tasks.append({
            "task_id": task_id,
            "episode_id": ep["episode_id"],
            "episode_number": ep.get("episode_number", 0),
            "title": ep.get("title", ""),
            "status": "pending",
        })

    return tasks
