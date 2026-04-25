"""Shot video generation node - Stage 4 of production pipeline.

For each shot:
1. Generate per-shot dual prompts (image_prompt + video_prompt) via LLM
2. Generate a first-frame image using image_prompt + character references
3. Generate video using video_prompt + first-frame (or character sheets as fallback)
"""

import hashlib
import json
import re
from pathlib import Path

from langgraph.types import interrupt

from graphs.state import ProductionState
from repositories import project_repo, agent_repo
from repositories.shot_repo import get_shots_by_episode, update_shot, add_shot_trace
from repositories.production_event_repo import (
    add_production_event,
    update_project_stage,
    is_stage_completed,
    get_assets,
)
from repositories.settings_repo import get_setting
from routers.websocket import send_agent_monitor
from integrations.video import is_video_configured, generate_video, get_video_config, parse_duration_seconds
from integrations.image import is_image_configured, generate_image, is_image_demo_mode
from integrations.llm import call_llm, is_llm_configured
from config import RENDERS_DIR, ASSETS_DIR, project_renders_dir, project_assets_dir
from models import ProductionStage, STAGE_AGENT_MAP
from prompt_reference import build_shot_dual_prompt_request, build_default_dual_prompts


def _get_storyboard_entry(episode: dict, shot_number: int) -> dict | None:
    """Look up storyboard entry by shot_number."""
    sb_json = episode.get("storyboard_json")
    storyboard = json.loads(sb_json) if isinstance(sb_json, str) else (sb_json or [])
    for entry in storyboard:
        if entry.get("shot_number") == shot_number:
            return entry
    return None


def _get_script_scene(episode: dict, scene_number: int) -> dict | None:
    """Look up script scene by scene_number."""
    script_json = episode.get("script_json")
    script = json.loads(script_json) if isinstance(script_json, str) else (script_json or {})
    for scene in script.get("scenes", []):
        if scene.get("scene_number") == scene_number:
            return scene
    return None


def _identify_characters_in_shot(
    shot_desc: str, dialogues: list[dict], character_assets: list[dict],
) -> list[dict]:
    """Identify which characters appear in a shot based on dialogues and description."""
    mentioned_names = set()
    for d in dialogues:
        if d.get("character"):
            mentioned_names.add(d["character"])
    appearing = []
    for ca in character_assets:
        name = ca.get("name", "")
        if name in mentioned_names or name in shot_desc:
            appearing.append(ca)
    return appearing


def _get_char_sheet_paths(appearing_chars: list[dict]) -> list[str]:
    """Resolve filesystem paths for appearing character sheet images."""
    paths = []
    for ca in appearing_chars:
        if ca.get("image_path"):
            real_path = str(ASSETS_DIR / ca["image_path"].replace("/assets/", ""))
            if Path(real_path).exists():
                paths.append(real_path)
    return paths


async def _generate_shot_prompts(
    shot: dict, episode: dict, character_assets: list[dict], series_type: str,
) -> dict:
    """Generate dual prompts (image_prompt + video_prompt) for a single shot.

    Returns dict with keys: image_prompt, video_prompt, appearing_characters
    """
    shot_number = shot.get("shot_number", 0)
    description = shot.get("description", "")

    # Cross-reference with storyboard for dialogues
    sb_entry = _get_storyboard_entry(episode, shot_number)
    scene_number = sb_entry.get("scene_number") if sb_entry else None
    scene = _get_script_scene(episode, scene_number) if scene_number else None

    # Identify appearing characters
    dialogues = sb_entry.get("dialogues", []) if sb_entry else []
    if not dialogues and scene:
        dialogues = scene.get("dialogues", [])
    appearing_chars = _identify_characters_in_shot(description, dialogues, character_assets)

    # Generate prompts via LLM
    if is_llm_configured():
        messages, ctx = build_shot_dual_prompt_request(
            shot=shot,
            storyboard_entry=sb_entry,
            scene=scene,
            appearing_characters=appearing_chars,
            series_type=series_type,
        )
        try:
            response = await call_llm(messages, temperature=0.4, max_tokens=1024)
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                parsed = json.loads(json_match.group())
                image_prompt = parsed.get("image_prompt", description)
                video_prompt = parsed.get("video_prompt", description)
                return {
                    "image_prompt": image_prompt,
                    "video_prompt": video_prompt,
                    "appearing_characters": appearing_chars,
                }
        except Exception as e:
            print(f"[Shots] LLM prompt generation failed for shot {shot_number}: {e}")

    # Fallback
    defaults = build_default_dual_prompts(shot, sb_entry)
    return {
        "image_prompt": defaults["image_prompt"],
        "video_prompt": defaults["video_prompt"],
        "appearing_characters": appearing_chars,
    }


