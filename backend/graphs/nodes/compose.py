"""Compose nodes - Stages 5 and 6 of production pipeline."""

from graphs.state import ProductionState
from repositories import project_repo, agent_repo
from repositories.shot_repo import get_shots_by_episode
from repositories.production_event_repo import (
    add_production_event,
    update_project_stage,
)
from routers.websocket import send_episode_completed, send_project_completed
from integrations.ffmpeg import is_ffmpeg_available, concatenate_videos
from config import RENDERS_DIR, OUTPUTS_DIR
from models import ProductionStage, STAGE_AGENT_MAP


async def episode_compose_node(state: ProductionState) -> dict:
    """Compose a completed episode from generated shots.

    This is Stage 5 of the production pipeline.
    """
    project_id = state["project_id"]
    current_episode_index = state.get("current_episode_index", 0)
    agent_id = STAGE_AGENT_MAP[ProductionStage.EPISODE_COMPOSING]

    # Get current episode
    episodes = project_repo.get_episodes(project_id)
    if current_episode_index >= len(episodes):
        return {"current_stage": ProductionStage.EPISODE_COMPLETED.value}

    ep = episodes[current_episode_index]
    episode_id = ep["episode_id"]

    update_project_stage(project_id, ProductionStage.EPISODE_COMPOSING.value, "in_progress")

    total_episodes = len(episodes)
    completed_before = project_repo.get_completed_episode_count(project_id)

    agent_repo.update_agent_state(
        project_id, agent_id,
        status="working",
        current_task=f"合成第{ep['episode_number']}集",
        completed_tasks=completed_before,
        total_tasks=max(1, total_episodes),
    )

    add_production_event(
        project_id, agent_id, ProductionStage.EPISODE_COMPOSING.value,
        "stage_started", f"开始合成第{ep['episode_number']}集",
        "正在拼接镜头、添加字幕...", episode_id=episode_id
    )

    project_repo.update_episode(episode_id, status="editing", progress=85)

    shots = get_shots_by_episode(episode_id)
    video_paths = [s["video_url"] for s in shots if s.get("video_url")]

    if video_paths and is_ffmpeg_available():
        try:
            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            output_path = str(OUTPUTS_DIR / f"{episode_id}.mp4")
            actual_paths = [str(RENDERS_DIR / p.replace("/renders/", "")) for p in video_paths]
            concatenate_videos(actual_paths, output_path)
            project_repo.update_episode(
                episode_id, video_url=f"/videos/{episode_id}.mp4", status="completed", progress=100
            )
            add_production_event(
                project_id, agent_id, ProductionStage.EPISODE_COMPOSING.value,
                "episode_completed", f"第{ep['episode_number']}集完成", "已合成成片",
                episode_id=episode_id, payload={"video_url": f"/videos/{episode_id}.mp4"}
            )
            await send_episode_completed(
                project_id, episode_id, ep["episode_number"], ep["title"], f"/videos/{episode_id}.mp4"
            )
        except Exception as e:
            project_repo.update_episode(episode_id, status="failed")
            add_production_event(
                project_id, agent_id, ProductionStage.EPISODE_COMPOSING.value,
                "episode_failed", f"第{ep['episode_number']}集合成失败", str(e), episode_id=episode_id
            )
    else:
        project_repo.update_episode(episode_id, status="completed", progress=100)
        add_production_event(
            project_id, agent_id, ProductionStage.EPISODE_COMPOSING.value,
            "episode_completed", f"第{ep['episode_number']}集完成", "已完成（无视频合成）",
            episode_id=episode_id
        )

    update_project_stage(project_id, ProductionStage.EPISODE_COMPOSING.value, "completed")
    update_project_stage(project_id, ProductionStage.EPISODE_COMPLETED.value, "completed")

    completed_now = project_repo.get_completed_episode_count(project_id)
    agent_repo.update_agent_state(
        project_id, agent_id, status="idle", current_task=None,
        completed_tasks=completed_now, total_tasks=max(1, total_episodes)
    )

    return {
        "current_stage": ProductionStage.EPISODE_COMPLETED.value,
    }


async def project_compose_node(state: ProductionState) -> dict:
    """Compose final output from all completed episodes.

    This is Stage 6 of the production pipeline.
    """
    project_id = state["project_id"]
    agent_id = STAGE_AGENT_MAP[ProductionStage.PROJECT_COMPOSING]

    update_project_stage(project_id, ProductionStage.PROJECT_COMPOSING.value, "in_progress")
    agent_repo.update_agent_state(project_id, agent_id, status="working", current_task="合成成片")

    add_production_event(
        project_id, agent_id, ProductionStage.PROJECT_COMPOSING.value,
        "stage_started", "开始合成项目", "正在拼接所有剧集..."
    )

    episodes = project_repo.get_episodes(project_id)
    completed_eps = [ep for ep in episodes if ep["status"] == "completed"]

    if not completed_eps:
        return {
            "status": "failed",
            "errors": [{"message": "No completed episodes"}],
        }

    if is_ffmpeg_available() and len(completed_eps) > 1:
        try:
            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            output_path = str(OUTPUTS_DIR / f"{project_id}_final.mp4")
            video_paths = [ep["video_url"] for ep in completed_eps if ep.get("video_url")]
            if video_paths:
                actual_paths = [str(OUTPUTS_DIR / p.replace("/videos/", "")) for p in video_paths]
                concatenate_videos(actual_paths, output_path)
                add_production_event(
                    project_id, agent_id, ProductionStage.PROJECT_COMPOSING.value,
                    "project_video_created", "项目视频已生成", output_path
                )
        except Exception as e:
            add_production_event(
                project_id, agent_id, ProductionStage.PROJECT_COMPOSING.value,
                "project_video_failed", "项目视频合成失败", str(e)
            )

    # Mark project completed
    project_repo.update_project(project_id, status="completed", progress=100)
    update_project_stage(project_id, ProductionStage.PROJECT_COMPOSING.value, "completed")
    update_project_stage(project_id, ProductionStage.PROJECT_COMPLETED.value, "completed")

    add_production_event(
        project_id, agent_id, ProductionStage.PROJECT_COMPLETED.value,
        "project_completed", "项目完成",
        f"《{project_repo.get_project(project_id)['title']}》已全部完成，共 {len(completed_eps)} 集"
    )

    # Reset all agent states
    states = agent_repo.get_agent_states(project_id)
    for s in states:
        agent_repo.update_agent_state(project_id, s["agent_id"], status="idle", current_task=None)

    await send_project_completed(project_id, project_repo.get_project(project_id)["title"], len(completed_eps))

    return {
        "status": "completed",
        "current_stage": ProductionStage.PROJECT_COMPLETED.value,
    }
