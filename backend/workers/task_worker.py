"""
Production worker - processes tasks from the task queue.

This worker enforces a strict linear pipeline:
  requirements_confirmed → script → format → assets → shots → episode_compose → project_compose

Each stage:
  1. Checks preconditions (previous stage must be completed)
  2. Performs real work
  3. Writes real output to database
  4. Creates next stage task(s)
  5. Emits structured production events
"""

import asyncio
import json
import hashlib
import re
from datetime import datetime
from pathlib import Path

from repositories import task_repo, project_repo, agent_repo
from repositories.shot_repo import (
    create_shot, update_shot, add_shot_trace, get_shots_by_episode,
)
from repositories.production_event_repo import (
    add_production_event,
    init_project_stages,
    update_project_stage,
    get_project_stages,
    is_stage_completed,
    get_current_stage,
    create_asset,
    update_asset,
    get_assets,
)
from routers.websocket import (
    send_progress_update, send_agent_update, send_episode_completed,
    send_project_completed, send_agent_monitor,
    send_stage_update,

)
from integrations.llm import is_llm_configured, stream_llm, call_llm
from integrations.video import is_video_configured, generate_video, get_video_config, parse_duration_seconds
from integrations.image import is_image_configured, generate_image, is_image_demo_mode
from integrations.ffmpeg import is_ffmpeg_available, concatenate_videos
from config import RENDERS_DIR, OUTPUTS_DIR, project_assets_dir, project_renders_dir
from repositories.settings_repo import get_setting
from storage.db import get_connection

from prompt_reference import HOT_HOOK_REFERENCE, build_character_sheet_prompt, build_shot_dual_prompt_request, build_default_dual_prompts

from models import (
    ProductionStage,
    STAGE_AGENT_MAP,
)


_worker_running = False


async def start_worker():
    """Start the background task worker."""
    global _worker_running
    if _worker_running:
        return
    _worker_running = True

    # On startup: reset any tasks stuck in "running" from a previous crash
    projects = project_repo.get_all_projects()
    for p in projects:
        task_repo.reset_running_tasks(p["project_id"])
    # Also reset any stuck agent states
    conn = get_connection()
    conn.execute("UPDATE agent_states SET status = 'idle', current_task = NULL WHERE status = 'working'")
    conn.commit()
    conn.close()
    print("[Worker] Startup cleanup: reset all running tasks and agent states")

    while _worker_running:
        try:
            await _process_one_task()
        except Exception as e:
            print(f"Worker error: {e}")
        await asyncio.sleep(2)


def stop_worker():
    global _worker_running
    _worker_running = False


async def _process_one_task():
    """Find and process one pending task across all active projects."""
    projects = project_repo.get_all_projects()
    for p in projects:
        if p["status"] != "in_progress":
            continue

        pending = task_repo.get_pending_tasks(p["project_id"])
        if not pending:
            continue

        task = pending[0]
        print(f"[Worker] PICKED task={task['task_id']} type={task['task_type']} project={p['project_id']} (pending={len(pending)})")
        await _execute_task(task)
        return  # Process one task per cycle

    # Check if any in-progress projects should be completed
    for p in projects:
        if p["status"] == "in_progress":
            episodes = project_repo.get_episodes(p["project_id"])
            if episodes and all(ep["status"] == "completed" for ep in episodes):
                # Queue project compose if not already queued
                tasks = task_repo.get_tasks_by_project(p["project_id"])
                has_compose = any(t["task_type"] == "project_compose" and t["status"] in ("pending", "running") for t in tasks)
                if not has_compose:
                    task_repo.create_task(
                        f"task_{p['project_id']}_compose_final",
                        p["project_id"],
                        "project_compose",
                    )


async def _execute_task(task: dict):
    """Execute a single task based on its type."""
    project_id = task["project_id"]
    task_type = task["task_type"]
    task_id = task["task_id"]

    print(f"[Worker] EXECUTING task={task_id} type={task_type} project={project_id} ep={task.get('episode_id')} shot={task.get('shot_id')}")
    task_repo.update_task(task["task_id"], status="running", started_at=datetime.utcnow().isoformat())

    try:
        if task_type == "project_script":
            await _execute_project_script(project_id, task)
        elif task_type == "project_format":
            await _execute_project_format(project_id, task)
        elif task_type == "project_assets":
            await _execute_project_assets(project_id, task)
        elif task_type == "episode_shot_video":
            await _execute_episode_shot_video(project_id, task)
        elif task_type == "episode_compose":
            await _execute_episode_compose(project_id, task)
        elif task_type == "project_compose":
            await _execute_project_compose(project_id, task)
        elif task_type == "episode_run":
            # Legacy: queue the new linear chain instead
            await _migrate_episode_run_to_linear(project_id, task)
        elif task_type == "shot_video":
            # Legacy: redirect to episode_shot_video
            await _execute_shot_video_legacy(project_id, task)
        else:
            task_repo.update_task(task["task_id"], status="completed")

    except Exception as e:
        retry_count = (task.get("retry_count") or 0) + 1
        task_repo.update_task(
            task["task_id"],
            status="pending",
            error_message=f"[retry {retry_count}] {e}",
            retry_count=retry_count,
        )
        agent_repo.add_agent_log(project_id, "agent_director", "warning",
                                  f"Task {task_type} failed (retry {retry_count}), re-queuing: {e}")
        # Backoff: wait longer for repeated failures
        await asyncio.sleep(min(10 * retry_count, 120))


# === Stage 1: Project Script Generation ===

