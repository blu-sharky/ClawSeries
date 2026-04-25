"""
Task repository - SQLite-backed task persistence for the production pipeline.
"""

import json
from storage.db import get_connection


def create_task(task_id: str, project_id: str, task_type: str,
                episode_id: str | None = None, shot_id: str | None = None,
                agent_id: str | None = None, input_data: dict | None = None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO tasks (task_id, project_id, episode_id, shot_id, task_type, agent_id, input_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(task_id) DO UPDATE SET
               project_id = excluded.project_id,
               episode_id = excluded.episode_id,
               shot_id = excluded.shot_id,
               task_type = excluded.task_type,
               agent_id = excluded.agent_id,
               input_json = excluded.input_json,
               output_json = NULL,
               error_message = NULL,
               retry_count = 0,
               status = 'pending',
               started_at = NULL,
               completed_at = NULL
           WHERE tasks.status = 'failed'""",
        (task_id, project_id, episode_id, shot_id, task_type, agent_id,
         json.dumps(input_data or {}, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def get_tasks_by_project(project_id: str, status: str | None = None) -> list[dict]:
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND status = ? ORDER BY created_at",
            (project_id, status),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_tasks_by_episode(project_id: str, episode_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE project_id = ? AND episode_id = ? ORDER BY created_at",
        (project_id, episode_id),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_task(task_id: str, **kwargs):
    conn = get_connection()
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k in ("input_json", "output_json") and not isinstance(v, str):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.append(task_id)
    conn.execute(
        f"UPDATE tasks SET {', '.join(sets)} WHERE task_id = ?",
        vals,
    )
    conn.commit()
    conn.close()


def reset_running_tasks(project_id: str):
    conn = get_connection()
    conn.execute(
        "UPDATE tasks SET status = 'pending', started_at = NULL WHERE project_id = ? AND status = 'running'",
        (project_id,),
    )
    conn.commit()
    conn.close()


def get_pending_tasks(project_id: str) -> list[dict]:
    return get_tasks_by_project(project_id, status="pending")


def get_task(task_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
