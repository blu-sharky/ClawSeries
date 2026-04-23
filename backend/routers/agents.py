"""
Agent routes with production events.
"""

from fastapi import APIRouter, HTTPException
from services.agent_service import AgentService

router = APIRouter()
agent_service = AgentService()


@router.get("/projects/{project_id}/agents")
async def get_agents(project_id: str):
    return agent_service.get_agents(project_id)


@router.get("/projects/{project_id}/agents/{agent_id}/logs")
async def get_agent_logs(project_id: str, agent_id: str):
    result = agent_service.get_agent_logs(project_id, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="智能体不存在")
    return result


@router.get("/projects/{project_id}/agents/{agent_id}/events")
async def get_agent_events(project_id: str, agent_id: str):
    """Get structured production events for an agent."""
    result = agent_service.get_agent_events(project_id, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="智能体不存在")
    return result


@router.get("/projects/{project_id}/timeline")
async def get_project_timeline(project_id: str):
    """Get the full production timeline for a project."""
    from repositories.production_event_repo import get_production_events
    events = get_production_events(project_id, limit=200)
    return {"project_id": project_id, "timeline": events}