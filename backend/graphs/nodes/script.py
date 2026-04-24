"""Script generation node - Stage 1 of production pipeline."""

import json
import re
from datetime import datetime

from langgraph.types import interrupt

from graphs.state import ProductionState
from repositories import project_repo, agent_repo
from repositories.production_event_repo import (
    add_production_event,
    init_project_stages,
    update_project_stage,
    is_stage_completed,
)
from routers.websocket import send_agent_monitor
from integrations.llm import is_llm_configured, stream_llm
from models import ProductionStage, STAGE_AGENT_MAP
from prompt_reference import HOT_HOOK_REFERENCE


def _extract_script_summary(script: dict, episode_number: int, title: str) -> str:
    """Extract a concise summary from a script for context passing.

    Returns:
        Summary string with key plot points, character states, and ending.
    """
    scenes = script.get("scenes", [])
    if not scenes:
        return f"第{episode_number}集《{title}》：无场景"

    summary_parts = [f"第{episode_number}集《{title}》："]

    # Extract key info from each scene
    for scene in scenes:
        scene_num = scene.get("scene_number", "?")
        location = scene.get("location", "未知地点")
        description = scene.get("description", "")[:100]  # Truncate
        summary_parts.append(f"  场景{scene_num}({location}): {description}")

        # Extract key dialogues (limit to avoid bloat)
        dialogues = scene.get("dialogues", [])
        for d in dialogues[:3]:  # Max 3 dialogues per scene
            char = d.get("character", "?")
            line = d.get("line", "")[:50]  # Truncate
            emotion = d.get("emotion", "")
            summary_parts.append(f"    - {char}: \"{line}\" ({emotion})")

    return "\n".join(summary_parts)


def _fallback_script(episode: dict) -> dict:
    """Generate a fallback script when LLM is not available."""
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


async def script_node(state: ProductionState) -> dict:
    """Generate complete scripts for all episodes.

    This is Stage 1 of the production pipeline.
    """
    project_id = state["project_id"]
    agent_id = STAGE_AGENT_MAP[ProductionStage.SCRIPT_GENERATING]

    # Initialize stages if needed
    if not is_stage_completed(project_id, ProductionStage.REQUIREMENTS_CONFIRMED.value):
        init_project_stages(project_id)
        update_project_stage(project_id, ProductionStage.REQUIREMENTS_CONFIRMED.value, "completed")

    update_project_stage(project_id, ProductionStage.SCRIPT_GENERATING.value, "in_progress")

    # Load project data
    project = project_repo.get_project(project_id)
    characters = project_repo.get_characters(project_id)
    episodes = project_repo.get_episodes(project_id)
    config = project.get("config", {})

    # Prepare character descriptions
    char_desc = "\n".join(
        f"- {c['name']}({c['role']}): {c['description']}" for c in characters
    )

    # Build per-episode detail lookup from outline
    episodes_detail = config.get("episodes_detail", [])
    detail_by_ep = {d.get("episode"): d for d in episodes_detail if isinstance(d, dict)}

    # Update agent status
    agent_repo.update_agent_state(
        project_id, agent_id,
        status="working",
        current_task="生成完整剧本",
        completed_tasks=0,
        total_tasks=len(episodes),
    )

    add_production_event(
        project_id, agent_id, ProductionStage.SCRIPT_GENERATING.value,
        "stage_started", "开始生成剧本", "正在为所有剧集逐集生成完整剧本..."
    )

    # Accumulate script summaries for context passing
    previous_scripts_summary: list[str] = []

    # Generate script for each episode
    for idx, ep in enumerate(episodes, start=1):
        episode_id = ep["episode_id"]
        project_repo.update_episode(episode_id, status="scripting", progress=10)

        # Build context from previous episodes
        previous_context = ""
        if previous_scripts_summary:
            previous_context = f"""前情提要（第1-{idx-1}集概要）：
{chr(10).join(previous_scripts_summary)}

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

        prompt = f"""{previous_context}请为以下 AI 短剧编写第{ep['episode_number']}集的完整剧本。

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

【输出格式 - 必须严格遵守】
直接输出纯 JSON 对象，禁止使用 markdown 代码块包裹，禁止输出任何其他内容。

正确示例：
{{"scenes": [{{"scene_number": 1, "location": "办公室", "time_of_day": "上午", "description": "...", "dialogues": [...], "actions": [...]}}]}}

错误示例（禁止）：
```json
{{"scenes": [...]}}
```

