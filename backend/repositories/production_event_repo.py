"""
Production event repository - SQLite-backed structured event stream.
"""

import json
from storage.db import get_connection


def add_production_event(
    project_id: str,
    agent_id: str,
    stage: str,
    event_type: str,
    title: str,
    message: str,
    episode_id: str | None = None,
    shot_id: str | None = None,
    payload: dict | None = None,
) -> int:
    """Add a structured production event. Returns the event id."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO production_events
           (project_id, episode_id, shot_id, agent_id, stage, event_type, title, message, payload_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            episode_id,
            shot_id,
            agent_id,
            stage,
            event_type,
            title,
            message,
            json.dumps(payload or {}, ensure_ascii=False),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_production_events(
    project_id: str,
    episode_id: str | None = None,
    agent_id: str | None = None,
    stage: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Get production events, optionally filtered."""
    conn = get_connection()
    query = "SELECT * FROM production_events WHERE project_id = ?"
    params = [project_id]

    if episode_id:
        query += " AND episode_id = ?"
        params.append(episode_id)
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    if stage:
        query += " AND stage = ?"
        params.append(stage)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    result = []
    for row in rows:
        e = dict(row)
        e["payload"] = json.loads(e["payload_json"]) if e["payload_json"] else {}
        del e["payload_json"]
        result.append(e)
    return list(reversed(result))


def get_latest_event_for_stage(project_id: str, stage: str) -> dict | None:
    """Get the most recent event for a specific stage."""
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM production_events
           WHERE project_id = ? AND stage = ?
           ORDER BY id DESC LIMIT 1""",
        (project_id, stage),
    ).fetchone()
    if not row:
        return None
    e = dict(row)
    e["payload"] = json.loads(e["payload_json"]) if e["payload_json"] else {}
    del e["payload_json"]
    return e


# === Project stage tracking ===


def init_project_stages(project_id: str):
    """Initialize all stage records for a project."""
    from models import ProductionStage

    conn = get_connection()
    for stage in ProductionStage:
        conn.execute(
            """INSERT INTO project_stages (project_id, stage, status)
               VALUES (?, ?, 'pending')
               ON CONFLICT(project_id, stage) DO NOTHING""",
            (project_id, stage.value),
        )
    conn.commit()


def update_project_stage(
    project_id: str,
    stage: str,
    status: str,
    error_message: str | None = None,
):
    """Update the status of a project stage."""
    from datetime import datetime

    conn = get_connection()
    sets = ["status = ?"]
    params = [status]

    if status == "in_progress":
        sets.append("started_at = ?")
        params.append(datetime.utcnow().isoformat())
    elif status in ("completed", "failed"):
        sets.append("completed_at = ?")
        params.append(datetime.utcnow().isoformat())

    if error_message:
        sets.append("error_message = ?")
        params.append(error_message)

    params.extend([project_id, stage])
    conn.execute(
        f"""UPDATE project_stages SET {', '.join(sets)}
           WHERE project_id = ? AND stage = ?""",
        params,
    )
    conn.commit()


def get_project_stages(project_id: str) -> list[dict]:
    """Get all stage statuses for a project."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM project_stages WHERE project_id = ? ORDER BY stage",
        (project_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_current_stage(project_id: str) -> dict | None:
    """Get the current in-progress stage, or the next pending one."""
    conn = get_connection()
    # First check for in-progress
    row = conn.execute(
        """SELECT * FROM project_stages
           WHERE project_id = ? AND status = 'in_progress'
           LIMIT 1""",
        (project_id,),
    ).fetchone()
    if row:
        return dict(row)
    # Then find the first pending (ordered by enum sequence)
    from models import ProductionStage
    when_clauses = []
    for i, s in enumerate(ProductionStage):
        when_clauses.append(f"WHEN '{s.value}' THEN {i}")
    case_expr = "CASE stage " + " ".join(when_clauses) + " END"
    row = conn.execute(
        f"""SELECT * FROM project_stages
           WHERE project_id = ? AND status = 'pending'
           ORDER BY {case_expr} LIMIT 1""",
        (project_id,),
    ).fetchone()
    if row:
        return dict(row)
    return None


def is_stage_completed(project_id: str, stage: str) -> bool:
    """Check if a specific stage is completed."""
    conn = get_connection()
    row = conn.execute(
        """SELECT status FROM project_stages
           WHERE project_id = ? AND stage = ?""",
        (project_id, stage),
    ).fetchone()
    return row and row["status"] == "completed"


# === Asset management ===


def create_asset(
    asset_id: str,
    project_id: str,
    type: str,
    name: str,
    description: str = "",
    episode_id: str | None = None,
    prompt: str | None = None,
    image_path: str | None = None,
    anchor_prompt: str | None = None,
    reference_image_path: str | None = None,
    embedding_ref: str | None = None,
):
    """Create a new asset record."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO assets
           (asset_id, project_id, episode_id, type, name, description,
            prompt, image_path, anchor_prompt, reference_image_path, embedding_ref)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            asset_id,
            project_id,
            episode_id,
            type,
            name,
            description,
            prompt,
            image_path,
            anchor_prompt,
            reference_image_path,
            embedding_ref,
        ),
    )
    conn.commit()


def get_assets(
    project_id: str,
    type: str | None = None,
    episode_id: str | None = None,
) -> list[dict]:
    """Get assets for a project, optionally filtered by type or episode."""
    conn = get_connection()
    query = "SELECT * FROM assets WHERE project_id = ?"
    params = [project_id]

    if type:
        query += " AND type = ?"
        params.append(type)
    if episode_id:
        query += " AND episode_id = ?"
        params.append(episode_id)

    query += " ORDER BY created_at"
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_asset(asset_id: str) -> dict | None:
    """Get a single asset by id."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
    return dict(row) if row else None


def update_asset(asset_id: str, **kwargs):
    """Update an asset."""
    conn = get_connection()
    sets = []
    vals = []
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.append(asset_id)
    conn.execute(
        f"UPDATE assets SET {', '.join(sets)} WHERE asset_id = ?",
        vals,
    )
    conn.commit()
