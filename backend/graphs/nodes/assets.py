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
            prompt = f"""best quality, masterpiece, character design reference sheet, pure white background, same character shown in 4 views arranged horizontally left to right, {name}, {role}, {desc}.

LAYOUT — 4 views in a single horizontal image:
View 1 (FAR LEFT): Face close-up portrait — detailed facial features, eyes, hairstyle construction, neutral expression, head and shoulders only
View 2 (LEFT): Full-body front view — standing straight, arms relaxed at sides, facing camera, neutral expression
View 3 (CENTER): Full-body left side profile view — standing straight, facing left, showing nose/chin/body profile depth
View 4 (RIGHT): Full-body back view — showing hair from behind, outfit rear details, same standing pose

ANIME/ILLUSTRATION STYLE:
- Clean anime/manga art style with crisp outlines and cel-shaded coloring
- Vibrant but balanced palette
- Pure solid white background (#FFFFFF) — no gradients, no shadows, no floor reflection
- Consistent character design across all 4 views: identical proportions, outfit, hairstyle, eye design, accessories
- Neutral relaxed standing pose in all full-body views
- Clean even spacing between each view, no overlap
- Flat even lighting with no dramatic shadows
- Professional concept art reference sheet quality
- NO text labels, NO grid lines, NO arrows, NO color swatches — only the character views
- NO environmental background, NO props, NO scene context"""
        else:
            prompt = f"""best quality, masterpiece, photorealistic character design reference sheet, pure white background, same person shown in 4 views arranged horizontally left to right, {name}, {role}, {desc}.

LAYOUT — 4 views in a single horizontal image:
View 1 (FAR LEFT): Face close-up portrait — detailed facial features, skin texture, eyes, hairstyle, neutral expression, professional headshot framing
View 2 (LEFT): Full-body front view — standing straight, arms relaxed at sides, facing camera, natural neutral expression
View 3 (CENTER): Full-body left side profile view — standing straight, facing left, showing nose/chin/body profile depth and posture
View 4 (RIGHT): Full-body back view — showing hair from behind, outfit rear details, same standing pose and build

PHOTOREALISTIC STYLE:
- Hyper-realistic rendering, as if photographed in a professional studio
- Natural skin texture, realistic proportions, professional actor headshot quality
- Pure solid white background (#FFFFFF) — no gradients, no shadows, no floor
- Flat even studio lighting — no dramatic shadows that alter appearance between views
- Consistent person across all 4 views: identical face, body proportions, clothing, hairstyle, accessories in every view
- Neutral relaxed standing pose in all full-body views
- Clean even spacing between each view, no overlap between figures
- Same outfit, same grooming, same accessories in every view without any variation
- Professional casting photo reference sheet quality
- NO text labels, NO grid lines, NO arrows — only the person views
- NO environmental background, NO props, NO scene context"""

        add_production_event(
            project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
            "prompt_issued", f"角色设定图提示词：{char['name']}",
            f"开始为角色 {char['name']} 生成角色设定图",
            payload={"prompt": prompt[:200]}
        )

        create_asset(
            asset_id, project_id, "character", char["name"], char["description"],
            prompt=prompt, anchor_prompt=f"{char['name']}, {char['role']}, character design reference sheet, face closeup + full-body front/side/back views, pure white background, {'anime' if series_type == 'animation' else 'photorealistic'}"
        )

        if image_configured or demo_mode:
            try:
                output_path = str(project_assets_dir(project_id) / f"{asset_id}.png")

                await generate_image(prompt, output_path, aspect_ratio="2:1")

                update_asset(asset_id, image_path=f"/assets/{project_id}/{asset_id}.png")
                add_production_event(
                    project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
                    "output_captured", f"角色设定图完成：{char['name']}",
                    "已生成角色设定图（脸部特写+全身前/侧/后视图，白底）",
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
