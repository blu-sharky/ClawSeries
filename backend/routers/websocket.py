"""
WebSocket real-time communication.
Broadcasts real task/agent/episode state changes.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

active_connections: Dict[str, Set[WebSocket]] = {}


async def broadcast_to_project(project_id: str, message: dict):
    if project_id in active_connections:
        dead = set()
        for ws in active_connections[project_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        active_connections[project_id] -= dead


async def send_progress_update(project_id: str, overall_progress: int,
                                episode_id: str = None, episode_progress: int = None):
    data = {"project_id": project_id, "overall_progress": overall_progress}
    if episode_id:
        data["episode_progress"] = {"episode_id": episode_id, "progress": episode_progress}
    await broadcast_to_project(project_id, {"type": "progress_update", "data": data})


async def send_agent_update(project_id: str, agent_id: str, status: str,
                             current_task: str = None, progress: int = None):
    data = {"agent_id": agent_id, "status": status}
    if current_task:
        data["current_task"] = current_task
    if progress is not None:
        data["progress"] = progress
    await broadcast_to_project(project_id, {"type": "agent_update", "data": data})
async def send_stage_update(project_id: str, stage: str, status: str, title: str | None = None):
    data = {"stage": stage, "status": status}
    if title:
        data["title"] = title
    await broadcast_to_project(project_id, {"type": "stage_update", "data": data})


async def send_agent_monitor(
    project_id: str,
    agent_id: str,
    stage: str | None = None,
    prompt: str | None = None,
    output_chunk: str | None = None,
    output_text: str | None = None,
    current_task: str | None = None,
    episode_id: str | None = None,
    shot_id: str | None = None,
    reset_output: bool = False,
    final: bool = False,
    progress: int | None = None,
    meta: dict | None = None,
    status: str | None = None,
    title: str | None = None,
    message: str | None = None,
    event_type: str | None = None,
):
    data = {"agent_id": agent_id}
    if stage is not None:
        data["stage"] = stage
    if prompt is not None:
        data["prompt"] = prompt
    if output_chunk is not None:
        data["output_chunk"] = output_chunk
    if output_text is not None:
        data["output_text"] = output_text
    if current_task is not None:
        data["current_task"] = current_task
    if episode_id is not None:
        data["episode_id"] = episode_id
    if shot_id is not None:
        data["shot_id"] = shot_id
    if progress is not None:
        data["progress"] = progress
    if meta is not None:
        data["meta"] = meta
    if status is not None:
        data["status"] = status
    if title is not None:
        data["title"] = title
    if message is not None:
        data["message"] = message
    if event_type is not None:
        data["event_type"] = event_type
    if reset_output:
        data["reset_output"] = True
    if final:
        data["final"] = True
    await broadcast_to_project(project_id, {"type": "agent_monitor", "data": data})


async def send_episode_completed(project_id: str, episode_id: str,
                                  episode_number: int, title: str, video_url: str):
    await broadcast_to_project(project_id, {
        "type": "episode_completed",
        "data": {
            "episode_id": episode_id,
            "episode_number": episode_number,
            "title": title,
            "video_url": video_url,
        },
    })


async def send_project_completed(project_id: str, title: str, total_episodes: int):
    await broadcast_to_project(project_id, {
        "type": "project_completed",
        "data": {
            "project_id": project_id,
            "title": title,
            "total_episodes": total_episodes,
            "completed_at": datetime.utcnow().isoformat() + "Z",
        },
    })


async def send_trace_update(project_id: str, shot_id: str, message: str):
    """Notify that new trace data is available for a shot."""
    await broadcast_to_project(project_id, {
        "type": "trace_update",
        "data": {"shot_id": shot_id, "message": message},
    })


@router.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    await websocket.accept()

    if project_id not in active_connections:
        active_connections[project_id] = set()
    active_connections[project_id].add(websocket)

    try:
        # Send current project state on connect
        from repositories import project_repo, agent_repo
        project = project_repo.get_project(project_id)
        if project:
            await websocket.send_json({
                "type": "progress_update",
                "data": {
                    "project_id": project_id,
                    "overall_progress": project["progress"],
                },
            })

        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        if project_id in active_connections:
            active_connections[project_id].discard(websocket)
            if not active_connections[project_id]:
                del active_connections[project_id]
