"""
Episode routes.
"""

from fastapi import APIRouter, HTTPException
from services.episode_service import EpisodeService

router = APIRouter()
episode_service = EpisodeService()


@router.get("/projects/{project_id}/episodes/{episode_id}")
async def get_episode(project_id: str, episode_id: str):
    result = episode_service.get_episode(project_id, episode_id)
    if not result:
        raise HTTPException(status_code=404, detail="剧集不存在")
    return result


@router.get("/projects/{project_id}/episodes/{episode_id}/video")
async def get_episode_video(project_id: str, episode_id: str):
    video_url = episode_service.get_video_path(project_id, episode_id)
    if not video_url:
        raise HTTPException(status_code=404, detail="视频不存在或尚未生成")
    return {"video_url": video_url}


@router.get("/projects/{project_id}/episodes/{episode_id}/traces")
async def get_episode_traces(project_id: str, episode_id: str):
    """Get detailed execution traces for an episode."""
    traces = episode_service.get_episode_traces(project_id, episode_id)
    return {"episode_id": episode_id, "traces": traces}