async def _execute_project_script(project_id: str, task: dict):
    """Generate complete scripts for all episodes."""
    if not is_stage_completed(project_id, ProductionStage.REQUIREMENTS_CONFIRMED.value):
        init_project_stages(project_id)
        update_project_stage(project_id, ProductionStage.REQUIREMENTS_CONFIRMED.value, "completed")

    update_project_stage(project_id, ProductionStage.SCRIPT_GENERATING.value, "in_progress")
    await _emit_stage_status(
        project_id, ProductionStage.SCRIPT_GENERATING.value, "in_progress", "开始生成剧本"
    )

    agent_id = STAGE_AGENT_MAP[ProductionStage.SCRIPT_GENERATING]
    project = project_repo.get_project(project_id)
    characters = project_repo.get_characters(project_id)
    episodes = project_repo.get_episodes(project_id)
    config = project.get("config", {})

    await _set_agent_status(
        project_id,
        agent_id,
        status="working",
        current_task="生成完整剧本",
        completed_tasks=0,
        total_tasks=len(episodes),
    )

    add_production_event(
        project_id, agent_id, ProductionStage.SCRIPT_GENERATING.value,
        "stage_started", "开始生成剧本", "正在为所有剧集逐集生成完整剧本..."
    )

    char_desc = "\n".join(
        f"- {c['name']}({c['role']}): {c['description']}" for c in characters
    )

    # Build per-episode detail lookup from outline
    episodes_detail = config.get("episodes_detail", [])
    detail_by_ep = {d.get("episode"): d for d in episodes_detail if isinstance(d, dict)}

    # Accumulate previous episode summaries
    previous_summaries: list[str] = []

    for idx, ep in enumerate(episodes, start=1):
        episode_id = ep["episode_id"]

        # Skip episodes that already have a valid script (e.g., from a previous run)
        existing_script = ep.get("script_json")
        if existing_script:
            try:
                parsed = json.loads(existing_script) if isinstance(existing_script, str) else existing_script
                if isinstance(parsed, dict) and "scenes" in parsed:
                    scenes_desc = "; ".join(
                        f"场景{s.get('scene_number', '?')}({s.get('location', '')}): {s.get('description', '')[:60]}"
                        for s in parsed.get("scenes", [])
                    )
                    previous_summaries.append(f"第{ep['episode_number']}集《{ep['title']}》: {scenes_desc}")
                    project_repo.update_episode(episode_id, status="scripting", progress=25)
                    await _push_progress_update(project_id, episode_id)
                    await _set_agent_status(
                        project_id, agent_id, status="working",
                        current_task=f"跳过已有剧本：第{ep['episode_number']}集",
                        completed_tasks=idx, total_tasks=len(episodes), progress=int(idx / len(episodes) * 100)
                    )
                    continue
            except (json.JSONDecodeError, TypeError):
                pass  # Invalid script, regenerate

        project_repo.update_episode(episode_id, status="scripting", progress=10)
        await _push_progress_update(project_id, episode_id)

        # Build previous episodes context
        prev_context = ""
        if previous_summaries:
            prev_context = f"""前情提要（第1-{idx-1}集概要）：
{chr(10).join(previous_summaries)}

"""

        # Get current episode outline detail (hook, escalation, cliffhanger, scenes)
        ep_detail = detail_by_ep.get(ep['episode_number'], {})
        outline_section = ""
        if ep_detail:
            outline_section = f"""
本集大纲概要：
- 开场钩子：{ep_detail.get('hook', '')}
- 中段升级：{ep_detail.get('escalation', '')}
- 结尾悬念：{ep_detail.get('cliffhanger', '')}
- 关键场景：{ep_detail.get('scenes', '')}

"""

        prompt = f"""{prev_context}请为以下 AI 短剧编写第{ep['episode_number']}集的完整剧本。

剧名: {project['title']}
故事梗概: {config.get('synopsis', '')}
类型: {config.get('genre', '都市爱情')}
风格: {config.get('style', '轻松幽默')}
总集数: {config.get('episode_count', '?')}集
单集时长: {config.get('episode_duration', '3分钟')}

主要角色:
{char_desc}

集数标题: {ep['title']}
{outline_section}
{HOT_HOOK_REFERENCE}

写作补充：
- 学习这些爆点钩子的起题方式、冲突密度、身份反差和反转力度，把同样的抓人感落到本集开场、推进和结尾，但不要直接照抄原题或原情节。
- 本集至少要有一个足够抓人的开场钩子、一个中段升级点、一个结尾反转或悬念。

要求：
1. 这是 AI 短剧，场景集中、节奏快、每场都要有推进。
2. 角色行动与对白要清晰，便于后续转分镜和视频生成。
3. **开场必须使用倒叙手法**：第一个场景必须是全剧最炸裂、最有悬念、最抓人的高潮片段（如：对峙、揭秘、崩塌瞬间），然后再通过倒叙回到事件起点，逐步揭示因果。绝对不能从平淡的日常生活开场。
4. 直接返回 JSON。

JSON 包含 scenes 数组，每个 scene 包含:
- scene_number: 场景编号
- location: 场景地点
- time_of_day: 时间
- description: 场景描述
- dialogues: 对话数组 [{{character, line, emotion}}]
- actions: 动作描述数组"""

        script = {}
        if is_llm_configured():
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    await _emit_agent_prompt(
                        project_id, agent_id, ProductionStage.SCRIPT_GENERATING.value,
                        prompt, f"第{ep['episode_number']}集剧本提示词" + (f" (重试{attempt})" if attempt > 1 else ""),
                        f"开始为《{ep['title']}》生成剧本", episode_id=episode_id
                    )

                    chunks = []
                    async for chunk in stream_llm(
                        [
                            {"role": "system", "content": "你是一个专业的 AI 短剧编剧。你擅长高钩子、强反转、强情绪推进的短剧写法。只返回 JSON 格式剧本。"},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.8,
                        max_tokens=4096,
                    ):
                        chunks.append(chunk)
                        await send_agent_monitor(
                            project_id, agent_id,
                            stage=ProductionStage.SCRIPT_GENERATING.value,
                            output_chunk=chunk,
                            episode_id=episode_id,
                            event_type="output_chunk",
                        )

                    response = "".join(chunks)
                    await _emit_agent_output(
                        project_id, agent_id, ProductionStage.SCRIPT_GENERATING.value,
                        response, f"第{ep['episode_number']}集剧本输出",
                        f"已获取《{ep['title']}》剧本输出", episode_id=episode_id
                    )

                    json_match = re.search(r'\{[\s\S]*\}', response)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        if isinstance(parsed, dict) and "scenes" in parsed:
                            script = parsed
                            break
                    if attempt < max_retries:
                        prompt = prompt + "\n\n注意：上一次返回的内容不是有效的JSON，请只返回纯JSON，不要包含任何其他文字。"
                except Exception as e:
                    agent_repo.add_agent_log(project_id, agent_id, "error", f"LLM调用失败: {e}")
                    if attempt < max_retries:
                        prompt = prompt + "\n\n注意：上一次返回的内容不是有效的JSON，请只返回纯JSON，不要包含任何其他文字。"

        if not script or "scenes" not in script:
            raise RuntimeError(f"第{ep['episode_number']}集《{ep['title']}》剧本生成失败：LLM未返回有效JSON，请重试")

        project_repo.update_episode(episode_id, script=script, status="scripting", progress=25)
        await _push_progress_update(project_id, episode_id)
        await _set_agent_status(
            project_id, agent_id, status="working",
            current_task=f"剧本生成：第{ep['episode_number']}集",
            completed_tasks=idx, total_tasks=len(episodes), progress=int(idx / len(episodes) * 100)
        )

        add_production_event(
            project_id, agent_id, ProductionStage.SCRIPT_GENERATING.value,
            "episode_script_completed", f"第{ep['episode_number']}集剧本完成",
            f"已完成《{ep['title']}》剧本编写",
            episode_id=episode_id,
            payload={"scene_count": len(script.get("scenes", []))}
        )

        # Build summary of this episode for context of subsequent episodes
        scenes_desc = "; ".join(
            f"场景{s.get('scene_number', '?')}({s.get('location', '')}): {s.get('description', '')[:60]}"
            for s in script.get("scenes", [])
        )
        previous_summaries.append(f"第{ep['episode_number']}集《{ep['title']}》: {scenes_desc}")

    update_project_stage(project_id, ProductionStage.SCRIPT_GENERATING.value, "completed")
    update_project_stage(project_id, ProductionStage.SCRIPT_COMPLETED.value, "completed")
    await _emit_stage_status(
        project_id, ProductionStage.SCRIPT_COMPLETED.value, "completed", "剧本生成完成"
    )

    add_production_event(
        project_id, agent_id, ProductionStage.SCRIPT_COMPLETED.value,
        "stage_completed", "剧本生成完成", f"已完成全部 {len(episodes)} 集剧本"
    )

    await _set_agent_status(
        project_id, agent_id, status="idle", current_task=None,
        completed_tasks=len(episodes), total_tasks=len(episodes), progress=100
    )

    task_repo.create_task(f"task_{project_id}_format", project_id, "project_format")
    task_repo.update_task(
        task["task_id"],
        status="completed",
        output_json={"episodes": len(episodes)},
        completed_at=datetime.utcnow().isoformat(),
    )


# === Stage 2: Project Format (Storyboard) ===

async def _execute_project_format(project_id: str, task: dict):
    """Format scripts into structured storyboards with shot lists."""
    if not is_stage_completed(project_id, ProductionStage.SCRIPT_COMPLETED.value):
        raise RuntimeError("Script must be completed before formatting")

    update_project_stage(project_id, ProductionStage.FORMAT_GENERATING.value, "in_progress")
    await _emit_stage_status(
        project_id, ProductionStage.FORMAT_GENERATING.value, "in_progress", "开始格式化分镜"
    )

    agent_id = STAGE_AGENT_MAP[ProductionStage.FORMAT_GENERATING]
    episodes = project_repo.get_episodes(project_id)
    total_shots = 0

    await _set_agent_status(
        project_id, agent_id, status="working", current_task="格式化分镜",
        completed_tasks=0, total_tasks=len(episodes)
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
        await _push_progress_update(project_id, episode_id)

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
        await _push_progress_update(project_id, episode_id)

        for sb in storyboard:
            shot_id = f"{episode_id}_shot_{sb['shot_number']}"
            create_shot(
                shot_id, episode_id, project_id, sb["shot_number"],
                sb.get("description", ""), sb.get("camera_movement", ""), sb.get("duration", "")
            )
            total_shots += 1

        await _set_agent_status(
            project_id, agent_id, status="working",
            current_task=f"分镜格式化：第{ep['episode_number']}集",
            completed_tasks=idx, total_tasks=len(episodes), progress=int(idx / len(episodes) * 100)
        )

        add_production_event(
            project_id, agent_id, ProductionStage.FORMAT_GENERATING.value,
            "episode_format_completed", f"第{ep['episode_number']}集分镜完成",
            f"已生成 {len(storyboard)} 个镜头",
            episode_id=episode_id, payload={"shot_count": len(storyboard)}
        )

    update_project_stage(project_id, ProductionStage.FORMAT_GENERATING.value, "completed")
    update_project_stage(project_id, ProductionStage.FORMAT_COMPLETED.value, "completed")
    await _emit_stage_status(
        project_id, ProductionStage.FORMAT_COMPLETED.value, "completed", "分镜格式化完成"
    )

    add_production_event(
        project_id, agent_id, ProductionStage.FORMAT_COMPLETED.value,
        "stage_completed", "分镜格式化完成", f"已创建 {total_shots} 个镜头"
    )

    await _set_agent_status(
        project_id, agent_id, status="idle", current_task=None,
        completed_tasks=len(episodes), total_tasks=len(episodes), progress=100
    )

    task_repo.create_task(f"task_{project_id}_assets", project_id, "project_assets")
    task_repo.update_task(
        task["task_id"],
        status="completed",
        output_json={"total_shots": total_shots},
        completed_at=datetime.utcnow().isoformat(),
    )

# === Stage 3: Project Assets ===

async def _execute_project_assets(project_id: str, task: dict):
    """Generate character and scene assets, then queue the first episode render."""
    if not is_stage_completed(project_id, ProductionStage.FORMAT_COMPLETED.value):
        raise RuntimeError("Format must be completed before asset generation")

    update_project_stage(project_id, ProductionStage.ASSETS_GENERATING.value, "in_progress")
    await _emit_stage_status(
        project_id, ProductionStage.ASSETS_GENERATING.value, "in_progress", "开始生成视觉资产"
    )

    agent_id = STAGE_AGENT_MAP[ProductionStage.ASSETS_GENERATING]
    characters = project_repo.get_characters(project_id)
    episodes = project_repo.get_episodes(project_id)
    project = project_repo.get_project(project_id)
    config = project.get("config", {}) if project else {}
    series_type = config.get("series_type", "live-action")
    await _set_agent_status(
        project_id, agent_id, status="working", current_task="生成视觉资产",
        completed_tasks=0, total_tasks=max(1, len(characters))
    )

    add_production_event(
        project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
        "stage_started", "开始生成视觉资产", "正在为角色和场景生成视觉资产..."
    )

    for ep in episodes:
        project_repo.update_episode(ep["episode_id"], status="asset_generating", progress=55)
    await _push_progress_update(project_id)

    assets_by_name = {a["name"]: a for a in get_assets(project_id, type="character")}

    print(f"[Assets] project={project_id} characters={len(characters)} existing_assets={len(assets_by_name)} image_configured={is_image_configured()} demo={is_image_demo_mode()}")

    for i, char in enumerate(characters, start=1):
        asset_id = f"{project_id}_char_{i:03d}"
        name, role, desc = char["name"], char.get("role", "角色"), char.get("description", "")
        gender = char.get("visual_assets", {}).get("gender")
        prompt = build_character_sheet_prompt(name, role, desc, series_type, char.get("age"), gender)
        existing = assets_by_name.get(char["name"])
        if existing and existing.get("image_path"):
            print(f"[Assets] SKIP {name} (already has image)")
            continue
        print(f"[Assets] generating character {i}/{len(characters)}: {name} (asset_id={asset_id})")
        await _emit_agent_prompt(
            project_id, agent_id, ProductionStage.ASSETS_GENERATING.value, prompt,
            f"角色设定图提示词：{char['name']}", f"开始为角色 {char['name']} 生成角色设定图"
        )
        create_asset(
            asset_id, project_id, "character", char["name"], char["description"],
            prompt=prompt, anchor_prompt=f"{name}, {role}, character design reference sheet, face closeup + full-body front/side/back views, pure white background, {'anime' if series_type == 'animation' else 'photorealistic'}"
        )

        if is_image_configured() or is_image_demo_mode():
            try:
                output_path = str(project_assets_dir(project_id) / f"{asset_id}.png")
                print(f"[Assets] calling generate_image for {name} -> {output_path}")
                await generate_image(prompt, output_path, aspect_ratio="2:1")
                update_asset(asset_id, image_path=f"/assets/{project_id}/{asset_id}.png")
                print(f"[Assets] SUCCESS {name} saved to /assets/{project_id}/{asset_id}.png")
            except Exception as e:
                print(f"[Assets] FAILED {name}: {e}")
                agent_repo.add_agent_log(project_id, agent_id, "warning",
                                         f"Character sheet generation failed for {char['name']}: {e}")
        else:
            print(f"[Assets] SKIP {name} (image not configured, not demo mode)")

        await _emit_agent_output(
            project_id, agent_id, ProductionStage.ASSETS_GENERATING.value,
            f"角色资产已锁定：{char['name']}", f"角色资产完成：{char['name']}",
            "已锁定角色视觉锚点", final=True
        )
        await _set_agent_status(
            project_id, agent_id, status="working",
            current_task=f"资产生成：角色 {char['name']}",
            completed_tasks=i, total_tasks=max(1, len(characters))
        )

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

    print(f"[Assets] generating {len(scene_names)} scene images...")
    for i, scene_name in enumerate(scene_names, start=1):
        asset_id = f"{project_id}_scene_{i:03d}"
        if series_type == "animation":
            scene_prompt = f"{scene_name}, anime style establishing shot, vibrant, cel-shaded, wide angle, cinematic composition, illustration"
        else:
            scene_prompt = f"{scene_name}, establishing shot, photorealistic, cinematic, natural lighting, high quality, wide angle"
        create_asset(
            asset_id, project_id, "scene", scene_name, f"场景: {scene_name}",
            prompt=scene_prompt
        )

        # Generate scene image
        if is_image_configured() or is_image_demo_mode():
            try:
                scene_output = str(project_assets_dir(project_id) / f"{asset_id}.png")
                print(f"[Assets] generating scene {i}/{len(scene_names)}: {scene_name}")
                await generate_image(scene_prompt, scene_output, aspect_ratio=get_setting("video_aspect_ratio", "16:9"))
                update_asset(asset_id, image_path=f"/assets/{project_id}/{asset_id}.png")
                print(f"[Assets] scene OK: {scene_name}")
            except Exception as e:
                print(f"[Assets] scene FAILED {scene_name}: {e}")
                agent_repo.add_agent_log(project_id, agent_id, "warning",
                                         f"Scene image generation failed for {scene_name}: {e}")

    for ep in episodes:
        project_repo.update_episode(ep["episode_id"], status="asset_generating", progress=60)
        await _push_progress_update(project_id, ep["episode_id"])

    update_project_stage(project_id, ProductionStage.ASSETS_GENERATING.value, "completed")
    update_project_stage(project_id, ProductionStage.ASSETS_COMPLETED.value, "completed")
    print(f"[Assets] DONE project={project_id} characters={len(characters)} scenes={len(scene_names)}")

    await _emit_stage_status(
        project_id, ProductionStage.ASSETS_COMPLETED.value, "completed", "视觉资产生成完成"
    )

    add_production_event(
        project_id, agent_id, ProductionStage.ASSETS_COMPLETED.value,
        "stage_completed", "视觉资产生成完成",
        f"已创建 {len(characters)} 个角色资产, {len(scene_names)} 个场景资产"
    )

    await _set_agent_status(
        project_id, agent_id, status="idle", current_task=None,
        completed_tasks=max(1, len(characters)), total_tasks=max(1, len(characters)), progress=100
    )

    _queue_next_episode_shot_task(project_id)
    task_repo.update_task(
        task["task_id"],
        status="completed",
        output_json={"characters": len(characters), "scenes": len(scene_names)},
        completed_at=datetime.utcnow().isoformat(),
    )


# === Stage 4: Episode Shot Video ===

async def _execute_episode_shot_video(project_id: str, task: dict):
    """Generate videos for all shots in an episode."""
    if not is_stage_completed(project_id, ProductionStage.ASSETS_COMPLETED.value):
        raise RuntimeError("Assets must be completed before shot video generation")

    episode_id = task["episode_id"]
    episode = project_repo.get_episode(episode_id)
    if not episode:
        raise RuntimeError(f"Episode {episode_id} not found")

    update_project_stage(project_id, ProductionStage.SHOTS_GENERATING.value, "in_progress")
    await _emit_stage_status(
        project_id, ProductionStage.SHOTS_GENERATING.value, "in_progress", f"开始生成第{episode['episode_number']}集镜头"
    )

    agent_id = STAGE_AGENT_MAP[ProductionStage.SHOTS_GENERATING]
    shots = get_shots_by_episode(episode_id)
    await _set_agent_status(
        project_id, agent_id, status="working",
        current_task=f"生成第{episode['episode_number']}集镜头视频",
        completed_tasks=0, total_tasks=max(1, len(shots))
    )

    add_production_event(
        project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
        "stage_started", f"开始生成第{episode['episode_number']}集镜头",
        "正在为每个分镜逐个生成视频...", episode_id=episode_id
    )

    project_repo.update_episode(episode_id, status="rendering", progress=70)
    await _push_progress_update(project_id, episode_id)

    shots_completed = 0
    video_mode = get_setting("video_generation_mode") or "manual"

    # Determine series type
    proj = project_repo.get_project(project_id)
    proj_config = json.loads(proj.get("config_json", "{}")) if proj and isinstance(proj.get("config_json"), str) else (proj.get("config", {}) if proj else {})
    series_type = proj_config.get("series_type", "live-action")

    print(f"[Worker] Episode shot video: project={project_id} episode={episode_id} mode={video_mode} shots={len(shots)} series={series_type}")

    if video_mode == "manual":
        # In manual mode: generate prompts + first-frame images, skip video generation
        add_production_event(
            project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
            "manual_mode", "半自动模式", "正在生成提示词和首帧图片，视频需手动触发",
            episode_id=episode_id
        )
        for idx, shot in enumerate(shots, start=1):
            await _generate_one_shot_video(project_id, episode, shot, agent_id, series_type, skip_video=True)
            episode_progress = 70 + int((idx / max(1, len(shots))) * 10)
            project_repo.update_episode(episode_id, status="rendering", progress=episode_progress)
            await _push_progress_update(project_id, episode_id)
            await _set_agent_status(
                project_id, agent_id, status="working",
                current_task=f"首帧图片：第{episode['episode_number']}集 / 镜头 {shot['shot_number']}",
                completed_tasks=idx, total_tasks=max(1, len(shots)),
                progress=int(idx / max(1, len(shots)) * 100)
            )

        update_project_stage(project_id, ProductionStage.SHOTS_GENERATING.value, "completed")
        update_project_stage(project_id, ProductionStage.SHOTS_COMPLETED.value, "completed")
        add_production_event(
            project_id, agent_id, ProductionStage.SHOTS_COMPLETED.value,
            "stage_completed", f"第{episode['episode_number']}集首帧完成",
            f"已生成 {len(shots)} 个首帧图片（视频需手动触发）", episode_id=episode_id
        )
        task_repo.create_task(f"task_{episode_id}_compose", project_id, "episode_compose", episode_id=episode_id)
        await _set_agent_status(project_id, agent_id, status="idle", current_task=None)
        task_repo.update_task(
            task["task_id"], status="completed",
            output_json={"mode": "manual", "shots": len(shots)}, completed_at=datetime.utcnow().isoformat()
        )
        _queue_next_episode_shot_task(project_id)
        return

    for idx, shot in enumerate(shots, start=1):
        completed = await _generate_one_shot_video(project_id, episode, shot, agent_id, series_type)
        if completed:
            shots_completed += 1

        episode_progress = 72 + int((shots_completed / max(1, len(shots))) * 13)
        project_repo.update_episode(episode_id, status="rendering", progress=episode_progress)
        await _push_progress_update(project_id, episode_id)
        await _set_agent_status(
            project_id, agent_id, status="working",
            current_task=f"镜头视频：第{episode['episode_number']}集 / 镜头 {shot['shot_number']}",
            completed_tasks=shots_completed, total_tasks=max(1, len(shots)),
            progress=int(idx / max(1, len(shots)) * 100)
        )


    if shots_completed == len(shots):
        update_project_stage(project_id, ProductionStage.SHOTS_GENERATING.value, "completed")
        update_project_stage(project_id, ProductionStage.SHOTS_COMPLETED.value, "completed")
        await _emit_stage_status(
            project_id, ProductionStage.SHOTS_COMPLETED.value, "completed", f"第{episode['episode_number']}集镜头完成"
        )
        add_production_event(
            project_id, agent_id, ProductionStage.SHOTS_COMPLETED.value,
            "stage_completed", f"第{episode['episode_number']}集镜头完成",
            f"已生成 {shots_completed} 个镜头视频", episode_id=episode_id
        )
        task_repo.create_task(f"task_{episode_id}_compose", project_id, "episode_compose", episode_id=episode_id)
    else:
        project_repo.update_episode(episode_id, status="rendering", progress=78)
        await _push_progress_update(project_id, episode_id)

    await _set_agent_status(project_id, agent_id, status="idle", current_task=None)
    task_repo.update_task(
        task["task_id"], status="completed",
        output_json={"shots_completed": shots_completed}, completed_at=datetime.utcnow().isoformat()
    )



async def _generate_one_shot_video(project_id: str, episode: dict, shot: dict, agent_id: str, series_type: str = "live-action", skip_video: bool = False) -> bool:
    episode_id = episode["episode_id"]
    shot_id = shot["shot_id"]
    description = shot.get("description", "")

    print(f"[ShotGen] START shot={shot_id} ep={episode['episode_number']} desc={description[:60]}...")
    update_shot(shot_id, status="running")

    # Step 0: Generate dual prompts with full script/character context
    storyboard_json = episode.get("storyboard_json")
    storyboard = json.loads(storyboard_json) if isinstance(storyboard_json, str) else (storyboard_json or [])
    sb_entry = next((s for s in storyboard if s.get("shot_number") == shot["shot_number"]), None)
    print(f"[ShotGen] storyboard entry: {'found' if sb_entry else 'MISSING'} for shot_number={shot.get('shot_number')}")

    script_json = episode.get("script_json")
    script = json.loads(script_json) if isinstance(script_json, str) else (script_json or {})
    scene_number = sb_entry.get("scene_number") if sb_entry else None
    scene = next((s for s in script.get("scenes", []) if s.get("scene_number") == scene_number), None) if scene_number else None
    print(f"[ShotGen] scene: {'found' if scene else 'MISSING'} for scene_number={scene_number}")

    # Identify appearing characters
    dialogues = sb_entry.get("dialogues", []) if sb_entry else []
    if not dialogues and scene:
        dialogues = scene.get("dialogues", [])
    mentioned_names = {d.get("character") for d in dialogues if d.get("character")}
    character_assets = get_assets(project_id, type="character")
    appearing_chars = []
    for ca in character_assets:
        name = ca.get("name", "")
        if name in mentioned_names or name in description:
            appearing_chars.append(ca)
    print(f"[ShotGen] appearing chars: {[c.get('name') for c in appearing_chars]} (mentioned={mentioned_names})")

    # Resolve character sheet paths
    char_sheet_paths = []
    for ca in appearing_chars:
        if ca.get("image_path"):
            real_path = str(project_assets_dir(project_id).parent / ca["image_path"].replace("/assets/", ""))
            if Path(real_path).exists():
                char_sheet_paths.append(real_path)
    print(f"[ShotGen] char sheet paths: {len(char_sheet_paths)} resolved")

    # Generate dual prompts via LLM
    image_prompt = description
    video_prompt = description
    if is_llm_configured():
        print(f"[ShotGen] calling LLM for dual prompts...")
        messages, ctx = build_shot_dual_prompt_request(
            shot=shot, storyboard_entry=sb_entry, scene=scene,
            appearing_characters=appearing_chars, series_type=series_type,
        )
        try:
            response = await asyncio.wait_for(
                call_llm(messages, temperature=0.4, max_tokens=1024),
                timeout=60.0,
            )
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                parsed = json.loads(json_match.group())
                image_prompt = parsed.get("image_prompt", description)
                video_prompt = parsed.get("video_prompt", description)
                print(f"[ShotGen] LLM prompts OK | img={len(image_prompt)} chars | vid={len(video_prompt)} chars")
            else:
                print(f"[ShotGen] LLM response no JSON match, using defaults")
        except (asyncio.TimeoutError, asyncio.CancelledError):
            print(f"[ShotGen] LLM timed out for dual prompts, using defaults")
            agent_repo.add_agent_log(project_id, agent_id, "warning",
                                     f"Shot {shot_id} prompt generation timed out (60s)")
            defaults = build_default_dual_prompts(shot, sb_entry)
            image_prompt = defaults["image_prompt"]
            video_prompt = defaults["video_prompt"]
        except Exception as e:
            print(f"[ShotGen] LLM failed: {e}")
            agent_repo.add_agent_log(project_id, agent_id, "warning",
                                     f"Shot {shot_id} prompt generation failed: {e}")
            defaults = build_default_dual_prompts(shot, sb_entry)
            image_prompt = defaults["image_prompt"]
            video_prompt = defaults["video_prompt"]
    else:
        print(f"[ShotGen] LLM not configured, using defaults")
        defaults = build_default_dual_prompts(shot, sb_entry)
        image_prompt = defaults["image_prompt"]
        video_prompt = defaults["video_prompt"]

    # Save prompts to DB
    update_shot(shot_id, image_prompt=image_prompt, video_prompt=video_prompt)

    await _emit_agent_prompt(
        project_id, agent_id, ProductionStage.SHOTS_GENERATING.value, image_prompt,
        f"镜头 {shot['shot_number']} 提示词",
        f"第{episode['episode_number']}集镜头 {shot['shot_number']} 提示词已生成",
        episode_id=episode_id, shot_id=shot_id
    )

    # Step 1: Generate first-frame image using image_prompt + character references
    first_frame_path = None
    if is_image_configured() or is_image_demo_mode():
        print(f"[ShotGen] generating first-frame image...")
        try:
            RENDERS_DIR.mkdir(parents=True, exist_ok=True)
            frame_output = str(project_renders_dir(project_id) / f"{shot_id}_frame.png")
            print(f"[ShotGen] image output: {frame_output} | aspect={get_setting('video_aspect_ratio', '16:9')} | refs={len(char_sheet_paths)}")
            await generate_image(
                image_prompt, frame_output,
                reference_images=char_sheet_paths if char_sheet_paths else None,
                aspect_ratio=get_setting("video_aspect_ratio", "16:9"),
            )
            first_frame_path = f"/renders/{project_id}/{shot_id}_frame.png"
            update_shot(shot_id, first_frame_path=first_frame_path)
            print(f"[ShotGen] first-frame OK: {first_frame_path}")
            add_production_event(
                project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                "first_frame_created", f"镜头 {shot['shot_number']} 首帧完成", "首帧图片已生成",
                episode_id=episode_id, shot_id=shot_id, payload={"first_frame_path": first_frame_path, "prompt": image_prompt[:100]}
            )
        except Exception as e:
            print(f"[ShotGen] first-frame FAILED: {e}")
            agent_repo.add_agent_log(project_id, agent_id, "warning",
                                     f"First-frame generation failed for shot {shot_id}: {e}")
    else:
        print(f"[ShotGen] image generation not configured, skipping first-frame")

    # Step 2: Generate video (skip in manual mode)
    if skip_video:
        print(f"[ShotGen] skip_video=True, skipping video generation")
        update_shot(shot_id, status="pending")  # Reset to pending for later manual trigger
        return False

    try:
        if is_video_configured():
            print(f"[ShotGen] generating video...")
            RENDERS_DIR.mkdir(parents=True, exist_ok=True)
            output_path = str(project_renders_dir(project_id) / f"{shot_id}.mp4")
            video_config = get_video_config()
            add_shot_trace(
                shot_id, project_id, "video_generation", agent_id=agent_id,
                prompt_summary=video_prompt[:100],
                prompt_hash=hashlib.md5(video_prompt.encode()).hexdigest(),
                provider_name=video_config["provider"], model_name=video_config["model"],
            )

            # Video reference: first-frame only (already contains characters)
            video_refs = []
            if first_frame_path:
                video_refs.append(str(RENDERS_DIR.parent / first_frame_path.lstrip("/")))

            print(f"[ShotGen] video refs: {len(video_refs)} (first-frame only) | provider={video_config['provider']} | aspect={video_config.get('aspect_ratio', '16:9')}")
            await generate_video(
                video_prompt, output_path,
                reference_images=video_refs if video_refs else None,
                duration_seconds=parse_duration_seconds(shot.get("duration")),
                aspect_ratio=video_config.get("aspect_ratio", "16:9"),
            )

            update_shot(shot_id, status="completed", video_url=f"/renders/{project_id}/{shot_id}.mp4")
            add_shot_trace(
                shot_id, project_id, "video_completed", agent_id=agent_id,
                output_path=output_path, provider_name=video_config["provider"], model_name=video_config["model"],
            )
            print(f"[ShotGen] video OK: /renders/{project_id}/{shot_id}.mp4")
            await _emit_agent_output(
                project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                f"镜头 {shot['shot_number']} 视频生成完成：/renders/{project_id}/{shot_id}.mp4",
                f"镜头 {shot['shot_number']} 输出", "视频已生成",
                episode_id=episode_id, shot_id=shot_id
            )
            add_production_event(
                project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                "shot_completed", f"镜头 {shot['shot_number']} 完成", "视频已生成",
                episode_id=episode_id, shot_id=shot_id,
                payload={
                    "image_prompt": image_prompt[:100],
                    "video_prompt": video_prompt[:100],
                    "first_frame_path": first_frame_path,
                    "video_url": f"/renders/{project_id}/{shot_id}.mp4",
                }
            )
            return True

        print(f"[ShotGen] video not configured, marking failed")
        update_shot(shot_id, status="failed")
        add_shot_trace(
            shot_id, project_id, "video_failed", agent_id=agent_id,
            error_reason="Video provider not configured"
        )
    except Exception as e:
        print(f"[ShotGen] video FAILED: {e}")
        update_shot(shot_id, status="failed")
        add_shot_trace(
            shot_id, project_id, "video_failed", agent_id=agent_id, error_reason=str(e)
        )
    return False

# === Stage 5: Episode Compose ===

async def _execute_episode_compose(project_id: str, task: dict):
    """Compose a completed episode from generated shots."""
    episode_id = task["episode_id"]
    episode = project_repo.get_episode(episode_id)
    if not episode:
        raise RuntimeError(f"Episode {episode_id} not found")

    update_project_stage(project_id, ProductionStage.EPISODE_COMPOSING.value, "in_progress")
    await _emit_stage_status(
        project_id, ProductionStage.EPISODE_COMPOSING.value, "in_progress", f"开始合成第{episode['episode_number']}集"
    )

    agent_id = STAGE_AGENT_MAP[ProductionStage.EPISODE_COMPOSING]
    total_episodes = len(project_repo.get_episodes(project_id))
    completed_before = project_repo.get_completed_episode_count(project_id)
    await _set_agent_status(
        project_id, agent_id, status="working", current_task=f"合成第{episode['episode_number']}集",
        completed_tasks=completed_before, total_tasks=max(1, total_episodes)
    )

    add_production_event(
        project_id, agent_id, ProductionStage.EPISODE_COMPOSING.value,
        "stage_started", f"开始合成第{episode['episode_number']}集",
        "正在拼接镜头、添加字幕...", episode_id=episode_id
    )

    project_repo.update_episode(episode_id, status="editing", progress=85)
    await _push_progress_update(project_id, episode_id)

    shots = get_shots_by_episode(episode_id)
    video_paths = [s["video_url"] for s in shots if s.get("video_url")]

    if video_paths and is_ffmpeg_available():
        try:
            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            output_path = str(OUTPUTS_DIR / f"{episode_id}.mp4")
            actual_paths = [str(RENDERS_DIR.parent / p.lstrip("/")) for p in video_paths]
            concatenate_videos(actual_paths, output_path)
            project_repo.update_episode(
                episode_id, video_url=f"/videos/{episode_id}.mp4", status="completed", progress=100
            )
            add_production_event(
                project_id, agent_id, ProductionStage.EPISODE_COMPOSING.value,
                "episode_completed", f"第{episode['episode_number']}集完成", "已合成成片",
                episode_id=episode_id, payload={"video_url": f"/videos/{episode_id}.mp4"}
            )
            await send_episode_completed(
                project_id, episode_id, episode["episode_number"], episode["title"], f"/videos/{episode_id}.mp4"
            )
        except Exception as e:
            project_repo.update_episode(episode_id, status="failed")
            add_production_event(
                project_id, agent_id, ProductionStage.EPISODE_COMPOSING.value,
                "episode_failed", f"第{episode['episode_number']}集合成失败", str(e), episode_id=episode_id
            )
    else:
        project_repo.update_episode(episode_id, status="completed", progress=100)
        add_production_event(
            project_id, agent_id, ProductionStage.EPISODE_COMPOSING.value,
            "episode_completed", f"第{episode['episode_number']}集完成", "已完成（无视频合成）",
            episode_id=episode_id
        )

    update_project_stage(project_id, ProductionStage.EPISODE_COMPOSING.value, "completed")
    update_project_stage(project_id, ProductionStage.EPISODE_COMPLETED.value, "completed")
    await _emit_stage_status(
        project_id, ProductionStage.EPISODE_COMPLETED.value, "completed", f"第{episode['episode_number']}集完成"
    )

    await _push_progress_update(project_id, episode_id)
    completed_now = project_repo.get_completed_episode_count(project_id)
    await _set_agent_status(
        project_id, agent_id, status="idle", current_task=None,
        completed_tasks=completed_now, total_tasks=max(1, total_episodes),
        progress=int(completed_now / max(1, total_episodes) * 100)
    )

    if not _queue_next_episode_shot_task(project_id):
        episodes = project_repo.get_episodes(project_id)
        if episodes and all(ep["status"] == "completed" for ep in episodes):
            task_repo.create_task(f"task_{project_id}_compose_final", project_id, "project_compose")

    task_repo.update_task(
        task["task_id"], status="completed", completed_at=datetime.utcnow().isoformat()
    )


# === Stage 6: Project Compose ===

async def _execute_project_compose(project_id: str, task: dict):
    """
    Compose final output from all completed episodes.
    Precondition: all episodes completed
    Output: project.status=completed
    """
    update_project_stage(project_id, ProductionStage.PROJECT_COMPOSING.value, "in_progress")
    agent_id = STAGE_AGENT_MAP[ProductionStage.PROJECT_COMPOSING]
    agent_repo.update_agent_state(project_id, agent_id, status="working", current_task="合成成片")

    add_production_event(
        project_id, agent_id, ProductionStage.PROJECT_COMPOSING.value,
        "stage_started", "开始合成项目", "正在拼接所有剧集..."
    )

    episodes = project_repo.get_episodes(project_id)
    completed_eps = [ep for ep in episodes if ep["status"] == "completed"]

    if not completed_eps:
        task_repo.update_task(task["task_id"], status="failed",
                              error_message="No completed episodes",
                              completed_at=datetime.utcnow().isoformat())
        return

    if is_ffmpeg_available() and len(completed_eps) > 1:
        try:
            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            output_path = str(OUTPUTS_DIR / f"{project_id}_final.mp4")
            video_paths = [ep["video_url"] for ep in completed_eps if ep.get("video_url")]
            if video_paths:
                actual_paths = [str(OUTPUTS_DIR.parent / p.lstrip("/")) for p in video_paths]
                concatenate_videos(actual_paths, output_path)

                add_production_event(
                    project_id, agent_id, ProductionStage.PROJECT_COMPOSING.value,
                    "project_video_created", "项目视频已生成",
                    output_path
                )
        except Exception as e:
            add_production_event(
                project_id, agent_id, ProductionStage.PROJECT_COMPOSING.value,
                "project_video_failed", "项目视频合成失败",
                str(e)
            )

    # Mark project completed
    project_repo.update_project(project_id, status="completed", progress=100)
    update_project_stage(project_id, ProductionStage.PROJECT_COMPOSING.value, "completed")
    update_project_stage(project_id, ProductionStage.PROJECT_COMPLETED.value, "completed")

    add_production_event(
        project_id, agent_id, ProductionStage.PROJECT_COMPLETED.value,
        "project_completed", "项目完成",
        f"《{project_repo.get_project(project_id)['title']}》已全部完成，共 {len(completed_eps)} 集"
    )

    # Reset all agent states to completed
    states = agent_repo.get_agent_states(project_id)
    for s in states:
        total = s["total_tasks"] or 1
        agent_repo.update_agent_state(project_id, s["agent_id"],
                                       status="idle", current_task=None,
                                       completed_tasks=total, total_tasks=total)

    await send_project_completed(project_id, project_repo.get_project(project_id)["title"], len(completed_eps))

    task_repo.update_task(task["task_id"], status="completed",
                          output_json={"episodes": len(completed_eps)},
                          completed_at=datetime.utcnow().isoformat())


# === Legacy support ===

async def _migrate_episode_run_to_linear(project_id: str, task: dict):
    """Convert legacy episode_run to the new linear chain."""
    episode_id = task["episode_id"]

    # Check if script exists
    episode = project_repo.get_episode(episode_id)
    if not episode:
        task_repo.update_task(task["task_id"], status="failed", error_message="Episode not found")
        return

    has_script = episode.get("script_json") is not None
    has_storyboard = episode.get("storyboard_json") is not None

    if not has_script:
        # Queue from script stage
        task_repo.create_task(f"task_{project_id}_script", project_id, "project_script")
    elif not has_storyboard:
        # Queue from format stage
        task_repo.create_task(f"task_{project_id}_format", project_id, "project_format")
    else:
        # Queue from assets/shots stage
        if not is_stage_completed(project_id, ProductionStage.ASSETS_COMPLETED.value):
            task_repo.create_task(f"task_{project_id}_assets", project_id, "project_assets")
        else:
            task_repo.create_task(f"task_{episode_id}_shots", project_id, "episode_shot_video",
                                   episode_id=episode_id)

    task_repo.update_task(task["task_id"], status="completed",
                          output_json={"migrated_to": "linear_chain"},
                          completed_at=datetime.utcnow().isoformat())


async def _execute_shot_video_legacy(project_id: str, task: dict):
    shot_id = task["shot_id"]
    episode_id = task["episode_id"]
    episode = project_repo.get_episode(episode_id)
    if not episode:
        raise RuntimeError(f"Episode {episode_id} not found")

    shot = next((s for s in get_shots_by_episode(episode_id) if s["shot_id"] == shot_id), None)
    if not shot:
        raise RuntimeError(f"Shot {shot_id} not found")

    # Determine series type
    proj = project_repo.get_project(project_id)
    proj_config = json.loads(proj.get("config_json", "{}")) if proj and isinstance(proj.get("config_json"), str) else (proj.get("config", {}) if proj else {})
    series_type = proj_config.get("series_type", "live-action")

    print(f"[Worker] Legacy shot video: project={project_id} shot={shot_id} series={series_type}")

    agent_id = STAGE_AGENT_MAP[ProductionStage.SHOTS_GENERATING]
    update_project_stage(project_id, ProductionStage.SHOTS_GENERATING.value, "in_progress")
    project_repo.update_episode(episode_id, status="rendering", progress=max(episode.get("progress") or 0, 70))
    await _set_agent_status(
        project_id, agent_id, status="working",
        current_task=f"镜头视频：第{episode['episode_number']}集 / 镜头 {shot['shot_number']}",
        completed_tasks=0, total_tasks=1
    )
    completed = await _generate_one_shot_video(project_id, episode, shot, agent_id, series_type)
    await _push_progress_update(project_id, episode_id)
    await _set_agent_status(project_id, agent_id, status="idle", current_task=None, completed_tasks=1 if completed else 0, total_tasks=1)
    task_repo.update_task(
        task["task_id"], status="completed",
        output_json={"shot_id": shot_id, "completed": completed},
        completed_at=datetime.utcnow().isoformat()
    )


# === Helpers ===


def _recalc_project_progress(project_id: str) -> int:
    """Recalculate project progress from episode progress fields."""
    episodes = project_repo.get_episodes(project_id)
    if not episodes:
        return 0

    progress = int(sum((ep.get("progress") or 0) for ep in episodes) / len(episodes))
    project = project_repo.get_project(project_id)
    if project and project.get("status") != "completed" and progress >= 100:
        progress = 95
    project_repo.update_project(project_id, progress=progress)
    return progress



async def _push_progress_update(project_id: str, episode_id: str | None = None):
    progress = _recalc_project_progress(project_id)
    episode_progress = None
    if episode_id:
        episode = project_repo.get_episode(episode_id)
        episode_progress = episode.get("progress") if episode else None
    await send_progress_update(project_id, progress, episode_id=episode_id, episode_progress=episode_progress)


async def _set_agent_status(
    project_id: str,
    agent_id: str,
    status: str,
    current_task: str | None = None,
    progress: int | None = None,
    completed_tasks: int | None = None,
    total_tasks: int | None = None,
):
    updates = {"status": status, "current_task": current_task}
    if completed_tasks is not None:
        updates["completed_tasks"] = completed_tasks
    elif progress is not None:
        updates["completed_tasks"] = progress
    if total_tasks is not None:
        updates["total_tasks"] = total_tasks
    agent_repo.update_agent_state(project_id, agent_id, **updates)
    await send_agent_update(project_id, agent_id, status, current_task=current_task, progress=progress)


async def _emit_stage_status(project_id: str, stage: str, status: str, title: str):
    await send_stage_update(project_id, stage, status, title=title)


async def _emit_agent_prompt(
    project_id: str,
    agent_id: str,
    stage: str,
    prompt: str,
    title: str,
    message: str,
    episode_id: str | None = None,
    shot_id: str | None = None,
):
    add_production_event(
        project_id, agent_id, stage, "prompt_issued", title, message,
        episode_id=episode_id, shot_id=shot_id, payload={"prompt": prompt}
    )
    await send_agent_monitor(
        project_id, agent_id, stage=stage, prompt=prompt, current_task=title,
        episode_id=episode_id, shot_id=shot_id, reset_output=True,
        event_type="prompt_issued", title=title, message=message
    )


async def _emit_agent_output(
    project_id: str,
    agent_id: str,
    stage: str,
    output_text: str,
    title: str,
    message: str,
    episode_id: str | None = None,
    shot_id: str | None = None,
    final: bool = True,
):
    add_production_event(
        project_id, agent_id, stage, "output_captured", title, message,
        episode_id=episode_id, shot_id=shot_id, payload={"output": output_text}
    )
    await send_agent_monitor(
        project_id, agent_id, stage=stage, output_text=output_text,
        episode_id=episode_id, shot_id=shot_id, final=final,
        event_type="output_captured", title=title, message=message
    )


def _queue_next_episode_shot_task(project_id: str) -> bool:
    episodes = project_repo.get_episodes(project_id)
    tasks = task_repo.get_tasks_by_project(project_id)
    active_episode_ids = {
        t.get("episode_id")
        for t in tasks
        if t["task_type"] in ("episode_shot_video", "episode_compose") and t["status"] in ("pending", "running")
    }
    print(f"[Worker] _queue_next_episode_shot_task: project={project_id} episodes={len(episodes)} active={active_episode_ids}")
    for episode in episodes:
        if episode["status"] == "completed":
            continue
        if episode["episode_id"] in active_episode_ids:
            continue
        task_id = f"task_{episode['episode_id']}_shots"
        print(f"[Worker] queueing task={task_id} for episode={episode['episode_id']}")
        task_repo.create_task(
            task_id, project_id,
            "episode_shot_video", episode_id=episode["episode_id"]
        )
        return True
    print(f"[Worker] no episode needs shot task")
    return False
