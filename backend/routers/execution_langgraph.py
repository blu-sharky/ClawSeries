"""LangGraph-based execution router - replaces polling task worker.

The frontend expects JSON responses from start-production/continue, not SSE.
The graph runs as a background task, with progress updates pushed via WebSocket.
"""

import json
import asyncio
import time
from fastapi import APIRouter, HTTPException

from repositories import project_repo, agent_repo, task_repo
from repositories.production_event_repo import init_project_stages, update_project_stage, get_current_stage
from graphs.production_graph import compile_production_graph
from graphs.state import ProductionState
from checkpoint.sqlite_saver import get_checkpointer
from models import ProductionStage

router = APIRouter()

# Track running graph tasks to avoid duplicates
_running_graphs: dict[str, asyncio.Task] = {}


def _initial_state_from_project(project: dict) -> ProductionState:
    return {
        "project_id": project["project_id"],
        "title": project["title"],
        "status": "in_progress",
        "config": project.get("config", {}),
        "characters": [],
        "episodes": [],
        "current_stage": ProductionStage.SCRIPT_GENERATING.value,
        "current_episode_index": 0,
        "current_shot_index": 0,
        "events": [],
        "errors": [],
        "awaiting_input": False,
        "interrupt_data": None,
        "video_mode": "auto",
    }


def _queue_stage_task(project_id: str, stage: str) -> bool:
    if stage in (ProductionStage.SCRIPT_GENERATING.value, ProductionStage.REQUIREMENTS_CONFIRMED.value):
        task_repo.create_task(f"task_{project_id}_script", project_id, "project_script")
        return True
    if stage == ProductionStage.FORMAT_GENERATING.value:
        task_repo.create_task(f"task_{project_id}_format", project_id, "project_format")
        return True
    if stage == ProductionStage.ASSETS_GENERATING.value:
        task_repo.create_task(f"task_{project_id}_assets", project_id, "project_assets")
        return True
    if stage == ProductionStage.SHOTS_GENERATING.value:
        for episode in project_repo.get_episodes(project_id):
            if episode["status"] != "completed":
                task_repo.create_task(
                    f"task_{episode['episode_id']}_shots", project_id,
                    "episode_shot_video", episode_id=episode["episode_id"]
                )
                return True
    return False


async def _run_production_graph(project_id: str, initial_state: ProductionState | None = None):
    """Run the production graph as a background task.

    All progress updates are pushed via WebSocket from within the nodes.
    """
    checkpointer = await get_checkpointer()
    graph = compile_production_graph(checkpointer)
    config = {"configurable": {"thread_id": project_id}}

    try:
        agent_repo.add_agent_log(project_id, "agent_director", "info", "LangGraph graph execution started")

        if initial_state is not None:
            async for event in graph.astream(initial_state, config=config, stream_mode="values"):
                stage = event.get("current_stage", "")
                errs = event.get("errors", [])
                agent_repo.add_agent_log(
                    project_id, "agent_director", "info",
                    f"Graph step completed: stage={stage}, errors={len(errs)}"
                )
        else:
            async for event in graph.astream(None, config=config, stream_mode="values"):
                stage = event.get("current_stage", "")
                errs = event.get("errors", [])
                agent_repo.add_agent_log(
                    project_id, "agent_director", "info",
                    f"Graph step completed: stage={stage}, errors={len(errs)}"
                )

        agent_repo.add_agent_log(project_id, "agent_director", "info", "LangGraph graph execution completed")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        agent_repo.add_agent_log(
            project_id, "agent_director", "error",
            f"Graph execution failed: {type(e).__name__}: {e}\n{tb[-500:]}"
        )
        project_repo.update_project(project_id, status="failed")
    finally:
        _running_graphs.pop(project_id, None)


@router.post("/projects/{project_id}/start-production")
async def start_production_langgraph(project_id: str):
    """Start production using LangGraph StateGraph.

    Returns JSON immediately, graph runs in background.
    """
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if project["status"] not in ("pending", "paused"):
        raise HTTPException(status_code=400, detail=f"项目状态不允许启动: {project['status']}")

    # Don't start if already running
    if project_id in _running_graphs and not _running_graphs[project_id].done():
        return {
            "status": "already_running",
            "project_id": project_id,
            "message": "制片流程正在执行中",
            "current_stage": ProductionStage.SCRIPT_GENERATING.value,
        }

    # Initialize stage tracking
    init_project_stages(project_id)
    update_project_stage(project_id, ProductionStage.REQUIREMENTS_CONFIRMED.value, "completed")

    project_repo.update_project(project_id, status="in_progress")
    agent_repo.add_agent_log(project_id, "agent_director", "info", "制片流程已启动 (LangGraph)")

    initial_state = _initial_state_from_project(project)

    # Start graph execution as background task
    task = asyncio.create_task(_run_production_graph(project_id, initial_state))
    _running_graphs[project_id] = task

    return {
        "status": "started",
        "project_id": project_id,
        "message": "制片流程已启动，正在生成剧本...",
        "current_stage": ProductionStage.SCRIPT_GENERATING.value,
    }


