"""
Execution control router - linear stage-based production control.

All endpoints enforce the linear pipeline:
  requirements_confirmed → script → format → assets → shots → compose

You cannot skip stages. Each endpoint validates preconditions.
"""

from fastapi import APIRouter, HTTPException
from repositories import project_repo, task_repo, agent_repo
from repositories.production_event_repo import (
    init_project_stages,
    update_project_stage,
    is_stage_completed,
    get_project_stages,
    get_current_stage,
)
from routers.websocket import send_progress_update, send_agent_update
from models import ProductionStage, STAGE_PRECONDITIONS

router = APIRouter()


@router.post("/projects/{project_id}/start-production")
async def start_project_production(project_id: str):
    """
    Start the linear production pipeline for a project.
    This is the single entry point that queues the first stage task.
    """
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if project["status"] not in ("pending", "paused"):
        raise HTTPException(status_code=400, detail=f"项目状态不允许启动: {project['status']}")

    # Initialize stage tracking
    init_project_stages(project_id)
    update_project_stage(project_id, ProductionStage.REQUIREMENTS_CONFIRMED.value, "completed")

    # Queue the first stage
    task_repo.create_task(f"task_{project_id}_script", project_id, "project_script")

    project_repo.update_project(project_id, status="in_progress")
    agent_repo.add_agent_log(project_id, "agent_director", "info", "制片流程已启动")

    return {
        "status": "started",
        "project_id": project_id,
        "message": "制片流程已启动，正在生成剧本...",
        "current_stage": ProductionStage.SCRIPT_GENERATING.value,
    }


@router.post("/projects/{project_id}/continue")
async def continue_project(project_id: str):
    """Continue production from the current stage."""
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if project["status"] not in ("paused", "in_progress", "pending"):
        raise HTTPException(status_code=400, detail=f"项目状态不允许继续: {project['status']}")

    current = get_current_stage(project_id)
    if not current:
        # No stages initialized - need to start fresh
        # Reset status to pending so start_project_production can proceed
        if project["status"] == "in_progress":
            project_repo.update_project(project_id, status="pending")
        return await start_project_production(project_id)

    stage = current["stage"]
    status = current["status"]

    if status == "in_progress":
        project_repo.update_project(project_id, status="in_progress")
        return {
            "status": "resumed",
            "message": "制片流程继续执行中",
            "current_stage": stage,
        }

    stage_to_task = {
        ProductionStage.SCRIPT_GENERATING.value: ("project_script", None),
        ProductionStage.FORMAT_GENERATING.value: ("project_format", None),
        ProductionStage.ASSETS_GENERATING.value: ("project_assets", None),
    }

    if stage in stage_to_task:
        task_type, episode_id = stage_to_task[stage]
        task_repo.create_task(
            f"task_{project_id}_{task_type}",
            project_id,
            task_type,
            episode_id=episode_id,
        )
    elif stage == ProductionStage.SHOTS_GENERATING.value:
        episodes = project_repo.get_episodes(project_id)
        for episode in episodes:
            if episode["status"] == "completed":
                continue
            task_repo.create_task(
                f"task_{episode['episode_id']}_shots",
                project_id,
                "episode_shot_video",
                episode_id=episode["episode_id"],
            )
            break
    project_repo.update_project(project_id, status="in_progress")
    return {
        "status": "resumed",
        "message": "制片流程已继续",
        "current_stage": stage,
    }


@router.post("/projects/{project_id}/generate-script")
async def generate_project_script(project_id: str):
    """
    Generate complete scripts for all episodes.
    Precondition: requirements_confirmed
    """
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # Check precondition
    if not is_stage_completed(project_id, ProductionStage.REQUIREMENTS_CONFIRMED.value):
        raise HTTPException(status_code=400, detail="需求尚未确认，无法生成剧本")

    # Check if already completed or in progress
    if is_stage_completed(project_id, ProductionStage.SCRIPT_COMPLETED.value):
        return {"status": "already_completed", "message": "剧本已生成完成"}

    # Queue the task
    task_repo.create_task(f"task_{project_id}_script", project_id, "project_script")

    return {"status": "started", "message": "剧本生成任务已加入队列"}


@router.post("/projects/{project_id}/format-script")
async def format_project_script(project_id: str):
    """
    Format scripts into structured storyboards.
    Precondition: script_completed
    """
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not is_stage_completed(project_id, ProductionStage.SCRIPT_COMPLETED.value):
        raise HTTPException(status_code=400, detail="剧本尚未完成，无法格式化分镜")

    if is_stage_completed(project_id, ProductionStage.FORMAT_COMPLETED.value):
        return {"status": "already_completed", "message": "分镜已格式化完成"}

    task_repo.create_task(f"task_{project_id}_format", project_id, "project_format")

    return {"status": "started", "message": "分镜格式化任务已加入队列"}


