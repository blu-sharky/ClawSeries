"""
Dubbing router — REST API for video dubbing.
"""

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List

from models import DubbingRequest, DubbingTaskInfo, DUBBING_LANGUAGES, BatchDubbingRequest, BatchDubbingResponse, CompletedProjectForDubbing, EpisodeForDubbing
from services import dubbing_service
from config import DUBBING_DIR

router = APIRouter()


class StartDubbingResponse(BaseModel):
    task_id: str
    status: str


class DubbingTaskListResponse(BaseModel):
    tasks: List[DubbingTaskInfo]


class DubbingLanguagesResponse(BaseModel):
    languages: dict


@router.get("/dubbing/languages", response_model=DubbingLanguagesResponse)
async def get_supported_languages():
    """Return supported target languages for dubbing."""
    return {"languages": DUBBING_LANGUAGES}


@router.get("/dubbing/completed-projects")
async def get_completed_projects():
    """Return completed projects with their episodes for dubbing selection."""
    projects = dubbing_service.get_completed_projects_for_dubbing()
    return {"projects": projects}


@router.post("/dubbing/start", response_model=StartDubbingResponse)
async def start_dubbing(req: DubbingRequest):
    """Start a dubbing task.

    Args:
        req.video_path: Path to source video file (absolute path or relative to project root)
        req.target_language: Target language code (e.g., "en", "ja")
        req.source_language: Optional source language code (auto-detect if None)

    Returns:
        task_id and initial status
    """
    import os
    from pathlib import Path

    video_path = req.video_path
    # Handle relative paths — resolve from project root
    if not os.path.isabs(video_path):
        # Check if it's in the test-video.mp4 location
        project_root = Path(__file__).parent.parent.parent
        candidate = project_root / video_path
        if candidate.exists():
            video_path = str(candidate)
        else:
            # Check data/outputs directory
            candidate = Path(DUBBING_DIR).parent / "outputs" / video_path
            if candidate.exists():
                video_path = str(candidate)

    if not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail=f"Video file not found: {video_path}")

    if req.target_language not in DUBBING_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported target language: {req.target_language}. Supported: {list(DUBBING_LANGUAGES.keys())}"
        )

    task_id = dubbing_service.start_dubbing(
        source_video=video_path,
        target_language=req.target_language,
        source_language=req.source_language,
    )

    return {"task_id": task_id, "status": "pending"}


@router.get("/dubbing/{task_id}", response_model=DubbingTaskInfo)
async def get_dubbing_status(task_id: str):
    """Get status of a dubbing task."""
    task = dubbing_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return DubbingTaskInfo(
        task_id=task["task_id"],
        source_video_path=task["source_video_path"],
        target_language=task["target_language"],
        source_language=task.get("source_language"),
        status=task["status"],
        progress=task.get("progress", 0),
        current_step=task.get("current_step"),
        output_video_path=task.get("output_video_path"),
        error_message=task.get("error_message"),
        created_at=task.get("created_at"),
        completed_at=task.get("completed_at"),
    )


@router.get("/dubbing", response_model=DubbingTaskListResponse)
async def list_dubbing_tasks():
    """List recent dubbing tasks."""
    tasks = dubbing_service.list_tasks()
    return {
        "tasks": [
            DubbingTaskInfo(
                task_id=t["task_id"],
                source_video_path=t["source_video_path"],
                target_language=t["target_language"],
                source_language=t.get("source_language"),
                status=t["status"],
                progress=t.get("progress", 0),
                current_step=t.get("current_step"),
                output_video_path=t.get("output_video_path"),
                error_message=t.get("error_message"),
                created_at=t.get("created_at"),
                completed_at=t.get("completed_at"),
            )
            for t in tasks
        ]
    }


@router.post("/dubbing/upload")
async def upload_video_for_dubbing(file: UploadFile = File(...)):
    """Upload a video file for dubbing.

    Returns the path to the uploaded file.
    """
    import os
    import uuid
    from pathlib import Path

    # Generate unique filename
    ext = os.path.splitext(file.filename or "video.mp4")[1] or ".mp4"
    upload_name = f"upload_{uuid.uuid4().hex[:8]}{ext}"
    upload_path = Path(DUBBING_DIR) / "uploads" / upload_name
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    # Save file
    content = await file.read()
    with open(upload_path, "wb") as f:
        f.write(content)

    return {"path": str(upload_path), "filename": upload_name}


@router.get("/dubbing/{task_id}/download")
async def download_dubbed_video(task_id: str):
    """Download the dubbed video file."""
    task = dubbing_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    output_path = task.get("output_video_path")
    if not output_path:
        raise HTTPException(status_code=400, detail="Task not completed or no output available")

    import os
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"dubbed_{task['target_language']}_{task_id}.mp4",
    )


@router.post("/dubbing/start-batch")
async def start_batch_dubbing(req: BatchDubbingRequest):
    """Start dubbing for selected episodes of a completed project.

    If episode_ids is not provided, dubs all episodes.
    """
    if req.target_language not in DUBBING_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported target language: {req.target_language}. Supported: {list(DUBBING_LANGUAGES.keys())}"
        )

    tasks = dubbing_service.start_batch_dubbing(
        project_id=req.project_id,
        target_language=req.target_language,
        episode_ids=req.episode_ids,
        source_language=req.source_language,
    )

    if not tasks:
        raise HTTPException(status_code=400, detail="No dubbing tasks created — episodes may have no video")

    return {"tasks": tasks, "total": len(tasks)}