@router.get("/projects/{project_id}/stages")
async def get_project_stage_status(project_id: str):
    """Get the current stage status for a project."""
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    from repositories.production_event_repo import get_project_stages, get_current_stage

    stages = get_project_stages(project_id)
    current = get_current_stage(project_id)

    return {
        "project_id": project_id,
        "stages": stages,
        "current_stage": current,
    }


@router.post("/projects/{project_id}/continue")
async def continue_production(project_id: str):
    """Continue production from current state (for paused/resumable projects)."""
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if project["status"] not in ("paused", "in_progress", "pending"):
        raise HTTPException(status_code=400, detail=f"项目状态不允许继续: {project['status']}")

    if project_id in _running_graphs and not _running_graphs[project_id].done():
        current = get_current_stage(project_id)
        return {
            "status": "resumed",
            "message": "制片流程继续执行中",
            "current_stage": current["stage"] if current else None,
        }

    init_project_stages(project_id)
    task_repo.reset_running_tasks(project_id)
    current = get_current_stage(project_id)
    stage = current["stage"] if current else ProductionStage.SCRIPT_GENERATING.value

    project_repo.update_project(project_id, status="in_progress")
    agent_repo.add_agent_log(project_id, "agent_director", "info", f"恢复制片流程: {stage}")

    queued_task = _queue_stage_task(project_id, stage)
    if queued_task:
        return {
            "status": "resumed",
            "message": "制片流程已继续",
            "current_stage": stage,
        }

    if stage in (ProductionStage.SCRIPT_GENERATING.value, ProductionStage.REQUIREMENTS_CONFIRMED.value):
        initial_state = _initial_state_from_project(project)
        task = asyncio.create_task(_run_production_graph(project_id, initial_state))
    else:
        task = asyncio.create_task(_run_production_graph(project_id))

    _running_graphs[project_id] = task

    return {
        "status": "resumed",
        "message": "制片流程已继续",
        "current_stage": stage,
    }


@router.post("/projects/{project_id}/generate-assets")
async def generate_project_assets(project_id: str):
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    task_repo.create_task(f"task_{project_id}_assets", project_id, "project_assets")
    project_repo.update_project(project_id, status="in_progress")
    return {"status": "started", "message": "资产生成任务已加入队列"}


@router.post("/projects/{project_id}/episodes/{episode_id}/generate-shots")
async def generate_episode_shots(project_id: str, episode_id: str):
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    episode = project_repo.get_episode(episode_id)
    if not episode or episode["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="剧集不存在")

    task_repo.create_task(
        f"task_{episode_id}_shots_{int(time.time())}", project_id, "episode_shot_video", episode_id=episode_id
    )
    project_repo.update_episode(episode_id, status="rendering", progress=max(episode.get("progress") or 0, 70))
    project_repo.update_project(project_id, status="in_progress")
    return {"status": "started", "message": f"第{episode['episode_number']}集镜头生成任务已加入队列"}


@router.post("/projects/{project_id}/episodes/{episode_id}/compose")
async def compose_episode(project_id: str, episode_id: str):
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    episode = project_repo.get_episode(episode_id)
    if not episode or episode["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="剧集不存在")

    task_repo.create_task(
        f"task_{episode_id}_compose_{int(time.time())}", project_id, "episode_compose", episode_id=episode_id
    )
    project_repo.update_episode(episode_id, status="editing", progress=max(episode.get("progress") or 0, 85))
    project_repo.update_project(project_id, status="in_progress")
    return {"status": "started", "message": f"第{episode['episode_number']}集合成任务已加入队列"}


@router.get("/projects/{project_id}/state")
async def get_production_state(project_id: str):
    """Get the current LangGraph state for a project."""
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    checkpointer = await get_checkpointer()
    graph = compile_production_graph(checkpointer)

    config = {"configurable": {"thread_id": project_id}}
    state = await graph.aget_state(config)

    return {
        "project_id": project_id,
        "current_stage": state.values.get("current_stage"),
        "status": state.values.get("status"),
        "events": state.values.get("events", []),
        "errors": state.values.get("errors", []),
        "awaiting_input": state.values.get("awaiting_input", False),
        "interrupt_data": state.values.get("interrupt_data"),
    }


@router.post("/projects/{project_id}/resume")
async def resume_production(project_id: str, decision: dict | None = None):
    """Resume production from an interrupt (human-in-the-loop)."""
    project = project_repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    checkpointer = await get_checkpointer()
    graph = compile_production_graph(checkpointer)

    config = {"configurable": {"thread_id": project_id}}

    # Resume graph with decision as input
    project_repo.update_project(project_id, status="in_progress")

    task = asyncio.create_task(_run_production_graph(project_id))
    _running_graphs[project_id] = task

    return {"status": "resumed", "message": "制片流程已恢复"}