@router.post("/projects/{project_id}/generate-assets")
async def generate_project_assets(project_id: str):
    """
    Generate character/scene/prop assets.
    Precondition: format_completed
    """
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not is_stage_completed(project_id, ProductionStage.FORMAT_COMPLETED.value):
        raise HTTPException(status_code=400, detail="分镜尚未完成，无法生成资产")

    if is_stage_completed(project_id, ProductionStage.ASSETS_COMPLETED.value):
        return {"status": "already_completed", "message": "资产已生成完成"}

    task_repo.create_task(f"task_{project_id}_assets", project_id, "project_assets")

    return {"status": "started", "message": "资产生成任务已加入队列"}


@router.post("/projects/{project_id}/generate-shots")
async def generate_project_shots(project_id: str):
    """
    Generate videos for all shots in all episodes.
    Precondition: assets_completed
    """
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not is_stage_completed(project_id, ProductionStage.ASSETS_COMPLETED.value):
        raise HTTPException(status_code=400, detail="资产尚未完成，无法生成镜头视频")

    # Queue shot video tasks for each episode
    episodes = project_repo.get_episodes(project_id)
    queued = 0
    for ep in episodes:
        if ep["status"] != "completed":
            task_repo.create_task(
                f"task_{ep['episode_id']}_shots",
                project_id, "episode_shot_video",
                episode_id=ep["episode_id"]
            )
            queued += 1

    return {"status": "started", "message": f"已为 {queued} 集创建镜头生成任务"}


@router.post("/projects/{project_id}/episodes/{episode_id}/generate-shots")
async def generate_episode_shots(project_id: str, episode_id: str):
    """
    Generate videos for all shots in a specific episode.
    Precondition: assets_completed
    """
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    episode = project_repo.get_episode(episode_id)
    if not episode or episode["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="剧集不存在")

    if not is_stage_completed(project_id, ProductionStage.ASSETS_COMPLETED.value):
        raise HTTPException(status_code=400, detail="资产尚未完成，无法生成镜头视频")

    if episode["status"] == "completed":
        return {"status": "already_completed", "message": "剧集已完成"}

    task_repo.create_task(
        f"task_{episode_id}_shots",
        project_id, "episode_shot_video",
        episode_id=episode_id
    )

    return {"status": "started", "message": f"第{episode['episode_number']}集镜头生成任务已加入队列"}


@router.post("/projects/{project_id}/compose")
async def compose_project(project_id: str):
    """
    Compose final output from all completed episodes.
    Precondition: all episodes completed
    """
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    episodes = project_repo.get_episodes(project_id)
    completed = [ep for ep in episodes if ep["status"] == "completed"]

    if not completed:
        raise HTTPException(status_code=400, detail="没有已完成的剧集可合成")

    task_repo.create_task(f"task_{project_id}_compose", project_id, "project_compose")

    return {"status": "started", "message": f"项目合成任务已加入队列，共 {len(completed)} 集"}


@router.get("/projects/{project_id}/stages")
async def get_project_stage_status(project_id: str):
    """Get the current stage status for a project."""
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    stages = get_project_stages(project_id)
    current = get_current_stage(project_id)

    return {
        "project_id": project_id,
        "stages": stages,
        "current_stage": current,
    }


# === Legacy endpoints (deprecated, redirect to linear flow) ===

@router.post("/projects/{project_id}/run")
async def run_project_legacy(project_id: str):
    """Deprecated: Use /start-production instead."""
    return await start_project_production(project_id)


@router.post("/projects/{project_id}/episodes/{episode_id}/run")
async def run_episode_legacy(project_id: str, episode_id: str):
    """Deprecated: Episodes are now processed as part of the linear pipeline."""
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    episode = project_repo.get_episode(episode_id)
    if not episode or episode["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="剧集不存在")

    # Create a legacy episode_run task that will be migrated to linear chain
    task_repo.create_task(
        f"task_{episode_id}_run_legacy",
        project_id, "episode_run",
        episode_id=episode_id,
        input_data={"episode_number": episode["episode_number"], "title": episode["title"]},
    )

    return {"status": "started", "message": "剧集任务已加入队列（将自动转换为线性流程）"}


@router.post("/projects/{project_id}/episodes/{episode_id}/shots/{shot_id}/run")
async def run_shot_legacy(project_id: str, episode_id: str, shot_id: str):
    """Deprecated: Individual shot execution breaks linear flow. Use episode-level generation."""
    raise HTTPException(
        status_code=400,
        detail="单个镜头执行已禁用。请使用 POST /projects/{project_id}/episodes/{episode_id}/generate-shots"
    )
