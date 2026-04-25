"""
Project service - SQLite-backed project management with stage tracking.
"""

import json
from repositories import project_repo
from storage.db import get_connection
from repositories.production_event_repo import get_project_stages, get_current_stage, get_production_events, get_assets
from models import (
    ProjectSummary, ProjectDetail, Character, EpisodeSummary,
    ProjectSummaryExtended, StageInfo, STAGE_AGENT_MAP,
)


# Map of stage to human-readable title
STAGE_TITLES = {
    "requirements_confirmed": "需求确认",
    "script_generating": "剧本生成中",
    "script_completed": "剧本完成",
    "format_generating": "分镜格式化中",
    "format_completed": "分镜完成",
    "assets_generating": "资产生成中",
    "assets_completed": "资产完成",
    "shots_generating": "镜头生成中",
    "shots_completed": "镜头完成",
    "episode_composing": "剧集合成中",
    "episode_completed": "剧集完成",
    "project_composing": "项目合成中",
    "project_completed": "项目完成",
}

# The ordered pipeline stages for display
PIPELINE_STAGES = [
    "requirements_confirmed",
    "script_completed",
    "format_completed",
    "assets_completed",
    "shots_completed",
    "episode_completed",
    "project_completed",
]


class ProjectService:
    def get_projects(self) -> dict:
        projects = project_repo.get_all_projects()
        summaries = []
        for p in projects:
            completed = project_repo.get_completed_episode_count(p["project_id"])
            episodes = project_repo.get_episodes(p["project_id"])
            current = get_current_stage(p["project_id"])

            summaries.append(ProjectSummaryExtended(
                project_id=p["project_id"],
                title=p["title"],
                status=p["status"],
                progress=p["progress"],
                created_at=p["created_at"],
                episode_count=len(episodes),
                completed_episodes=completed,
                current_stage=current["stage"] if current else None,
                current_agent=STAGE_AGENT_MAP.get(current["stage"]) if current else None,
            ))
        return {"projects": summaries, "total": len(summaries)}

    def get_project(self, project_id: str) -> dict | None:
        p = project_repo.get_project(project_id)
        if not p:
            return None

        characters = project_repo.get_characters(project_id)

        # Load character turnaround sheet assets
        char_assets = {a["name"]: a for a in get_assets(project_id, type="character")}

        char_models = [
            {
                "character_id": c["character_id"],
                "name": c["name"],
                "age": c["age"],
                "gender": c.get("visual_assets", {}).get("gender"),
                "role": c["role"],
                "description": c["description"],
                "visual_assets": c.get("visual_assets", {}),
                "portrait_url": char_assets.get(c["name"], {}).get("image_path"),
                "sheet_url": char_assets.get(c["name"], {}).get("image_path"),
            }
            for c in characters
        ]

        episodes = project_repo.get_episodes(project_id)
        ep_models = [
            {
                "episode_id": e["episode_id"],
                "episode_number": e["episode_number"],
                "title": e["title"],
                "status": e["status"],
                "progress": e["progress"],
                "duration": e.get("duration"),
                "video_url": e.get("video_url"),
            }
            for e in episodes
        ]

        # Build stage info
        stages = get_project_stages(project_id)
        current = get_current_stage(project_id)

        stage_infos = []
        for stage in stages:
            agent_id = STAGE_AGENT_MAP.get(stage["stage"], "agent_director")
            title = STAGE_TITLES.get(stage["stage"], stage["stage"])
            stage_infos.append(StageInfo(
                stage=stage["stage"],
                agent_id=agent_id,
                status=stage["status"],
                title=title,
            ))

        result = {
            "project_id": p["project_id"],
            "title": p["title"],
            "status": p["status"],
            "progress": p["progress"],
            "created_at": p["created_at"],
            "config": p.get("config", {}),
            "characters": char_models,
            "episodes": ep_models,
            "current_stage": current["stage"] if current else None,
            "current_agent": STAGE_AGENT_MAP.get(current["stage"]) if current else None,
            "stages": [s.model_dump() for s in stage_infos],
        }

        return result

    def delete_project(self, project_id: str) -> bool:
        p = project_repo.get_project(project_id)
        if not p:
            return False

        conn = get_connection()
        conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
        conn.commit()
        return True