JSON 结构：
- scenes: 场景数组
  - scene_number: 场景编号
  - location: 场景地点
  - time_of_day: 时间
  - description: 场景描述
  - dialogues: 对话数组 [{{character, line, emotion}}]
  - actions: 动作描述数组"""

        script = _fallback_script(ep)
        if is_llm_configured():
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    add_production_event(
                        project_id, agent_id, ProductionStage.SCRIPT_GENERATING.value,
                        "prompt_issued", f"第{ep['episode_number']}集剧本提示词" + (f" (重试{attempt})" if attempt > 1 else ""),
                        f"开始为《{ep['title']}》生成剧本", episode_id=episode_id,
                        payload={"prompt": prompt[:200], "attempt": attempt}
                    )

                    chunks = []
                    async for chunk in stream_llm(
                        [
                            {"role": "system", "content": "你是一个专业的 AI 短剧编剧。你擅长高钩子、强反转、强情绪推进的短剧写法。\n\n【输出规则 - 绝对遵守】\n1. 直接输出纯 JSON 对象，不要包裹在 markdown 代码块中。\n2. 禁止输出任何 JSON 以外的内容：不要解释、不要注释、不要前后缀文字。\n3. 禁止使用 ```json ``` 包裹。"},
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
                    add_production_event(
                        project_id, agent_id, ProductionStage.SCRIPT_GENERATING.value,
                        "output_captured", f"第{ep['episode_number']}集剧本输出",
                        f"已获取《{ep['title']}》剧本输出", episode_id=episode_id,
                        payload={"output": response[:200]}
                    )

                    json_match = re.search(r'\{[\s\S]*\}', response)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        # Validate basic structure
                        if isinstance(parsed, dict) and "scenes" in parsed:
                            script = parsed
                            break  # Success, exit retry loop
                        else:
                            agent_repo.add_agent_log(
                                project_id, agent_id, "warning",
                                f"第{ep['episode_number']}集第{attempt}次尝试: JSON缺少scenes字段"
                            )
                    else:
                        agent_repo.add_agent_log(
                            project_id, agent_id, "warning",
                            f"第{ep['episode_number']}集第{attempt}次尝试: 未找到有效JSON"
                        )

                    if attempt < max_retries:
                        # Append retry hint to the same prompt for next attempt
                        prompt = prompt + "\n\n注意：上一次返回的内容不是有效的JSON，请只返回纯JSON，不要包含任何其他文字。"

                except json.JSONDecodeError as e:
                    agent_repo.add_agent_log(
                        project_id, agent_id, "warning",
                        f"第{ep['episode_number']}集第{attempt}次尝试: JSON解析失败 - {e}"
                    )
                    if attempt < max_retries:
                        prompt = prompt + "\n\n注意：上一次返回的内容不是有效的JSON，请只返回纯JSON，不要包含任何其他文字。"
                except Exception as e:
                    agent_repo.add_agent_log(project_id, agent_id, "error", f"LLM调用失败: {e}")
                    break  # Non-JSON error, don't retry

        project_repo.update_episode(episode_id, script=script, status="scripting", progress=25)

        # Accumulate this script's summary for next episode
        script_summary = _extract_script_summary(script, ep['episode_number'], ep['title'])
        previous_scripts_summary.append(script_summary)

        agent_repo.update_agent_state(
            project_id, agent_id, status="working",
            current_task=f"剧本生成：第{ep['episode_number']}集",
            completed_tasks=idx, total_tasks=len(episodes)
        )

        add_production_event(
            project_id, agent_id, ProductionStage.SCRIPT_GENERATING.value,
            "episode_script_completed", f"第{ep['episode_number']}集剧本完成",
            f"已完成《{ep['title']}》剧本编写",
            episode_id=episode_id,
            payload={"scene_count": len(script.get("scenes", []))}
        )

    # Mark stage completed
    update_project_stage(project_id, ProductionStage.SCRIPT_GENERATING.value, "completed")
    update_project_stage(project_id, ProductionStage.SCRIPT_COMPLETED.value, "completed")

    add_production_event(
        project_id, agent_id, ProductionStage.SCRIPT_COMPLETED.value,
        "stage_completed", "剧本生成完成", f"已完成全部 {len(episodes)} 集剧本"
    )

    agent_repo.update_agent_state(
        project_id, agent_id, status="idle", current_task=None,
        completed_tasks=len(episodes), total_tasks=len(episodes)
    )

    # Return state updates
    return {
        "current_stage": ProductionStage.SCRIPT_COMPLETED.value,
        "episodes": [
            {
                "episode_id": ep["episode_id"],
                "episode_number": ep["episode_number"],
                "title": ep["title"],
                "status": "scripting",
                "progress": 25,
            }
            for ep in episodes
        ],
    }
