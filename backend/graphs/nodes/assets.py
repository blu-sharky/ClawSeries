"""Asset generation node - Stage 3 of production pipeline."""

import json

from graphs.state import ProductionState
from repositories import project_repo, agent_repo
from repositories.production_event_repo import (
    add_production_event,
    update_project_stage,
    is_stage_completed,
    create_asset,
)
from models import ProductionStage, STAGE_AGENT_MAP


async def assets_node(state: ProductionState) -> dict:
    """Generate character and scene assets.

    This is Stage 3 of the production pipeline.
    """
    project_id = state["project_id"]
    agent_id = STAGE_AGENT_MAP[ProductionStage.ASSETS_GENERATING]

    # Check precondition
    if not is_stage_completed(project_id, ProductionStage.FORMAT_COMPLETED.value):
        raise RuntimeError("Format must be completed before asset generation")

    update_project_stage(project_id, ProductionStage.ASSETS_GENERATING.value, "in_progress")

    characters = project_repo.get_characters(project_id)
    episodes = project_repo.get_episodes(project_id)

    agent_repo.update_agent_state(
        project_id, agent_id,
        status="working",
        current_task="生成视觉资产",
        completed_tasks=0,
        total_tasks=max(1, len(characters)),
    )

    add_production_event(
        project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
        "stage_started", "开始生成视觉资产", "正在为角色和场景生成视觉资产..."
    )

    # Update all episodes to asset_generating status
    for ep in episodes:
        project_repo.update_episode(ep["episode_id"], status="asset_generating", progress=55)

    # Create character assets
    for i, char in enumerate(characters, start=1):
        asset_id = f"asset_char_{i:03d}"
        prompt = f"{char['name']}, {char['description']}, portrait, consistent character design"
        add_production_event(
            project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
            "prompt_issued", f"角色资产提示词：{char['name']}",
            f"开始为角色 {char['name']} 锁定视觉锚点",
            payload={"prompt": prompt}
        )
        create_asset(
            asset_id, project_id, "character", char["name"], char["description"],
            prompt=prompt, anchor_prompt=f"{char['name']}, {char['role']}, consistent face"
        )
        add_production_event(
            project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
            "output_captured", f"角色资产完成：{char['name']}",
            "已锁定角色视觉锚点",
            payload={"output": f"角色资产已锁定：{char['name']}"}
        )
        agent_repo.update_agent_state(
            project_id, agent_id, status="working",
            current_task=f"资产生成：角色 {char['name']}",
            completed_tasks=i, total_tasks=max(1, len(characters))
        )

    # Extract scene names from scripts
    scene_names = set()
    for ep in episodes:
        script_json = ep.get("script_json")
        if not script_json:
            continue
        script = json.loads(script_json) if isinstance(script_json, str) else script_json
        for scene in script.get("scenes", []):
            loc = scene.get("location", "")
            if loc:
                scene_names.add(loc)

    # Create scene assets
    for i, scene_name in enumerate(scene_names, start=1):
        asset_id = f"asset_scene_{i:03d}"
        create_asset(
            asset_id, project_id, "scene", scene_name, f"场景: {scene_name}",
            prompt=f"{scene_name}, establishing shot, cinematic"
        )

    # Update episode progress
    for ep in episodes:
        project_repo.update_episode(ep["episode_id"], status="asset_generating", progress=60)

    # Mark stage completed
    update_project_stage(project_id, ProductionStage.ASSETS_GENERATING.value, "completed")
    update_project_stage(project_id, ProductionStage.ASSETS_COMPLETED.value, "completed")

    add_production_event(
        project_id, agent_id, ProductionStage.ASSETS_COMPLETED.value,
        "stage_completed", "视觉资产生成完成",
        f"已创建 {len(characters)} 个角色资产, {len(scene_names)} 个场景资产"
    )

    agent_repo.update_agent_state(
        project_id, agent_id, status="idle", current_task=None,
        completed_tasks=max(1, len(characters)), total_tasks=max(1, len(characters))
    )

    return {
        "current_stage": ProductionStage.ASSETS_COMPLETED.value,
        "characters": [
            {"name": c["name"], "role": c["role"], "description": c["description"]}
            for c in characters
        ],
    }
