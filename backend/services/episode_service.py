"""
Episode service - SQLite-backed episode detail management with stage gates.
"""

import json
import re
from repositories import project_repo, shot_repo
from repositories.shot_repo import get_episode_traces
from repositories.production_event_repo import get_production_events


class EpisodeService:
    def get_episode(self, project_id: str, episode_id: str) -> dict | None:
        episode = project_repo.get_episode(episode_id)
        if not episode or episode["project_id"] != project_id:
            return None

        # Parse JSON fields
        script = json.loads(episode.get("script_json") or "null")
        storyboard = json.loads(episode.get("storyboard_json") or "null")
        assets = json.loads(episode.get("assets_json") or "{}")
        events = get_production_events(project_id, episode_id=episode_id, limit=50)
        recovered_script = self._recover_script_from_events(events)
        if recovered_script:
            script = recovered_script

        result = {
            "episode_id": episode["episode_id"],
            "episode_number": episode["episode_number"],
            "title": episode["title"],
            "status": episode["status"],
            "duration": episode.get("duration"),
            "progress": episode.get("progress", 0),
            # Stage-gated: only show what exists
            "has_script": script is not None,
            "has_storyboard": storyboard is not None and len(storyboard) > 0,
            "script": script,
            "storyboard": storyboard or [],
            "assets": assets or {"videos": [], "audios": [], "images": []},
            "video_url": episode.get("video_url"),
        }

        # Include shots only if storyboard exists (stage gate)
        if storyboard:
            shots = shot_repo.get_shots_by_episode(episode_id)
            if shots:
                result["shots"] = shots

        # Include timeline from production events
        result["timeline"] = events

        return result

    def _recover_script_from_events(self, events: list[dict]) -> dict | None:
        for event in reversed(events):
            if event.get("event_type") != "output_captured":
                continue
            if event.get("stage") != "script_generating":
                continue

            output = (event.get("payload") or {}).get("output")
            if not output:
                continue

            json_match = re.search(r'\{[\s\S]*\}', output)
            if not json_match:
                continue

            try:
                parsed = json.loads(json_match.group())
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict) and isinstance(parsed.get("scenes"), list):
                return parsed
        return None


    def get_video_path(self, project_id: str, episode_id: str) -> str | None:
        episode = project_repo.get_episode(episode_id)
        if not episode or episode["project_id"] != project_id:
            return None
        if episode["status"] == "completed":
            return episode.get("video_url")
        return None

    def get_episode_traces(self, project_id: str, episode_id: str) -> list:
        return get_episode_traces(project_id, episode_id)
