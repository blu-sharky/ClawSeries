"""
Project routes with stage info.
"""

from fastapi import APIRouter, HTTPException
from services.project_service import ProjectService

router = APIRouter()
project_service = ProjectService()


@router.get("/projects")
async def get_projects():
    return project_service.get_projects()


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    result = project_service.get_project(project_id)
    if not result:
        raise HTTPException(status_code=404, detail="项目不存在")
    return result

@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    result = project_service.delete_project(project_id)
    if not result:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"status": "deleted", "project_id": project_id}