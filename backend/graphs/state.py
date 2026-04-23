"""LangGraph state schema for production pipeline."""

from typing import TypedDict, Annotated


def merge_dicts(left: dict, right: dict) -> dict:
    """Reducer: merge right dict into left dict."""
    return {**left, **right}


def append_list(left: list, right: list) -> list:
    """Reducer: append right list to left list."""
    return left + right


class EpisodeState(TypedDict, total=False):
    """State for a single episode within production."""

    episode_id: str
    episode_number: int
    title: str
    status: str
    progress: int
    script: dict | None  # parsed script JSON
    storyboard: list | None
    shots: list | None
    video_url: str | None


class ProductionState(TypedDict, total=False):
    """Main state for LangGraph production pipeline.

    This state tracks the entire production flow from script generation
    to final project composition.
    """

    # Project metadata
    project_id: str
    title: str
    status: str
    config: Annotated[dict, merge_dicts]

    # Characters
    characters: list[dict]

    # Episodes (flat list, indexed by current_episode_index)
    episodes: list[EpisodeState]

    # Current execution state
    current_stage: str
    current_episode_index: int | None  # index into episodes list
    current_shot_index: int | None  # index into current episode's shots

    # Production events (timeline)
    events: Annotated[list[dict], append_list]

    # Errors
    errors: Annotated[list[dict], append_list]

    # Human-in-the-loop
    awaiting_input: bool
    interrupt_data: dict | None

    # Video mode
    video_mode: str  # "manual" or "auto"
