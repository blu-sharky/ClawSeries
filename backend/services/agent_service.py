"""
Agent service - SQLite-backed agent state management with production events.
"""

from repositories import agent_repo
from repositories.production_event_repo import get_production_events
from models import AgentInfo


class AgentService:
    def get_agents(self, project_id: str) -> dict:
        # Check if agents already exist before initializing (avoid write on every poll)
        states = agent_repo.get_agent_states(project_id)
        if not states:
            agent_repo.init_agent_states(project_id)
            states = agent_repo.get_agent_states(project_id)
        agents = [
            AgentInfo(
                agent_id=s["agent_id"],
                name=s["name"],
                status=s["status"],
                current_task=s.get("current_task"),
                completed_tasks=s["completed_tasks"],
                total_tasks=s["total_tasks"],
            )
            for s in states
        ]
        return {"agents": agents}

    def get_agent_logs(self, project_id: str, agent_id: str) -> dict | None:
        states = agent_repo.get_agent_states(project_id)
        agent_ids = {s["agent_id"] for s in states}
        if agent_id not in agent_ids:
            return None
        logs = agent_repo.get_agent_logs(project_id, agent_id)
        return {"agent_id": agent_id, "logs": logs}

    def get_agent_events(self, project_id: str, agent_id: str, limit: int = 100) -> dict | None:
        """Get structured production events for an agent."""
        states = agent_repo.get_agent_states(project_id)
        agent_ids = {s["agent_id"] for s in states}
        if agent_id not in agent_ids:
            return None
        events = get_production_events(project_id, agent_id=agent_id, limit=limit)
        return {"agent_id": agent_id, "events": events}
