"""Main LangGraph production graph definition."""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from graphs.state import ProductionState
from graphs.nodes.script import script_node
from graphs.nodes.format import format_node
from graphs.nodes.assets import assets_node
from graphs.nodes.shots import shots_node
from graphs.nodes.compose import episode_compose_node, project_compose_node
from graphs.routers.edge_routers import (
    shots_router,
    episode_shot_router,
    episode_compose_router,
)


def create_production_graph() -> StateGraph:
    """Create the production pipeline StateGraph.

    Graph structure:
    START → script_node → format_node → assets_node
          → [shots_router] → shots_node → [episode_shot_router] → episode_compose_node
          → [episode_compose_router] → (shots_node or project_compose_node) → END
    """
    graph = StateGraph(ProductionState)

    # Add nodes
    graph.add_node("script_node", script_node)
    graph.add_node("format_node", format_node)
    graph.add_node("assets_node", assets_node)
    graph.add_node("shots_node", shots_node)
    graph.add_node("episode_compose_node", episode_compose_node)
    graph.add_node("project_compose_node", project_compose_node)

    # Add edges
    graph.add_edge(START, "script_node")
    graph.add_edge("script_node", "format_node")
    graph.add_edge("format_node", "assets_node")

    # Conditional edges from assets_node
    graph.add_conditional_edges(
        "assets_node",
        shots_router,
        {
            "shots_node": "shots_node",
            "episode_compose_router": "episode_compose_node",
        },
    )

    # Conditional edges from shots_node
    graph.add_conditional_edges(
        "shots_node",
        episode_shot_router,
        {
            "episode_compose_node": "episode_compose_node",
            "shots_node": "shots_node",
            "project_compose_node": "project_compose_node",
        },
    )

    # Conditional edges from episode_compose_node
    graph.add_conditional_edges(
        "episode_compose_node",
        episode_compose_router,
        {
            "shots_node": "shots_node",
            "project_compose_node": "project_compose_node",
        },
    )

    # Final edge
    graph.add_edge("project_compose_node", END)

    return graph


def compile_production_graph(checkpointer: SqliteSaver | None = None) -> StateGraph:
    """Compile the production graph with optional checkpointer.

    Args:
        checkpointer: Optional SqliteSaver for state persistence.
                     If None, graph runs without checkpointing.

    Returns:
        Compiled StateGraph ready for execution.
    """
    graph = create_production_graph()
    return graph.compile(checkpointer=checkpointer)
