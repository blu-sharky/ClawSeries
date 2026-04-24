"""Shot video generation node - Stage 4 of production pipeline.

For each shot:
1. Generate a first-frame image using the shot description
2. Pass the first frame as reference to video generation
"""

import hashlib

from langgraph.types import interrupt

from graphs.state import ProductionState
from repositories import project_repo, agent_repo
from repositories.shot_repo import get_shots_by_episode, update_shot, add_shot_trace
from repositories.production_event_repo import (
    add_production_event,
    update_project_stage,
    is_stage_completed,
    get_assets,
)
from repositories.settings_repo import get_setting
from routers.websocket import send_agent_monitor
from integrations.video import is_video_configured, generate_video, get_video_config
from integrations.image import is_image_configured, generate_image, is_image_demo_mode
from config import RENDERS_DIR, ASSETS_DIR, project_renders_dir, project_assets_dir
from models import ProductionStage, STAGE_AGENT_MAP



async def _plan_shots_with_llm(
    project_id: str, episode: dict, shots: list[dict],
    character_assets: list[dict], series_type: str = "live-action"
) -> list[dict]:
    """Use LLM to plan visual prompts and character selection for each shot.

    Returns list of dicts with keys: shot_id, visual_prompt, characters, camera_direction
    """
    from integrations.llm import call_llm, is_llm_configured

    if not is_llm_configured():
        # Fallback: use existing descriptions
        return [_default_shot_plan(s) for s in shots]

    # Build character info for LLM
    char_info = []
    for ca in character_assets:
        char_info.append({
            "name": ca.get("name", ""),
            "description": ca.get("description", ""),
            "anchor": ca.get("anchor_prompt", ""),
        })

    # Get script context
    import json
    import re
    script_json = episode.get("script_json")
    script = json.loads(script_json) if isinstance(script_json, str) else (script_json or {})
    scenes = script.get("scenes", [])

    shots_info = []
    for s in shots:
        shots_info.append({
            "shot_id": s["shot_id"],
            "shot_number": s["shot_number"],
            "description": s.get("description", ""),
            "camera_movement": s.get("camera_movement", ""),
            "duration": s.get("duration", ""),
        })

    style_instruction = ""
    if series_type == "animation":
        style_instruction = "\n\n重要风格要求：这是一部动画漫剧，所有 visual_prompt 必须使用动漫/插画面风描述，包含关键词：anime style, cel-shaded, vibrant colors, illustration。不要使用 photorealistic、realistic 等真人风关键词。"
    else:
        style_instruction = "\n\n重要风格要求：这是一部真人短剧，所有 visual_prompt 必须使用写实电影风格描述，包含关键词：photorealistic, cinematic lighting, natural。不要使用 anime、illustration、cartoon 等动画风关键词。"

    prompt = f"""你是一个专业的AI短剧视觉导演。根据以下分镜信息和角色设定，为每个镜头生成详细的视觉提示词。{style_instruction}

角色设定：
{json.dumps(char_info, ensure_ascii=False, indent=2)}

本集场景：
{json.dumps(scenes[:5], ensure_ascii=False, indent=2)[:1500]}

分镜列表：
{json.dumps(shots_info, ensure_ascii=False, indent=2)}

请为每个镜头生成：
1. visual_prompt: 详细画面描述（英文），包含场景、人物位置/动作/表情、光线、氛围、构图。用于AI图片生成。
2. characters: 本镜头出现的角色名称列表（从角色设定中选择）
3. camera_direction: 镜头运动指导（如：缓慢推进、跟随镜头、固定机位、俯拍等）

要求：
- visual_prompt必须是英文，便于AI图像模型理解
- 每个镜头描述要具体可视觉化，包含人物外观细节
- 保持与前后镜头的视觉连贯性

【输出格式 - 必须严格遵守】
直接输出纯 JSON 数组，禁止使用 markdown 代码块包裹，禁止输出任何其他内容。

正确示例：
[{{\"shot_id\": \"xxx\", \"visual_prompt\": \"A young woman in business attire...\", \"characters\": [\"角色名1\"], \"camera_direction\": \"slow push in\"}}]

错误示例（禁止）：
```json
[...]
```"""

    system_msg = {"role": "system", "content": "你是一个专业的AI短剧视觉导演。\n\n【输出规则 - 绝对遵守】\n1. 直接输出纯 JSON 数组，不要包裹在 markdown 代码块中。\n2. 禁止输出任何 JSON 以外的内容。\n3. 禁止使用 \\`\\`\\`json \\`\\`\\` 包裹。"}

    try:
        response = await call_llm(
            [system_msg, {"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=2048,
        )

        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            plans = json.loads(json_match.group())
            # Validate structure
            if isinstance(plans, list) and len(plans) == len(shots):
                return plans

        # Fallback on parse failure
        return [_default_shot_plan(s) for s in shots]
    except Exception as e:
        print(f"Shot planning LLM failed: {e}")
        return [_default_shot_plan(s) for s in shots]


def _default_shot_plan(shot: dict) -> dict:
    return {
        "shot_id": shot["shot_id"],
        "visual_prompt": shot.get("description", ""),
        "characters": [],
        "camera_direction": shot.get("camera_movement", ""),
    }

async def shots_node(state: ProductionState) -> dict:
    """Generate first-frame images and videos for all shots in an episode.

    This is Stage 4 of the production pipeline.
    For each shot:
    1. Build a first-frame prompt from shot description + character assets
    2. Generate a first-frame image
    3. Use that image as reference for video generation
    """
    project_id = state["project_id"]
    current_episode_index = state.get("current_episode_index", 0)
    agent_id = STAGE_AGENT_MAP[ProductionStage.SHOTS_GENERATING]

    # Check precondition
    if not is_stage_completed(project_id, ProductionStage.ASSETS_COMPLETED.value):
        raise RuntimeError("Assets must be completed before shot video generation")

    # Get current episode
    episodes = project_repo.get_episodes(project_id)
    if current_episode_index >= len(episodes):
        return {"current_stage": ProductionStage.SHOTS_COMPLETED.value}

    ep = episodes[current_episode_index]
    episode_id = ep["episode_id"]

    update_project_stage(project_id, ProductionStage.SHOTS_GENERATING.value, "in_progress")

    shots = get_shots_by_episode(episode_id)
    agent_repo.update_agent_state(
        project_id, agent_id,
        status="working",
        current_task=f"生成第{ep['episode_number']}集镜头视频",
        completed_tasks=0,
        total_tasks=max(1, len(shots)),
    )

    add_production_event(
        project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
        "stage_started", f"开始生成第{ep['episode_number']}集镜头",
        "正在为每个分镜生成首帧图片和视频...", episode_id=episode_id
    )

    project_repo.update_episode(episode_id, status="rendering", progress=70)

    # Check video mode
    video_mode = get_setting("video_generation_mode") or "manual"

    if video_mode == "manual":
        add_production_event(
            project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
            "manual_mode", "手动模式", "视频生成模式为手动，请手动触发镜头生成",
            episode_id=episode_id
        )
        project_repo.update_episode(episode_id, status="rendering", progress=72)

        human_input = interrupt({
            "type": "manual_video",
            "message": "Manual video generation mode",
            "episode_id": episode_id,
            "episode_number": ep["episode_number"],
            "shots": [
                {"shot_id": s["shot_id"], "shot_number": s["shot_number"], "description": s.get("description", "")}
                for s in shots
            ],
        })

        if human_input.get("skip"):
            agent_repo.update_agent_state(project_id, agent_id, status="idle", current_task=None)
            return {
                "current_stage": ProductionStage.SHOTS_COMPLETED.value,
                "current_episode_index": current_episode_index + 1,
            }

    # Load character assets
    character_assets = get_assets(project_id, type="character")

    # Determine series type
    proj = project_repo.get_project(project_id)
    proj_config = proj.get("config", {}) if proj else {}
    if isinstance(proj_config, str):
        import json as _json
        proj_config = _json.loads(proj_config)
    series_type = state.get("series_type") or proj_config.get("series_type", "live-action")

    # Plan all shots with LLM
    shot_plans = await _plan_shots_with_llm(project_id, ep, shots, character_assets, series_type)
    plan_by_id = {p["shot_id"]: p for p in shot_plans}

    # Auto mode: generate first frames then videos
    shots_completed = 0
    image_configured = is_image_configured() or is_image_demo_mode()
    video_ok = is_video_configured()

    for idx, shot in enumerate(shots, start=1):
        shot_id = shot["shot_id"]
        description = shot.get("description", "")

        # Use LLM-planned visual prompt
        plan = plan_by_id.get(shot_id, _default_shot_plan(shot))
        frame_prompt = plan.get("visual_prompt", description)
        camera_dir = plan.get("camera_direction", shot.get("camera_movement", ""))
        appearing_chars = plan.get("characters", [])

        # Find character sheet images for appearing characters
        char_sheet_paths = []
        for ca in character_assets:
            if ca.get("name") in appearing_chars and ca.get("image_path"):
                real_path = str(ASSETS_DIR / ca["image_path"].replace("/assets/", ""))
                from pathlib import Path
                if Path(real_path).exists():
                    char_sheet_paths.append(real_path)
        char_sheet_paths = char_sheet_paths[:3]  # Limit to avoid overly large prompts

        first_frame_path = None

        # Step 1: Generate first-frame image
        if image_configured:
            add_production_event(
                project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                "prompt_issued", f"镜头 {shot['shot_number']} 首帧图片",
                f"开始生成第{ep['episode_number']}集镜头 {shot['shot_number']} 首帧",
                episode_id=episode_id, shot_id=shot_id,
                payload={"prompt": frame_prompt[:100]}
            )

            try:
                frame_output = str(project_renders_dir(project_id) / f"{shot_id}_frame.png")

                await generate_image(frame_prompt, frame_output, reference_images=char_sheet_paths if char_sheet_paths else None, aspect_ratio="16:9")

                first_frame_path = f"/renders/{project_id}/{shot_id}_frame.png"
                update_shot(shot_id, first_frame_path=first_frame_path)

                add_production_event(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    "output_captured", f"镜头 {shot['shot_number']} 首帧完成", "首帧图片已生成",
                    episode_id=episode_id, shot_id=shot_id,
                    payload={"output": first_frame_path}
                )
            except Exception as e:
                add_production_event(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    "first_frame_failed", f"镜头 {shot['shot_number']} 首帧失败", str(e),
                    episode_id=episode_id, shot_id=shot_id,
                )

        # Step 2: Generate video using first frame as reference
        if video_ok:
            add_production_event(
                project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                "prompt_issued", f"镜头 {shot['shot_number']} 视频生成",
                f"开始用首帧生成第{ep['episode_number']}集镜头 {shot['shot_number']} 视频",
                episode_id=episode_id, shot_id=shot_id,
                payload={"prompt": description[:100], "has_first_frame": first_frame_path is not None}
            )

            try:
                video_output = str(project_renders_dir(project_id) / f"{shot_id}.mp4")
                video_config = get_video_config()
                add_shot_trace(
                    shot_id, project_id, "video_generation", agent_id=agent_id,
                    prompt_summary=description[:100],
                    prompt_hash=hashlib.md5(description.encode()).hexdigest(),
                    provider_name=video_config["provider"], model_name=video_config["model"],
                )

                # Pass first frame image path as reference
                real_frame_path = None
                if first_frame_path:
                    real_frame_path = str(RENDERS_DIR / first_frame_path.replace("/renders/", ""))

                video_prompt = f"{frame_prompt}, {camera_dir}" if camera_dir else frame_prompt
                await generate_video(
                    video_prompt, video_output,
                    reference_image=real_frame_path,
                    duration_seconds=3, aspect_ratio=video_config.get("aspect_ratio", "16:9")
                )

                update_shot(shot_id, status="completed", video_url=f"/renders/{project_id}/{shot_id}.mp4")
                add_shot_trace(
                    shot_id, project_id, "video_completed", agent_id=agent_id,
                    output_path=video_output, provider_name=video_config["provider"],
                    model_name=video_config["model"],
                )
                shots_completed += 1

                add_production_event(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    "output_captured", f"镜头 {shot['shot_number']} 输出", "视频已生成",
                    episode_id=episode_id, shot_id=shot_id,
                    payload={"output": f"/renders/{project_id}/{shot_id}.mp4"}
                )
                add_production_event(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    "shot_completed", f"镜头 {shot['shot_number']} 完成", "视频已生成",
                    episode_id=episode_id, shot_id=shot_id
                )
            except Exception as e:
                update_shot(shot_id, status="failed")
                add_shot_trace(
                    shot_id, project_id, "video_failed", agent_id=agent_id, error_reason=str(e)
                )
        else:
            update_shot(shot_id, status="failed")
            add_shot_trace(
                shot_id, project_id, "video_failed", agent_id=agent_id,
                error_reason="Video provider not configured"
            )

        # Update progress
        episode_progress = 72 + int((shots_completed / max(1, len(shots))) * 13)
        project_repo.update_episode(episode_id, status="rendering", progress=episode_progress)
        agent_repo.update_agent_state(
            project_id, agent_id, status="working",
            current_task=f"镜头视频：第{ep['episode_number']}集 / 镜头 {shot['shot_number']}",
            completed_tasks=shots_completed, total_tasks=max(1, len(shots)),
            progress=int(idx / max(1, len(shots)) * 100)
        )

    # Check if all shots completed
    if shots_completed == len(shots):
        update_project_stage(project_id, ProductionStage.SHOTS_GENERATING.value, "completed")
        update_project_stage(project_id, ProductionStage.SHOTS_COMPLETED.value, "completed")
        add_production_event(
            project_id, agent_id, ProductionStage.SHOTS_COMPLETED.value,
            "stage_completed", f"第{ep['episode_number']}集镜头完成",
            f"已生成 {shots_completed} 个镜头视频", episode_id=episode_id
        )

    agent_repo.update_agent_state(project_id, agent_id, status="idle", current_task=None)

    return {
        "current_stage": ProductionStage.SHOTS_COMPLETED.value,
    }
