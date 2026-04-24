"""Format (storyboard) generation node - Stage 2 of production pipeline."""

import json

from graphs.state import ProductionState
from repositories import project_repo, agent_repo
from repositories.shot_repo import create_shot
from repositories.production_event_repo import (
    add_production_event,
    update_project_stage,
    is_stage_completed,
)
from models import ProductionStage, STAGE_AGENT_MAP


async def format_node(state: ProductionState) -> dict:
    """Format scripts into structured storyboards with shot lists.

    This is Stage 2 of the production pipeline.
    """
    project_id = state["project_id"]
    agent_id = STAGE_AGENT_MAP[ProductionStage.FORMAT_GENERATING]

    # Check precondition
    if not is_stage_completed(project_id, ProductionStage.SCRIPT_COMPLETED.value):
        raise RuntimeError("Script must be completed before formatting")

    update_project_stage(project_id, ProductionStage.FORMAT_GENERATING.value, "in_progress")

    episodes = project_repo.get_episodes(project_id)
    total_shots = 0

    agent_repo.update_agent_state(
        project_id, agent_id,
        status="working",
        current_task="格式化分镜",
        completed_tasks=0,
        total_tasks=len(episodes),
    )

    add_production_event(
        project_id, agent_id, ProductionStage.FORMAT_GENERATING.value,
        "stage_started", "开始格式化分镜", "正在将剧本逐集转化为结构化分镜..."
    )

    for idx, ep in enumerate(episodes, start=1):
        episode_id = ep["episode_id"]
        script_json = ep.get("script_json")
        if not script_json:
            continue

        project_repo.update_episode(episode_id, status="storyboarding", progress=35)

        script = json.loads(script_json) if isinstance(script_json, str) else script_json
        scenes = script.get("scenes", [])
        storyboard = []
        shot_num = 0

        for scene in scenes:
            shot_num += 1
            storyboard.append({
                "shot_number": shot_num,
                "scene_number": scene.get("scene_number", 1),
                "description": f"{scene.get('location', '未知')} - {scene.get('description', '')[:80]}",
                "camera_movement": "固定机位",
                "duration": "3s",
                "dialogues": scene.get("dialogues", []),
            })

        if not storyboard:
            raise RuntimeError(f"第{ep['episode_number']}集分镜生成失败：剧本中无有效场景数据")

        project_repo.update_episode(episode_id, storyboard=storyboard, status="storyboarding", progress=45)

        # Create shot records
        for sb in storyboard:
            shot_id = f"{episode_id}_shot_{sb['shot_number']}"
            create_shot(
                shot_id, episode_id, project_id, sb["shot_number"],
                sb.get("description", ""), sb.get("camera_movement", ""), sb.get("duration", "")
            )
            total_shots += 1

        agent_repo.update_agent_state(
            project_id, agent_id, status="working",
            current_task=f"分镜格式化：第{ep['episode_number']}集",
            completed_tasks=idx, total_tasks=len(episodes)
        )

        add_production_event(
            project_id, agent_id, ProductionStage.FORMAT_GENERATING.value,
            "episode_format_completed", f"第{ep['episode_number']}集分镜完成",
            f"已生成 {len(storyboard)} 个镜头",
            episode_id=episode_id, payload={"shot_count": len(storyboard)}
        )

    # Mark stage completed
    update_project_stage(project_id, ProductionStage.FORMAT_GENERATING.value, "completed")
    update_project_stage(project_id, ProductionStage.FORMAT_COMPLETED.value, "completed")

    add_production_event(
        project_id, agent_id, ProductionStage.FORMAT_COMPLETED.value,
        "stage_completed", "分镜格式化完成", f"已创建 {total_shots} 个镜头"
    )

    agent_repo.update_agent_state(
        project_id, agent_id, status="idle", current_task=None,
        completed_tasks=len(episodes), total_tasks=len(episodes)
    )

    return {
        "current_stage": ProductionStage.FORMAT_COMPLETED.value,
    }
