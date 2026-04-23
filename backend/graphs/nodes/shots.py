"""Shot video generation node - Stage 4 of production pipeline."""

import hashlib

from langgraph.types import interrupt

from graphs.state import ProductionState
from repositories import project_repo, agent_repo
from repositories.shot_repo import get_shots_by_episode, update_shot, add_shot_trace
from repositories.production_event_repo import (
    add_production_event,
    update_project_stage,
    is_stage_completed,
)
from repositories.settings_repo import get_setting
from routers.websocket import send_agent_monitor
from integrations.video import is_video_configured, generate_video, get_video_config
from config import RENDERS_DIR
from models import ProductionStage, STAGE_AGENT_MAP


async def shots_node(state: ProductionState) -> dict:
    """Generate videos for all shots in an episode.

    This is Stage 4 of the production pipeline.
    Supports human-in-the-loop via interrupt() for manual video mode.
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
        "正在为每个分镜逐个生成视频...", episode_id=episode_id
    )

    project_repo.update_episode(episode_id, status="rendering", progress=70)

    # Check video mode
    video_mode = get_setting("video_generation_mode") or "manual"

    if video_mode == "manual":
        # Human-in-the-loop: interrupt for manual approval
        add_production_event(
            project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
            "manual_mode", "手动模式", "视频生成模式为手动，请手动触发镜头生成",
            episode_id=episode_id
        )
        project_repo.update_episode(episode_id, status="rendering", progress=72)

        # Interrupt and wait for human decision
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

        # Resume with human decision
        if human_input.get("skip"):
            agent_repo.update_agent_state(project_id, agent_id, status="idle", current_task=None)
            return {
                "current_stage": ProductionStage.SHOTS_COMPLETED.value,
                "current_episode_index": current_episode_index + 1,
            }

    # Auto mode: generate videos
    shots_completed = 0
    for idx, shot in enumerate(shots, start=1):
        shot_id = shot["shot_id"]
        description = shot.get("description", "")

        add_production_event(
            project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
            "prompt_issued", f"镜头 {shot['shot_number']} 视频提示词",
            f"开始生成第{ep['episode_number']}集镜头 {shot['shot_number']} 视频",
            episode_id=episode_id, shot_id=shot_id,
            payload={"prompt": description[:100]}
        )

        try:
            if is_video_configured():
                RENDERS_DIR.mkdir(parents=True, exist_ok=True)
                output_path = str(RENDERS_DIR / f"{shot_id}.mp4")
                video_config = get_video_config()
                add_shot_trace(
                    shot_id, project_id, "video_generation", agent_id=agent_id,
                    prompt_summary=description[:100],
                    prompt_hash=hashlib.md5(description.encode()).hexdigest(),
                    provider_name=video_config["provider"], model_name=video_config["model"],
                )

                await generate_video(description, output_path, duration_seconds=3, aspect_ratio="16:9")

                update_shot(shot_id, status="completed", video_url=f"/renders/{shot_id}.mp4")
                add_shot_trace(
                    shot_id, project_id, "video_completed", agent_id=agent_id,
                    output_path=output_path, provider_name=video_config["provider"],
                    model_name=video_config["model"],
                )
                shots_completed += 1

                add_production_event(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    "output_captured", f"镜头 {shot['shot_number']} 输出", "视频已生成",
                    episode_id=episode_id, shot_id=shot_id,
                    payload={"output": f"/renders/{shot_id}.mp4"}
                )
                add_production_event(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    "shot_completed", f"镜头 {shot['shot_number']} 完成", "视频已生成",
                    episode_id=episode_id, shot_id=shot_id
                )
            else:
                update_shot(shot_id, status="failed")
                add_shot_trace(
                    shot_id, project_id, "video_failed", agent_id=agent_id,
                    error_reason="Video provider not configured"
                )
        except Exception as e:
            update_shot(shot_id, status="failed")
            add_shot_trace(
                shot_id, project_id, "video_failed", agent_id=agent_id, error_reason=str(e)
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
        "current_episode_index": current_episode_index + 1,
    }
