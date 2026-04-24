"""Asset generation node - Stage 3 of production pipeline.

Generates character portraits and scene images using the configured
image generation provider.
"""

import json

from graphs.state import ProductionState
from repositories import project_repo, agent_repo
from repositories.production_event_repo import (
    add_production_event,
    update_project_stage,
    is_stage_completed,
    create_asset,
    update_asset,
    get_assets,
)
from models import ProductionStage, STAGE_AGENT_MAP
from integrations.image import is_image_configured, generate_image, is_image_demo_mode
from config import ASSETS_DIR, project_assets_dir


async def assets_node(state: ProductionState) -> dict:
    """Generate character portraits and scene establishing shots.

    This is Stage 3 of the production pipeline.
    For each character, generates a portrait image to lock visual identity.
    For each scene, generates an establishing shot.
    """
    project_id = state["project_id"]
    agent_id = STAGE_AGENT_MAP[ProductionStage.ASSETS_GENERATING]

    # Check precondition
    if not is_stage_completed(project_id, ProductionStage.FORMAT_COMPLETED.value):
        raise RuntimeError("Format must be completed before asset generation")

    update_project_stage(project_id, ProductionStage.ASSETS_GENERATING.value, "in_progress")

    characters = project_repo.get_characters(project_id)
    episodes = project_repo.get_episodes(project_id)

    # Count total assets to generate
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

    total_assets = len(characters) + len(scene_names)

    agent_repo.update_agent_state(
        project_id, agent_id,
        status="working",
        current_task="生成视觉资产",
        completed_tasks=0,
        total_tasks=max(1, total_assets),
    )

    add_production_event(
        project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
        "stage_started", "开始生成视觉资产", "正在为角色和场景生成视觉资产..."
    )

    # Update all episodes to asset_generating status
    for ep in episodes:
        project_repo.update_episode(ep["episode_id"], status="asset_generating", progress=55)

    completed_count = 0
    image_configured = is_image_configured()
    demo_mode = is_image_demo_mode()

    # Determine series type for style-aware prompts
    project = project_repo.get_project(project_id)
    config = project.get("config", {}) if project else {}
    if isinstance(config, str):
        import json as _json
        config = _json.loads(config)
    series_type = config.get("series_type", "live-action")
    state_series_type = state.get("series_type", series_type)
    series_type = state_series_type or series_type

    # --- Generate character turnaround reference sheets ---
    for i, char in enumerate(characters, start=1):
        asset_id = f"{project_id}_char_{i:03d}"

        name, role, desc = char['name'], char['role'], char['description']

        if series_type == "animation":
            prompt = f"""Professional anime character turnaround reference sheet for {name}, {role}, {desc}.

STRICT LAYOUT — Generate exactly 4 views in a single horizontal 2:1 image:
Panel 1 (LEFT): Full-body front view — standing straight, arms at sides, neutral expression
Panel 2 (CENTER-LEFT): Full-body 3/4 view — slightly turned, showing depth
Panel 3 (CENTER-RIGHT): Full-body side/profile view — facing left, showing profile
Panel 4 (RIGHT): Close-up face portrait — detailed facial features, neutral expression

ANIME/ILLUSTRATION STYLE:
- Clean anime/manga art style with crisp outlines
- Cel-shaded coloring, vibrant but balanced palette
- Consistent character design across all 4 views (same proportions, same outfit)
- Clean white background, no gradients or patterns
- Professional character design sheet quality
- Same hairstyle, eye design, and accessories in every view
- NO text labels, NO grid lines, NO arrows — only the character views
- High quality, detailed"""
        else:
            prompt = f"""Professional character turnaround reference sheet for {name}, {role}, {desc}.

STRICT LAYOUT — Generate exactly 4 views in a single horizontal 2:1 image:
Panel 1 (LEFT): Full-body front view — standing straight, arms at sides, neutral expression
Panel 2 (CENTER-LEFT): Full-body 3/4 view — slightly turned, showing depth
Panel 3 (CENTER-RIGHT): Full-body side/profile view — facing left, showing profile
Panel 4 (RIGHT): Close-up face portrait — detailed facial features, neutral expression

PHOTOREALISTIC STYLE:
- Hyper-realistic rendering, as if photographed
- Natural skin texture, realistic lighting (soft studio 3-point lighting)
- Professional actor headshot quality
- Consistent clothing, hairstyle, accessories across all 4 views
- Clean white studio background with subtle shadow on ground
- Same body proportions and facial features in every view
- NO text labels, NO grid lines, NO arrows — only the character views
- High quality, detailed"""

        add_production_event(
            project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
            "prompt_issued", f"角色设定图提示词：{char['name']}",
            f"开始为角色 {char['name']} 生成角色设定图",
            payload={"prompt": prompt[:200]}
        )

        create_asset(
            asset_id, project_id, "character", char["name"], char["description"],
            prompt=prompt, anchor_prompt=f"{char['name']}, {char['role']}, character turnaround reference sheet, front/side/back/face views, {'anime' if series_type == 'animation' else 'photorealistic'}"
        )

        if image_configured or demo_mode:
            try:
                output_path = str(project_assets_dir(project_id) / f"{asset_id}.png")

                await generate_image(prompt, output_path, aspect_ratio="2:1")

                update_asset(asset_id, image_path=f"/assets/{project_id}/{asset_id}.png")
                add_production_event(
                    project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
                    "output_captured", f"角色设定图完成：{char['name']}",
                    "已生成角色设定图（全身前/侧/后视图+大脸照）",
                    payload={"output": f"/assets/{project_id}/{asset_id}.png"}
                )
            except Exception as e:
                add_production_event(
                    project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
                    "asset_failed", f"角色肖像失败：{char['name']}",
                    str(e),
                    payload={"error": str(e)}
                )

        completed_count += 1
        agent_repo.update_agent_state(
            project_id, agent_id, status="working",
            current_task=f"资产生成：角色 {char['name']}",
            completed_tasks=completed_count, total_tasks=max(1, total_assets)
        )

    # --- Generate scene establishing shots ---
    for i, scene_name in enumerate(scene_names, start=1):
        asset_id = f"{project_id}_scene_{i:03d}"
        if series_type == "animation":
            prompt = f"{scene_name}, anime style establishing shot, vibrant, cel-shaded, wide angle, cinematic composition, illustration"
        else:
            prompt = f"{scene_name}, establishing shot, photorealistic, cinematic, natural lighting, high quality, wide angle"

        create_asset(
            asset_id, project_id, "scene", scene_name, f"场景: {scene_name}",
            prompt=prompt
        )

        if image_configured or demo_mode:
            try:
                output_path = str(project_assets_dir(project_id) / f"{asset_id}.png")

                await generate_image(prompt, output_path, aspect_ratio="16:9")

                update_asset(asset_id, image_path=f"/assets/{project_id}/{asset_id}.png")
                add_production_event(
                    project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
                    "output_captured", f"场景图完成：{scene_name}",
                    "已生成场景图",
                    payload={"output": f"/assets/{project_id}/{asset_id}.png"}
                )
            except Exception as e:
                add_production_event(
                    project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
                    "asset_failed", f"场景图失败：{scene_name}",
                    str(e),
                    payload={"error": str(e)}
                )

        completed_count += 1

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
        completed_tasks=max(1, total_assets), total_tasks=max(1, total_assets)
    )

    return {
        "current_stage": ProductionStage.ASSETS_COMPLETED.value,
        "characters": [
            {"name": c["name"], "role": c["role"], "description": c["description"]}
            for c in characters
        ],
    }