async def shots_node(state: ProductionState) -> dict:
    """Generate first-frame images and videos for all shots in an episode.

    This is Stage 4 of the production pipeline.
    For each shot:
    1. Generate dual prompts (image + video) via LLM with full script context
    2. Generate a first-frame image using image_prompt + character references
    3. Generate video using video_prompt + first-frame (or character sheets)
    """
    project_id = state["project_id"]
    current_episode_index = state.get("current_episode_index", 0)
    agent_id = STAGE_AGENT_MAP[ProductionStage.SHOTS_GENERATING]

    # Check precondition
    if not is_stage_completed(project_id, ProductionStage.ASSETS_COMPLETED.value):
        raise RuntimeError("Assets must be completed before shot video generation")

    # Get current episode
    episodes = project_repo.get_episodes(project_id)
    if current_episode_index >= len(episodes):
        return {"current_stage": ProductionStage.SHOTS_COMPLETED.value}

    ep = episodes[current_episode_index]
    episode_id = ep["episode_id"]

    update_project_stage(project_id, ProductionStage.SHOTS_GENERATING.value, "in_progress")

    shots = get_shots_by_episode(episode_id)
    agent_repo.update_agent_state(
        project_id, agent_id,
        status="working",
        current_task=f"生成第{ep['episode_number']}集镜头视频",
        completed_tasks=0,
        total_tasks=max(1, len(shots)),
    )

    add_production_event(
        project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
        "stage_started", f"开始生成第{ep['episode_number']}集镜头",
        "正在为每个分镜逐个生成提示词、首帧图片和视频...", episode_id=episode_id
    )

    project_repo.update_episode(episode_id, status="rendering", progress=70)

    # Check video mode
    video_mode = get_setting("video_generation_mode") or "manual"

    if video_mode == "manual":
        add_production_event(
            project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
            "manual_mode", "手动模式", "视频生成模式为手动，请手动触发镜头生成",
            episode_id=episode_id
        )
        project_repo.update_episode(episode_id, status="rendering", progress=72)

        human_input = interrupt({
            "type": "manual_video",
            "message": "Manual video generation mode",
            "episode_id": episode_id,
            "episode_number": ep["episode_number"],
            "shots": [
                {"shot_id": s["shot_id"], "shot_number": s["shot_number"], "description": s.get("description", "")}
                for s in shots
            ],
        })

        if human_input.get("skip"):
            agent_repo.update_agent_state(project_id, agent_id, status="idle", current_task=None)
            return {
                "current_stage": ProductionStage.SHOTS_COMPLETED.value,
                "current_episode_index": current_episode_index + 1,
            }

    # Load character assets
    character_assets = get_assets(project_id, type="character")

    # Determine series type
    proj = project_repo.get_project(project_id)
    proj_config = proj.get("config", {}) if proj else {}
    if isinstance(proj_config, str):
        proj_config = json.loads(proj_config)
    series_type = state.get("series_type") or proj_config.get("series_type", "live-action")

    # Auto mode: generate prompts, first frames, then videos
    shots_completed = 0
    image_configured = is_image_configured() or is_image_demo_mode()
    video_ok = is_video_configured()
    image_aspect_ratio = get_setting("video_aspect_ratio", "16:9")

    for idx, shot in enumerate(shots, start=1):
        shot_id = shot["shot_id"]
        description = shot.get("description", "")

        # Step 0: Generate dual prompts with full context
        add_production_event(
            project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
            "prompt_issued", f"镜头 {shot['shot_number']} 提示词生成",
            f"正在为第{ep['episode_number']}集镜头 {shot['shot_number']} 生成专用提示词",
            episode_id=episode_id, shot_id=shot_id,
        )

        prompts = await _generate_shot_prompts(shot, ep, character_assets, series_type)
        image_prompt = prompts["image_prompt"]
        video_prompt = prompts["video_prompt"]
        appearing_chars = prompts["appearing_characters"]

        # Save prompts to DB
        update_shot(shot_id, image_prompt=image_prompt, video_prompt=video_prompt)

        # Resolve character sheet paths for appearing characters
        char_sheet_paths = _get_char_sheet_paths(appearing_chars)

        first_frame_path = None

        # Step 1: Generate first-frame image using image_prompt + character references
        if image_configured:
            add_production_event(
                project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                "prompt_issued", f"镜头 {shot['shot_number']} 首帧图片",
                f"开始生成第{ep['episode_number']}集镜头 {shot['shot_number']} 首帧",
                episode_id=episode_id, shot_id=shot_id,
                payload={"prompt": image_prompt[:200], "char_refs": len(char_sheet_paths)}
            )

            try:
                frame_output = str(project_renders_dir(project_id) / f"{shot_id}_frame.png")

                await generate_image(
                    image_prompt, frame_output,
                    reference_images=char_sheet_paths if char_sheet_paths else None,
                    aspect_ratio=image_aspect_ratio,
                )

                first_frame_path = f"/renders/{project_id}/{shot_id}_frame.png"
                update_shot(shot_id, first_frame_path=first_frame_path)

                add_production_event(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    "output_captured", f"镜头 {shot['shot_number']} 首帧完成", "首帧图片已生成",
                    episode_id=episode_id, shot_id=shot_id,
                    payload={"output": first_frame_path}
                )
            except Exception as e:
                add_production_event(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    "first_frame_failed", f"镜头 {shot['shot_number']} 首帧失败", str(e),
                    episode_id=episode_id, shot_id=shot_id,
                )

        # Step 2: Generate video using video_prompt + first-frame (or character sheets)
        if video_ok:
            add_production_event(
                project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                "prompt_issued", f"镜头 {shot['shot_number']} 视频生成",
                f"开始生成第{ep['episode_number']}集镜头 {shot['shot_number']} 视频",
                episode_id=episode_id, shot_id=shot_id,
                payload={"prompt": video_prompt[:200], "has_first_frame": first_frame_path is not None}
            )

            try:
                video_output = str(project_renders_dir(project_id) / f"{shot_id}.mp4")
                video_config = get_video_config()
                add_shot_trace(
                    shot_id, project_id, "video_generation", agent_id=agent_id,
                    prompt_summary=video_prompt[:100],
                    prompt_hash=hashlib.md5(video_prompt.encode()).hexdigest(),
                    provider_name=video_config["provider"], model_name=video_config["model"],
                )

                # Video reference images: first-frame (primary), character sheets (fallback)
                video_refs = []
                if first_frame_path:
                    real_frame_path = str(RENDERS_DIR.parent / first_frame_path.lstrip("/"))
                    video_refs.append(real_frame_path)
                if char_sheet_paths and len(video_refs) < 3:
                    # Fill remaining slots with character sheets (max 3 total)
                    video_refs.extend(char_sheet_paths[:3 - len(video_refs)])

                await generate_video(
                    video_prompt, video_output,
                    reference_images=video_refs if video_refs else None,
                    duration_seconds=parse_duration_seconds(shot.get("duration")),
                    aspect_ratio=video_config.get("aspect_ratio", "16:9"),
                )

                update_shot(shot_id, status="completed", video_url=f"/renders/{project_id}/{shot_id}.mp4")
                add_shot_trace(
                    shot_id, project_id, "video_completed", agent_id=agent_id,
                    output_path=video_output, provider_name=video_config["provider"],
                    model_name=video_config["model"],
                )
                shots_completed += 1

                add_production_event(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    "output_captured", f"镜头 {shot['shot_number']} 输出", "视频已生成",
                    episode_id=episode_id, shot_id=shot_id,
                    payload={"output": f"/renders/{project_id}/{shot_id}.mp4"}
                )
                add_production_event(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    "shot_completed", f"镜头 {shot['shot_number']} 完成", "视频已生成",
                    episode_id=episode_id, shot_id=shot_id,
                    payload={
                        "image_prompt": image_prompt[:100],
                        "video_prompt": video_prompt[:100],
                        "first_frame_path": first_frame_path,
                        "video_url": f"/renders/{project_id}/{shot_id}.mp4",
                    }
                )
            except Exception as e:
                update_shot(shot_id, status="failed")
                add_shot_trace(
                    shot_id, project_id, "video_failed", agent_id=agent_id, error_reason=str(e)
                )
        else:
            update_shot(shot_id, status="failed")
            add_shot_trace(
                shot_id, project_id, "video_failed", agent_id=agent_id,
                error_reason="Video provider not configured"
            )

        # Update progress
        episode_progress = 72 + int((shots_completed / max(1, len(shots))) * 13)
        project_repo.update_episode(episode_id, status="rendering", progress=episode_progress)
        agent_repo.update_agent_state(
            project_id, agent_id, status="working",
            current_task=f"镜头视频：第{ep['episode_number']}集 / 镜头 {shot['shot_number']}",
            completed_tasks=shots_completed, total_tasks=max(1, len(shots)),
            progress=int(idx / max(1, len(shots)) * 100)
        )

    # Check if all shots completed
    if shots_completed == len(shots):
        update_project_stage(project_id, ProductionStage.SHOTS_GENERATING.value, "completed")
        update_project_stage(project_id, ProductionStage.SHOTS_COMPLETED.value, "completed")
        add_production_event(
            project_id, agent_id, ProductionStage.SHOTS_COMPLETED.value,
            "stage_completed", f"第{ep['episode_number']}集镜头完成",
            f"已生成 {shots_completed} 个镜头视频", episode_id=episode_id
        )

    agent_repo.update_agent_state(project_id, agent_id, status="idle", current_task=None)

    return {
        "current_stage": ProductionStage.SHOTS_COMPLETED.value,
    }
