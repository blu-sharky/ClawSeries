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
    get_assets,
)
from routers.websocket import (
    send_progress_update, send_agent_update, send_episode_completed,
    send_project_completed, send_trace_update, send_agent_monitor,
    send_stage_update,

)
from integrations.llm import is_llm_configured, stream_llm
from integrations.video import is_video_configured, generate_video, get_video_config
from integrations.ffmpeg import is_ffmpeg_available, concatenate_videos
from config import RENDERS_DIR, OUTPUTS_DIR

from prompt_reference import HOT_HOOK_REFERENCE

from models import (
    ProductionStage,
    STAGE_AGENT_MAP,
    STAGE_PRECONDITIONS,
)


_worker_running = False


async def start_worker():
    """Start the background task worker."""
    global _worker_running
    if _worker_running:
        return
    _worker_running = True

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
        task_repo.update_task(
            task["task_id"],
            status="failed",
            error_message=str(e),
            completed_at=datetime.utcnow().isoformat(),
        )
        agent_repo.add_agent_log(project_id, "agent_director", "error",
                                  f"Task {task_type} failed: {e}")


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

    for idx, ep in enumerate(episodes, start=1):
        episode_id = ep["episode_id"]
        project_repo.update_episode(episode_id, status="scripting", progress=10)
        await _push_progress_update(project_id, episode_id)

        prompt = f"""请为以下 AI 短剧编写第{ep['episode_number']}集的完整剧本。

剧名: {project['title']}
类型: {config.get('genre', '都市爱情')}
风格: {config.get('style', '轻松幽默')}

主要角色:
{char_desc}

集数标题: {ep['title']}

{HOT_HOOK_REFERENCE}

写作补充：
- 学习这些爆点钩子的起题方式、冲突密度、身份反差和反转力度，把同样的抓人感落到本集开场、推进和结尾，但不要直接照抄原题或原情节。
- 本集至少要有一个足够抓人的开场钩子、一个中段升级点、一个结尾反转或悬念。

要求：
1. 这是 AI 短剧，场景集中、节奏快、每场都要有推进。
2. 角色行动与对白要清晰，便于后续转分镜和视频生成。
3. 直接返回 JSON。

JSON 包含 scenes 数组，每个 scene 包含:
- scene_number: 场景编号
- location: 场景地点
- time_of_day: 时间
- description: 场景描述
- dialogues: 对话数组 [{{character, line, emotion}}]
- actions: 动作描述数组"""

        script = _fallback_script(ep)
        if is_llm_configured():
            try:
                await _emit_agent_prompt(
                    project_id, agent_id, ProductionStage.SCRIPT_GENERATING.value,
                    prompt, f"第{ep['episode_number']}集剧本提示词",
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
                    script = json.loads(json_match.group())
            except Exception as e:
                agent_repo.add_agent_log(project_id, agent_id, "error", f"LLM调用失败: {e}")

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
            storyboard = _fallback_storyboard()

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

    for i, char in enumerate(characters, start=1):
        asset_id = f"asset_char_{i:03d}"
        prompt = f"{char['name']}, {char['description']}, portrait, consistent character design"
        await _emit_agent_prompt(
            project_id, agent_id, ProductionStage.ASSETS_GENERATING.value, prompt,
            f"角色资产提示词：{char['name']}", f"开始为角色 {char['name']} 锁定视觉锚点"
        )
        create_asset(
            asset_id, project_id, "character", char["name"], char["description"],
            prompt=prompt, anchor_prompt=f"{char['name']}, {char['role']}, consistent face"
        )
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

    for i, scene_name in enumerate(scene_names, start=1):
        asset_id = f"asset_scene_{i:03d}"
        create_asset(
            asset_id, project_id, "scene", scene_name, f"场景: {scene_name}",
            prompt=f"{scene_name}, establishing shot, cinematic"
        )

    for ep in episodes:
        project_repo.update_episode(ep["episode_id"], status="asset_generating", progress=60)
        await _push_progress_update(project_id, ep["episode_id"])

    update_project_stage(project_id, ProductionStage.ASSETS_GENERATING.value, "completed")
    update_project_stage(project_id, ProductionStage.ASSETS_COMPLETED.value, "completed")
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
    from repositories.settings_repo import get_setting
    video_mode = get_setting("video_generation_mode") or "manual"

    if video_mode == "manual":
        add_production_event(
            project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
            "manual_mode", "手动模式", "视频生成模式为手动，请手动触发镜头生成",
            episode_id=episode_id
        )
        project_repo.update_episode(episode_id, status="rendering", progress=72)
        await _push_progress_update(project_id, episode_id)
        task_repo.update_task(
            task["task_id"], status="completed",
            output_json={"mode": "manual"}, completed_at=datetime.utcnow().isoformat()
        )
        await _set_agent_status(project_id, agent_id, status="idle", current_task=None)
        return

    for idx, shot in enumerate(shots, start=1):
        shot_id = shot["shot_id"]
        description = shot.get("description", "")

        await _emit_agent_prompt(
            project_id, agent_id, ProductionStage.SHOTS_GENERATING.value, description,
            f"镜头 {shot['shot_number']} 视频提示词",
            f"开始生成第{episode['episode_number']}集镜头 {shot['shot_number']} 视频",
            episode_id=episode_id, shot_id=shot_id
        )

        try:
            if is_video_configured():
                RENDERS_DIR.mkdir(parents=True, exist_ok=True)
                output_path = str(RENDERS_DIR / f"{shot_id}.mp4")
                video_config = get_video_config()
                add_shot_trace(
                    shot_id, project_id, "video_generation", agent_id=agent_id,
                    prompt_summary=description[:100],
                    prompt_hash=hashlib.md5(description.encode()).hexdigest(),
                    provider_name=video_config["provider"], model_name=video_config["model"],
                )

                await generate_video(description, output_path, duration_seconds=3, aspect_ratio="16:9")

                update_shot(shot_id, status="completed", video_url=f"/renders/{shot_id}.mp4")
                add_shot_trace(
                    shot_id, project_id, "video_completed", agent_id=agent_id,
                    output_path=output_path, provider_name=video_config["provider"], model_name=video_config["model"],
                )
                shots_completed += 1

                await _emit_agent_output(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    f"镜头 {shot['shot_number']} 视频生成完成：/renders/{shot_id}.mp4",
                    f"镜头 {shot['shot_number']} 输出", "视频已生成",
                    episode_id=episode_id, shot_id=shot_id
                )
                add_production_event(
                    project_id, agent_id, ProductionStage.SHOTS_GENERATING.value,
                    "shot_completed", f"镜头 {shot['shot_number']} 完成", "视频已生成",
                    episode_id=episode_id, shot_id=shot_id
                )
            else:
                update_shot(shot_id, status="failed")
                add_shot_trace(
                    shot_id, project_id, "video_failed", agent_id=agent_id,
                    error_reason="Video provider not configured"
                )
        except Exception as e:
            update_shot(shot_id, status="failed")
            add_shot_trace(
                shot_id, project_id, "video_failed", agent_id=agent_id, error_reason=str(e)
            )

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
            actual_paths = [str(RENDERS_DIR / p.replace("/renders/", "")) for p in video_paths]
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
                actual_paths = [str(OUTPUTS_DIR / p.replace("/videos/", "")) for p in video_paths]
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

    # Reset all agent states
    states = agent_repo.get_agent_states(project_id)
    for s in states:
        agent_repo.update_agent_state(project_id, s["agent_id"], status="idle", current_task=None)

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
    """Legacy single shot video task."""
    shot_id = task["shot_id"]
    episode_id = task["episode_id"]

    # Redirect to episode_shot_video
    task_repo.create_task(f"task_{episode_id}_shots", project_id, "episode_shot_video",
                          episode_id=episode_id)
    task_repo.update_task(task["task_id"], status="completed",
                          output_json={"redirected": "episode_shot_video"},
                          completed_at=datetime.utcnow().isoformat())


# === Helpers ===

def _fallback_script(episode: dict) -> dict:
    return {
        "scenes": [
            {
                "scene_number": 1,
                "location": "上海陆家嘴 - 写字楼大厅",
                "time_of_day": "清晨",
                "description": f"清晨的陆家嘴，阳光洒在玻璃幕墙上。{episode['title']}的故事从这里开始...",
                "dialogues": [
                    {"character": "主角", "line": "新的一天开始了！", "emotion": "期待"},
                ],
                "actions": ["主角深吸一口气，推开旋转门"],
            },
        ]
    }


def _fallback_storyboard() -> list:
    return [
        {"shot_number": 1, "description": "全景 - 城市天际线", "camera_movement": "缓慢推进", "duration": "3s"},
        {"shot_number": 2, "description": "中景 - 主角出场", "camera_movement": "跟随镜头", "duration": "4s"},
        {"shot_number": 3, "description": "特写 - 表情", "camera_movement": "固定机位", "duration": "2s"},
    ]


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
    for episode in episodes:
        if episode["status"] == "completed":
            continue
        if episode["episode_id"] in active_episode_ids:
            continue
        task_repo.create_task(
            f"task_{episode['episode_id']}_shots", project_id,
            "episode_shot_video", episode_id=episode["episode_id"]
        )
        return True
    return False
