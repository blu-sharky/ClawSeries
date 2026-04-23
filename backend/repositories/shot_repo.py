"""
Shot repository - SQLite-backed shot and trace persistence.
"""

import json
from storage.db import get_connection


def create_shot(shot_id: str, episode_id: str, project_id: str,
                shot_number: int, description: str = "",
                camera_movement: str = "", duration: str = ""):
    conn = get_connection()
    conn.execute(
        """INSERT INTO shots (shot_id, episode_id, project_id, shot_number, description, camera_movement, duration)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (shot_id, episode_id, project_id, shot_number, description, camera_movement, duration),
    )
    conn.commit()


def get_shots_by_episode(episode_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM shots WHERE episode_id = ? ORDER BY shot_number",
        (episode_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def update_shot(shot_id: str, **kwargs):
    conn = get_connection()
    sets = []
    vals = []
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.append(shot_id)
    conn.execute(
        f"UPDATE shots SET {', '.join(sets)} WHERE shot_id = ?",
        vals,
    )
    conn.commit()


def add_shot_trace(shot_id: str, project_id: str, stage: str,
                   agent_id: str | None = None,
                   chroma_hits: list | None = None,
                   assets_referenced: list | None = None,
                   prompt_summary: str | None = None,
                   prompt_hash: str | None = None,
                   provider_name: str | None = None,
                   model_name: str | None = None,
                   output_path: str | None = None,
                   cache_hit: bool = False,
                   error_reason: str | None = None,
                   duration_ms: int | None = None,
                   retry_count: int = 0):
    conn = get_connection()
    conn.execute(
        """INSERT INTO shot_traces
           (shot_id, project_id, agent_id, stage, chroma_hits_json, assets_referenced_json,
            prompt_summary, prompt_hash, provider_name, model_name, output_path,
            cache_hit, error_reason, duration_ms, retry_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (shot_id, project_id, agent_id, stage,
         json.dumps(chroma_hits or [], ensure_ascii=False),
         json.dumps(assets_referenced or [], ensure_ascii=False),
         prompt_summary, prompt_hash, provider_name, model_name, output_path,
         1 if cache_hit else 0, error_reason, duration_ms, retry_count),
    )
    conn.commit()


def get_shot_traces(shot_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM shot_traces WHERE shot_id = ? ORDER BY created_at",
        (shot_id,),
    ).fetchall()
    result = []
    for row in rows:
        t = dict(row)
        t["chroma_hits"] = json.loads(t["chroma_hits_json"]) if t["chroma_hits_json"] else []
        t["assets_referenced"] = json.loads(t["assets_referenced_json"]) if t["assets_referenced_json"] else []
        t["cache_hit"] = bool(t["cache_hit"])
        del t["chroma_hits_json"]
        del t["assets_referenced_json"]
        result.append(t)
    return result


def get_episode_traces(project_id: str, episode_id: str) -> list[dict]:
    """Get all traces for all shots in an episode."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT st.* FROM shot_traces st
           JOIN shots s ON st.shot_id = s.shot_id
           WHERE s.episode_id = ? AND st.project_id = ?
           ORDER BY s.shot_number, st.created_at""",
        (episode_id, project_id),
    ).fetchall()
    result = []
    for row in rows:
        t = dict(row)
        t["chroma_hits"] = json.loads(t["chroma_hits_json"]) if t["chroma_hits_json"] else []
        t["assets_referenced"] = json.loads(t["assets_referenced_json"]) if t["assets_referenced_json"] else []
        t["cache_hit"] = bool(t["cache_hit"])
        del t["chroma_hits_json"]
        del t["assets_referenced_json"]
        result.append(t)
    return result
