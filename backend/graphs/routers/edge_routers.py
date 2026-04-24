"""Conditional edge routers for production graph."""

from graphs.state import ProductionState
from repositories import project_repo
from models import ProductionStage


def shots_router(state: ProductionState) -> str:
    """Route after assets node: go to shots_node for the first episode."""
    return "shots_node"


def episode_shot_router(state: ProductionState) -> str:
    """Route after shots_node: check if more episodes need shots or go to compose.

    Returns:
        "episode_compose_node" to compose current episode
        "project_compose_node" if all episodes are already completed
    """
    project_id = state["project_id"]
    episodes = project_repo.get_episodes(project_id)
    all_completed = all(ep["status"] == "completed" for ep in episodes)

    if all_completed:
        return "project_compose_node"

    return "episode_compose_node"


def episode_compose_router(state: ProductionState) -> str:
    """Route after episode_compose_node: check if more episodes remain.

    Returns:
        "shots_node" if more episodes need shots
        "project_compose_node" if all episodes completed
    """
    project_id = state["project_id"]
    current_episode_index = state.get("current_episode_index", 0)
    episodes = project_repo.get_episodes(project_id)

    # Check if all episodes are completed
    all_completed = all(ep["status"] == "completed" for ep in episodes)

    if all_completed:
        return "project_compose_node"

    # Find next uncompleted episode index
    for idx, ep in enumerate(episodes):
        if ep["status"] != "completed":
            return "shots_node"

    return "project_compose_node"
