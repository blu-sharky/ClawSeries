"""
Conversation service - LLM-driven conversation flow for script outline generation.
"""

import uuid
import json
import re
from datetime import datetime

from models import (
    CreateConversationResponse, SendMessageResponse,
    ConversationDetail, ConversationState, Message, QuestionOption,
    ConfirmResponse, StartProductionResponse, ScriptOutline,
)
from repositories import conversation_repo, project_repo, agent_repo, task_repo
from integrations.llm import call_llm, stream_llm, is_llm_configured

from prompt_reference import HOT_HOOK_REFERENCE, SHORT_DRAMA_PROMPT_REFERENCE


# Genre options remain useful for lightweight classification and fallbacks.
GENRE_OPTIONS = ["都市爱情", "悬疑推理", "古风仙侠", "职场商战"]
SERIES_TYPE_OPTIONS = ["真人短剧", "动画漫剧"]
EPISODE_COUNT_OPTIONS = ["8集", "12集", "20集", "30集"]
EPISODE_DURATION_OPTIONS = ["1分钟", "2分钟", "3分钟", "5分钟", "8分钟"]
TARGET_AUDIENCE_OPTIONS = ["年轻女性", "年轻男性", "全年龄向", "中年群体"]
STYLE_TONE_OPTIONS = ["轻松幽默", "紧张刺激", "温馨治愈", "暗黑深沉"]

# Episode title templates
EPISODE_TITLES = [
    "意外的相遇", "电梯风波", "不打不相识", "暗生情愫", "心动的瞬间",
    "第一次约会", "甜蜜日常", "职场风波", "误会重重", "信任危机",
    "真相大白", "冰释前嫌", "患难见真情", "暗中守护", "命运转折",
    "最终抉择", "破茧重生", "勇敢面对", "携手并进", "幸福结局",
    "新的开始", "并肩作战", "风雨同路", "拨云见日", "逆风翻盘",
    "曙光初现", "步步为营", "绝地反击", "峰回路转", "大结局",
]


class ConversationService:
    async def create_conversation(self, initial_idea: str) -> CreateConversationResponse:
        """Create conversation and generate first questions via LLM."""
        conv_id = f"conv_{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow().isoformat() + "Z"

        # Persist conversation
        conversation_repo.create_conversation(conv_id, initial_idea)
        conversation_repo.add_message(conv_id, "user", initial_idea)

        collected = {"initial_idea": initial_idea}
        self._extract_common_preferences(collected, initial_idea)

        # Try to extract genre from initial idea using LLM
        if is_llm_configured() and "genre" not in collected:
            try:
                genre = await self._extract_genre_from_idea(initial_idea)
                if genre:
                    collected["genre"] = genre
            except Exception as e:
                print(f"Genre extraction failed: {e}")

        # Generate first questions via LLM (or fallback)
        questions, content = await self._generate_next_questions(collected, phase=1)
        
        conversation_repo.update_conversation(conv_id, collected_info=collected, current_phase=1)
        
        msg = Message(role="assistant", content=content,
                      timestamp=now, questions=questions, agent_id="agent_director")

        conversation_repo.add_message(conv_id, "assistant", content,
                                       questions_json=[q.model_dump() for q in questions])

        return CreateConversationResponse(
            conversation_id=conv_id, message=msg,
            state=ConversationState.COLLECTING_REQUIREMENTS,
        )

    async def _extract_genre_from_idea(self, initial_idea: str) -> str | None:
        """Extract genre from user's initial idea using LLM."""
        prompt = f"""分析用户的短剧想法，判断最匹配的类型。

用户想法：{initial_idea}

可选类型：都市爱情、悬疑推理、古风仙侠、职场商战

只返回类型名称，不要其他内容。如果无法判断，返回"都市爱情"。"""
        
        try:
            response = await call_llm(
                [{"role": "user", "content": prompt}], 
                temperature=0.3, 
                max_tokens=20
            )
            genre = response.strip()
            # Validate it's one of our genres
            if genre in GENRE_OPTIONS:
                return genre
            # Try to match partial
            for g in GENRE_OPTIONS:
                if g in genre or genre in g:
                    return g
            return None
        except Exception as e:
            print(f"Genre extraction error: {e}")
            return None
    async def send_message(self, conversation_id: str, user_message: str) -> SendMessageResponse | None:
        conv = conversation_repo.get_conversation(conversation_id)
        if not conv:
            return None

        now, current_phase, collected = self._ingest_user_message(
            conv, conversation_id, user_message
        )

        next_phase = current_phase + 1
        if next_phase < 3:
            conversation_repo.update_conversation(
                conversation_id, current_phase=next_phase
            )
            questions, content = await self._generate_next_questions(collected, next_phase)
            msg = Message(
                role="assistant",
                content=content,
                timestamp=now,
                questions=questions,
                agent_id="agent_director",
            )
            conversation_repo.add_message(
                conversation_id,
                "assistant",
                content,
                questions_json=[q.model_dump() for q in questions],
            )

            return SendMessageResponse(
                conversation_id=conversation_id,
                message=msg,
                state=ConversationState.COLLECTING_REQUIREMENTS,
            )

        outline = await self._generate_outline_with_llm(collected)
        return self._finalize_outline_response(conversation_id, outline, now)

    def _ingest_user_message(
        self, conv: dict, conversation_id: str, user_message: str
    ) -> tuple[str, int, dict]:
        now = datetime.utcnow().isoformat() + "Z"
        conversation_repo.add_message(conversation_id, "user", user_message)

        current_phase = conv["current_phase"]
        collected = (
            json.loads(conv["collected_info"])
            if isinstance(conv["collected_info"], str)
            else (conv["collected_info"] or {})
        )
        self._extract_info(collected, user_message, current_phase)
        conversation_repo.update_conversation(
            conversation_id, collected_info=collected
        )
        return now, current_phase, collected

    def _finalize_outline_response(
        self, conversation_id: str, outline: ScriptOutline, now: str
    ) -> SendMessageResponse:
        conversation_repo.update_conversation(
            conversation_id,
            state="awaiting_final_confirmation",
            script_outline_json=outline.model_dump(),
        )
        content = self._build_outline_message(outline)
        msg = Message(
            role="assistant",
            content=content,
            timestamp=now,
            agent_id="agent_chief_director",
        )
        conversation_repo.add_message(conversation_id, "assistant", content)
        return SendMessageResponse(
            conversation_id=conversation_id,
            message=msg,
            state=ConversationState.AWAITING_FINAL_CONFIRMATION,
        )

    async def _generate_next_questions(
        self, collected: dict, phase: int
    ) -> tuple[list[QuestionOption], str]:
        """Generate AI-short-drama follow-up questions with LLM and fallback."""
        genre = collected.get("genre", "短剧")
        initial_idea = collected.get("initial_idea", "")
        missing_fields = []
        if "episode_count" not in collected:
            missing_fields.append("集数")
        if "episode_duration" not in collected:
            missing_fields.append("单集时长")
        if "target_audience" not in collected:
            missing_fields.append("目标观众")

        if not is_llm_configured():
            return self._fallback_questions(collected, phase)

        if phase == 1:
            context = f"用户想制作一部{genre}AI短剧，初始想法是：{initial_idea}"
            instruction = (
                "请生成 2-3 个问题，帮助明确这部 AI 短剧的创作方向。"
                "优先追问核心冲突、主角类型、故事舞台、悬念钩子、参考气质。"
                f"如果以下信息缺失且确实影响方案，请自然地补问：{', '.join(missing_fields) if missing_fields else '无'}。"
                "已明确的信息不要重复问。严禁询问预算、拍摄成本、演员资源、置景成本。"
                "问题要像创作讨论，不要像制片表格。"
            )
        else:
            context = (
                f"用户想制作{genre}AI短剧，已知信息："
                f"{json.dumps(collected, ensure_ascii=False)}"
            )
            instruction = (
                "请生成 2-3 个更深入的问题，继续细化人物关系、反转机制、情绪基调、结局倾向、"
                "必须保留的名场面或禁忌元素。"
                f"如果以下信息仍缺失，可以顺带补问其中最关键的项：{', '.join(missing_fields) if missing_fields else '无'}。"
                "已明确的信息不要重复问。严禁询问预算、拍摄成本、演员资源。"
            )

        prompt = f"""你是一位专业的 AI 短剧制片顾问。
{context}
{instruction}

{SHORT_DRAMA_PROMPT_REFERENCE}

背景约束：
1. 这是 AI 短剧，不是传统长剧；后续会进入 AI 分镜、资产生成和视频生成流程。
2. 问题应帮助模型产出更适合 AI 生成的内容：人物关系清晰、场景集中、钩子强、反转快。
3. 如果用户已经给出集数、单集时长、目标观众，就不要再问这些。
4. 不要问预算。

【输出格式 - 必须严格遵守】
直接输出纯 JSON 对象，禁止使用 markdown 代码块包裹，禁止输出任何其他内容。

正确示例：
{{"开场白": "自然的回应", "问题": [{{"id": "q1", "问题": "问题文本", "类型": "select", "选项": ["选项1", "选项2"]}}]}}

错误示例（禁止）：
```json
{{"开场白": ...}}
```

JSON 结构：
- 开场白: 一句自然的回应和引导语
- 问题: 问题数组
  - id: 英文ID，用于内部存储
  - 问题: 具体自然的问题文本
  - 类型: select 或 text
  - 选项: 仅 select 类型需要，2-4 个选项
  - 占位符: 仅 text 类型需要

要求：
1. 问题必须能帮助编剧推进创作，而不是让用户填制片表格。
2. 如果是 select，选项要有明显区分度。"""

        try:
            data = None
            system_msg = {"role": "system", "content": "你是一个专业的 AI 短剧制片顾问。\n\n【输出规则 - 绝对遵守】\n1. 直接输出纯 JSON 对象，不要包裹在 markdown 代码块中。\n2. 禁止输出任何 JSON 以外的内容：不要解释、不要注释、不要前后缀文字。\n3. 禁止使用 ```json ``` 包裹。"}

            max_retries = 3
            current_prompt = prompt
            for attempt in range(1, max_retries + 1):
                try:
                    response = await call_llm(
                        [system_msg, {"role": "user", "content": current_prompt}],
                        temperature=0.7,
                        max_tokens=1024,
                    )
                    data = self._parse_llm_json(response)
                    break
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"LLM question generation parse error (attempt {attempt}/{max_retries}): {e}")
                    if attempt < max_retries:
                        current_prompt = current_prompt + "\n\n注意：上一次返回的内容不是有效的JSON，请只返回纯JSON，不要包含任何其他文字或代码块。"
                    else:
                        data = None

            if not data:
                return self._fallback_questions(collected, phase)

            questions = []
            for q in data.get("问题", []):
                question_text = (q.get("问题") or "").strip()
                if not question_text:
                    continue
                question_type = q.get("类型", "text")
                options = q.get("选项") if question_type == "select" else None
                questions.append(
                    QuestionOption(
                        id=q.get("id", f"q_{phase}_{len(questions)}"),
                        question=question_text,
                        type=question_type,
                        options=options,
                        placeholder=q.get("占位符"),
                    )
                )

            if not questions:
                return self._fallback_questions(collected, phase)

            content = data.get("开场白", "让我继续了解您的需求。")
            return questions, content

        except Exception as e:
            print(f"LLM question generation failed: {e}")
            return self._fallback_questions(collected, phase)

    def _missing_production_questions(self, collected: dict) -> list[QuestionOption]:
        questions: list[QuestionOption] = []
        if "series_type" not in collected:
            questions.append(
                QuestionOption(
                    id="series_type",
                    question="您想制作真人短剧还是动画漫剧？",
                    type="select",
                    options=SERIES_TYPE_OPTIONS,
                )
            )
        if "episode_count" not in collected:
            questions.append(
                QuestionOption(
                    id="episode_count",
                    question="这部 AI 短剧您更倾向做成多少集？",
                    type="select",
                    options=EPISODE_COUNT_OPTIONS,
                )
            )
        if "episode_duration" not in collected:
            questions.append(
                QuestionOption(
                    id="episode_duration",
                    question="单集时长更希望控制在哪个区间？",
                    type="select",
                    options=EPISODE_DURATION_OPTIONS,
                )
            )
        if "target_audience" not in collected:
            questions.append(
                QuestionOption(
                    id="target_audience",
                    question="更希望主要打到哪类观众？",
                    type="select",
                    options=TARGET_AUDIENCE_OPTIONS,
                )
            )
        return questions

    def _fallback_questions(self, collected: dict, phase: int) -> tuple[list[QuestionOption], str]:
        """Fallback questions when LLM is unavailable or malformed."""
        missing_questions = self._missing_production_questions(collected)

        if phase == 1:
            questions = [
                QuestionOption(
                    id="story_world",
                    question="您更想把故事放在什么样的舞台里？",
                    type="select",
                    options=["现代都市", "校园/青春", "古风世界", "架空悬疑场景"],
                )
            ]
            questions.extend(missing_questions[:2])
            if len(questions) < 3:
                questions.append(
                    QuestionOption(
                        id="core_hook",
                        question="最想突出的核心钩子是什么？",
                        type="text",
                        placeholder="例如：身份反转、时间循环、禁忌之恋、复仇翻盘……",
                    )
                )
            content = f"明白了，我们先把这部《{collected.get('genre', '短剧')}》AI短剧的故事骨架搭起来。"
            return questions[:3], content

        if phase == 2:
            questions = missing_questions[:2]
            questions.extend(
                [
                    QuestionOption(
                        id="relationship_dynamic",
                        question="您更想强化哪种人物关系张力？",
                        type="select",
                        options=["互相试探", "宿敌对决", "暧昧拉扯", "师徒/搭档信任危机"],
                    ),
                    QuestionOption(
                        id="tone_direction",
                        question="整体气质更偏向哪种感觉？",
                        type="select",
                        options=["冷峻克制", "高能反转", "情绪浓烈", "轻松但有钩子"],
                    ),
                    QuestionOption(
                        id="must_have_element",
                        question="有没有一定想保留的名场面或设定？",
                        type="text",
                        placeholder="例如：雨夜追凶、婚礼翻车、天台对峙、记忆错位……",
                    ),
                ]
            )
            content = "很好，再把这部 AI 短剧的人物关系和戏剧张力钉得更牢一点。"
            return questions[:3], content

        return [], ""

    def _parse_llm_json(self, response: str) -> dict:
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(
                lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]
            )
        return json.loads(response)

    def _build_outline_prompt(self, collected: dict) -> str:
        genre = collected.get("genre", "都市爱情")
        episode_count = collected.get("episode_count", 20)
        episode_duration = collected.get("episode_duration", "3分钟")
        target_audience = collected.get("target_audience", "全年龄向")
        story_background = collected.get("story_background", "")
        style_tone = collected.get("style_tone", "")
        special_elements = collected.get("special_elements", "")
        initial_idea = collected.get("initial_idea", "")
        phase1_answers = collected.get("phase1_answers", "")
        phase2_answers = collected.get("phase2_answers", "")

        return f"""你是一位专业的 AI 短剧编剧。请根据以下需求生成一个适合 AI 生成制作的短剧剧本大纲。

项目要求：
1. 这是 AI 短剧，节奏要快，每集都应有明确钩子或反转。
2. 角色关系要清晰，核心场景尽量集中，便于后续 AI 分镜、资产和视频生成。
3. 如果用户已经明确给出集数、单集时长、目标观众，就严格以用户输入为准。

{HOT_HOOK_REFERENCE}

逐集结构要求（每集必须遵循）：
- 开场5秒内必须有强钩子（悬念/冲突/身份反差/意外事件）
- 中段必须有升级点（新信息揭示/关系变化/危机加深）
- 结尾必须有反转或悬念（让用户忍不住点下一集）
- 每集场景控制在2-4个，便于AI视频生成
- 对白简洁有力，动作描写可视化（便于后续分镜和视频生成）

AI视频生成适配要求：
- 场景描写要具体可视觉化（明确的时间、地点、光线、氛围）
- 角色动作要清晰具体（便于AI生成分镜画面）
- 避免抽象内心独白，用动作和对白表达情感
- 每场戏有明确的空间感（室内/室外、近景/远景、日/夜）

用户需求：
- 类型：{genre}
- 建议集数：{episode_count}集
- 建议单集时长：{episode_duration}
- 目标观众：{target_audience}
- 故事背景：{story_background or '由编剧自由发挥'}
- 风格基调：{style_tone or '由编剧根据题材判断'}
- 特殊元素：{special_elements or '无特别要求'}
- 初始想法：{initial_idea}
- 第一轮补充：{phase1_answers or '无'}
- 第二轮补充：{phase2_answers or '无'}

如果用户没有明确给出集数或单集时长，请你自行选择最适合该题材的常见 AI 短剧规模，不要因为缺少这两个信息而降低内容完整度。
请学习这些爆点钩子的起题方式、身份反差、反转力度和开场抓人感，把同样的爆点密度融入剧名、梗概、角色设定与分集主题，但不要直接照抄原题或原情节。

请生成一个完整的剧本大纲，包括：
1. 剧名（吸引人的标题）
2. 故事梗概（100-200字）
3. 主要角色（3-5个角色，每个包含姓名、年龄、角色定位、性格描述）
4. 逐集标题和结构（每集包含开场钩子、中段升级点、结尾悬念）
5. 逐集详情（包含每集的钩子、升级点、悬念、关键场景描述）

【输出格式 - 必须严格遵守】
直接输出纯 JSON 对象，禁止使用 markdown 代码块包裹，禁止输出任何其他内容。

正确示例：
{{"title": "剧名", "synopsis": "故事梗概", "characters": [{{"name": "姓名", "age": 25, "role": "角色定位", "description": "性格描述"}}], "episode_titles": ["第1集标题", "第2集标题"], "episodes_summary": [{{"range": "1-5", "theme": "主题"}}], "episodes_detail": [{{"episode": 1, "title": "第1集标题", "hook": "开场钩子描述", "escalation": "中段升级点", "cliffhanger": "结尾悬念/反转", "scenes": "2-3句话描述本集关键场景"}}], "episode_count": 6, "episode_duration": "3-5分钟"}}

错误示例（禁止）：
```json
{{"title": ...}}
```

JSON 结构：
- title: 剧名
- synopsis: 故事梗概
- characters: 角色数组 [{{name, age, role, description}}]
- episode_titles: 逐集标题数组
- episodes_summary: 分集概要数组 [{{range, theme}}]
- episodes_detail: 逐集详情数组 [{{"episode": 集号, "title": "标题", "hook": "开场钩子描述", "escalation": "中段升级点", "cliffhanger": "结尾悬念/反转", "scenes": "2-3句话描述本集关键场景"}}]
- episode_count: 总集数（必须与用户选择一致）
- episode_duration: 单集时长，必须是一个确切分钟数（如"3分钟"、"4分钟"），不要写范围"""

    def _build_outline_stream_prompt(self, collected: dict) -> str:
        genre = collected.get("genre", "都市爱情")
        episode_count = collected.get("episode_count", 20)
        episode_duration = collected.get("episode_duration", "3分钟")
        target_audience = collected.get("target_audience", "全年龄向")
        story_background = collected.get("story_background", "")
        style_tone = collected.get("style_tone", "")
        special_elements = collected.get("special_elements", "")
        initial_idea = collected.get("initial_idea", "")
        phase1_answers = collected.get("phase1_answers", "")
        phase2_answers = collected.get("phase2_answers", "")

        return f"""你是一位专业的 AI 短剧编剧，现在直接面向用户输出一版可确认的大纲说明。
要求：
1. 直接输出中文 markdown，不要输出 JSON，不要输出代码块。
2. 结构尽量贴近最终确认文案：剧名、故事梗概、主要角色、分集概要。
3. 这是 AI 短剧，内容要高钩子、强反转、角色关系清晰、场景集中。
4. 语气像已经整理好方案后在向用户汇报，不要解释你的思考过程。
5. 每集都要有明确的开场钩子、冲突升级和结尾悬念

{HOT_HOOK_REFERENCE}

逐集结构要求：每集必须有开场钩子（前5秒抓人）、中段升级点、结尾反转或悬念。场景描写要具体可视觉化。
用户需求：
- 类型：{genre}
- 建议集数：{episode_count}集
- 建议单集时长：{episode_duration}
- 目标观众：{target_audience}
- 故事背景：{story_background or '由编剧自由发挥'}
- 风格基调：{style_tone or '由编剧根据题材判断'}
- 特殊元素：{special_elements or '无特别要求'}
- 初始想法：{initial_idea}
- 第一轮补充：{phase1_answers or '无'}
- 第二轮补充：{phase2_answers or '无'}
请学习这些爆点钩子的起题方式、戏剧冲突和反转力度，把同样的抓人感融入最终汇报版大纲，但不要直接照抄原题或原情节。

请直接开始输出最终大纲内容。"""

    async def _generate_outline_with_llm(self, collected: dict) -> ScriptOutline:
        """Generate script outline using LLM based on collected requirements."""
        genre = collected.get("genre", "都市爱情")
        if not is_llm_configured():
            return self._fallback_outline(genre)

        prompt = self._build_outline_prompt(collected)
        system_msg = {"role": "system", "content": "你是一个专业的 AI 短剧编剧。\n\n【输出规则 - 绝对遵守】\n1. 直接输出纯 JSON 对象，不要包裹在 markdown 代码块中。\n2. 禁止输出任何 JSON 以外的内容：不要解释、不要注释、不要前后缀文字。\n3. 禁止使用 ```json ``` 包裹。"}

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = await call_llm(
                    [system_msg, {"role": "user", "content": prompt}],
                    temperature=0.8,
                )
                data = self._parse_llm_json(response)
                return ScriptOutline(**data)
            except json.JSONDecodeError as e:
                print(f"LLM outline generation JSON parse error (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    prompt = prompt + "\n\n注意：上一次返回的内容不是有效的JSON，请只返回纯JSON，不要包含任何其他文字或代码块。"
            except TypeError as e:
                print(f"LLM outline generation type error (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    prompt = prompt + "\n\n注意：请确保返回的JSON结构正确，字段类型匹配。"
            except Exception as e:
                print(f"LLM outline generation failed (attempt {attempt}/{max_retries}): {e}")
                if attempt >= max_retries:
                    break

        print(f"LLM outline generation failed after {max_retries} attempts, using fallback")
        return self._fallback_outline(genre)

    def _fallback_outline(self, genre: str) -> ScriptOutline:
        """Fallback outline when LLM is not available."""
        # Simplified fallback templates
        templates = {
            "都市爱情": {
                "title": "心动时刻",
                "synopsis": "职场新人意外邂逅集团继承人，从欢喜冤家到相知相爱，经历重重考验最终携手走向幸福。",
                "characters": [
                    {"name": "林小夏", "age": 24, "role": "女主角", "description": "市场部新人，活泼开朗"},
                    {"name": "陆景琛", "age": 28, "role": "男主角", "description": "集团继承人，外冷内热"},
                    {"name": "苏婉清", "age": 26, "role": "女配角", "description": "名门千金，心机深沉"},
                ],
                "episode_titles": ["意外的相遇", "电梯风波", "不打不相识", "暗生情愫", "心动的瞬间"],
                "episodes_summary": [
                    {"range": "1-5", "theme": "相遇与误会"},
                    {"range": "6-10", "theme": "相知与心动"},
                ],
            },
            "悬疑推理": {
                "title": "暗夜追踪",
                "synopsis": "天才犯罪心理学教授被卷入连环失踪案，随着调查深入，发现所有线索都指向十年前的旧案...",
                "characters": [
                    {"name": "顾言", "age": 32, "role": "男主角", "description": "犯罪心理学教授，冷静理性"},
                    {"name": "沈薇", "age": 28, "role": "女主角", "description": "刑侦记者，胆大心细"},
                    {"name": "韩墨", "age": 35, "role": "反派", "description": "神秘企业家，心思难测"},
                ],
                "episode_titles": ["午夜来电", "消失的证物", "第二个嫌疑人", "不完美的不在场", "镜中人"],
                "episodes_summary": [
                    {"range": "1-5", "theme": "案件初现"},
                    {"range": "6-10", "theme": "层层迷雾"},
                ],
            },
            "古风仙侠": {
                "title": "苍穹诀",
                "synopsis": "废柴少女意外觉醒上古血脉，踏上修仙之路，与冷面仙尊之间的宿命纠葛跨越千年...",
                "characters": [
                    {"name": "叶灵溪", "age": 18, "role": "女主角", "description": "活泼少女，血脉觉醒者"},
                    {"name": "凤九渊", "age": 500, "role": "男主角", "description": "仙界至尊，冷面寡言"},
                    {"name": "墨尘", "age": 200, "role": "男配角", "description": "魔族王子，亦正亦邪"},
                ],
                "episode_titles": ["血脉初醒", "仙门试炼", "暗中窥视", "正邪一线间", "宿命之约"],
                "episodes_summary": [
                    {"range": "1-5", "theme": "血脉觉醒"},
                    {"range": "6-10", "theme": "仙门试炼"},
                ],
            },
            "职场商战": {
                "title": "逆风翻盘",
                "synopsis": "前投行精英被合伙人背叛，失去一切后从底层重新开始，用智慧夺回属于自己的帝国。",
                "characters": [
                    {"name": "陈默", "age": 30, "role": "男主角", "description": "前投行精英，沉稳果决"},
                    {"name": "方晓薇", "age": 28, "role": "女主角", "description": "创业公司CEO，雷厉风行"},
                    {"name": "赵鹏飞", "age": 35, "role": "反派", "description": "投行合伙人，阴险狡诈"},
                ],
                "episode_titles": ["跌入谷底", "暗中蛰伏", "绝地反击", "背水一战", "王者归来"],
                "episodes_summary": [
                    {"range": "1-5", "theme": "跌入谷底"},
                    {"range": "6-10", "theme": "暗中布局"},
                ],
            },
        }
        
        template = templates.get(genre, templates["都市爱情"])
        return ScriptOutline(**template)

    def get_conversation(self, conversation_id: str) -> ConversationDetail | None:
        conv = conversation_repo.get_conversation(conversation_id)
        if not conv:
            return None
        messages = conversation_repo.get_messages(conversation_id)
        collected = json.loads(conv["collected_info"]) if isinstance(conv["collected_info"], str) else conv["collected_info"]
        return ConversationDetail(
            conversation_id=conv["conversation_id"],
            state=conv["state"],
            messages=messages,
            collected_info=collected or {},
        )

    def confirm_outline(self, conversation_id: str) -> ConfirmResponse | None:
        conv = conversation_repo.get_conversation(conversation_id)
        if not conv:
            return None

        outline_data = conv.get("script_outline_json")
        if not outline_data:
            return None

        if isinstance(outline_data, str):
            outline_data = json.loads(outline_data)

        outline = ScriptOutline(**outline_data)
        project_id = f"proj_{uuid.uuid4().hex[:8]}"

        conversation_repo.update_conversation(
            conversation_id,
            state="confirmed",
            project_id=project_id,
        )

        now = datetime.utcnow().isoformat() + "Z"
        content = (
            f"剧本大纲已确认！《{outline.title}》的制片项目即将启动。\n\n"
            "确认后将进入全自动制片流程，包括：\n"
            "- 角色三视图自动生成\n"
            "- 分集剧本编写\n"
            "- 分镜设计与视频生成\n"
            "- 自动剪辑与合成\n\n"
            '请点击"启动制片"按钮开始。'
        )
        msg = Message(role="assistant", content=content, timestamp=now, agent_id="agent_director")
        conversation_repo.add_message(conversation_id, "assistant", content)

        return ConfirmResponse(
            conversation_id=conversation_id,
            project_id=project_id,
            message=msg,
            script_outline=outline,
            state=ConversationState.CONFIRMED,
        )

    def start_production(self, conversation_id: str) -> StartProductionResponse | None:
        conv = conversation_repo.get_conversation(conversation_id)
        if not conv:
            return None

        project_id = conv.get("project_id") or f"proj_{uuid.uuid4().hex[:8]}"
        conversation_repo.update_conversation(
            conversation_id, state="production_started"
        )

        # Build project from conversation data
        outline_data = conv.get("script_outline_json")
        if isinstance(outline_data, str):
            outline_data = json.loads(outline_data)

        collected = json.loads(conv["collected_info"]) if isinstance(conv["collected_info"], str) else conv["collected_info"]

        if outline_data:
            outline = ScriptOutline(**outline_data)
            # Skip if project already exists (idempotent)
            existing = project_repo.get_project(project_id)
            if not existing:
                self._create_project_in_db(project_id, conversation_id, outline, collected)

        # Initialize production stages and queue first task
        from repositories.production_event_repo import (
            init_project_stages, update_project_stage, add_production_event
        )
        from repositories import task_repo
        from models import ProductionStage

        init_project_stages(project_id)
        update_project_stage(project_id, ProductionStage.REQUIREMENTS_CONFIRMED.value, "completed")

        # Mark agent_director (项目总监) as completed — it handled the conversation
        from repositories import agent_repo
        agent_repo.init_agent_states(project_id)
        agent_repo.update_agent_state(
            project_id, "agent_director",
            status="idle", current_task=None,
            completed_tasks=1, total_tasks=1,
        )

        # Emit production start events
        # First: mark requirements confirmed as completed by project director
        add_production_event(
            project_id, "agent_director", ProductionStage.REQUIREMENTS_CONFIRMED.value,
            "stage_completed", "需求确认完成",
            f"项目总监已完成需求收集与剧本大纲确认，项目《{outline.title}》正式立项"
        )
        # Second: announce production started
        add_production_event(
            project_id, "agent_director", ProductionStage.REQUIREMENTS_CONFIRMED.value,
            "production_started", "制片流程已启动",
            f"即将开始生成剧本..."
        )

        # Queue the first linear stage task
        task_repo.create_task(f"task_{project_id}_script", project_id, "project_script")

        return StartProductionResponse(
            project_id=project_id,
            status="production_started",
            message="制片工作流已启动！您可以在项目面板中查看实时进度。",
            estimated_completion_time=None,
        )

    def _create_project_in_db(self, project_id: str, conversation_id: str,
                               outline: ScriptOutline, collected: dict):
        # Prefer LLM-confirmed values, fall back to user-selected values
        episode_count = outline.episode_count or collected.get("episode_count", 20)
        episode_duration = outline.episode_duration or collected.get("episode_duration", "3分钟")
        config = {
            "episode_count": episode_count,
            "episode_duration": episode_duration,
            "genre": collected.get("genre", "都市爱情"),
            "style": collected.get("style_tone", "轻松幽默"),
            "synopsis": outline.synopsis,
            "episodes_detail": outline.episodes_detail,
        }

        project_repo.create_project(
            project_id, outline.title, conversation_id, config, status="in_progress"
        )

        # Create characters with unique IDs
        for i, c in enumerate(outline.characters):
            char_id = f"{project_id}_char_{i + 1:03d}"
            project_repo.create_character(
                char_id, project_id, c["name"], c.get("age", 25),
                c.get("role", "角色"), c.get("description", ""),
                {
                    "face_reference": f"assets/{char_id}_face.png",
                    "costume_references": [f"assets/{char_id}_costume1.png"],
                },
            )

        # Create episodes with titles from LLM outline
        actual_count = episode_count
        llm_titles = outline.episode_titles or []
        for i in range(actual_count):
            ep_id = f"{project_id}_ep_{i + 1:03d}"
            if i < len(llm_titles):
                title = llm_titles[i]
            elif i < len(EPISODE_TITLES):
                title = EPISODE_TITLES[i]
            else:
                title = f"第{i + 1}集"
            project_repo.create_episode(ep_id, project_id, i + 1, title, status="pending")

        # Init agent states
        agent_repo.init_agent_states(project_id)

        # Recalculate progress
        completed = project_repo.get_completed_episode_count(project_id)
        progress = int((completed / actual_count) * 100) if actual_count > 0 else 0
        project_repo.update_project(project_id, progress=progress)

    def _extract_common_preferences(self, info: dict, user_message: str):
        for genre in GENRE_OPTIONS:
            if genre in user_message and "genre" not in info:
                info["genre"] = genre
                break

        # Series type: 真人短剧 vs 动画漫剧
        if "series_type" not in info:
            if any(kw in user_message for kw in ["真人", "实拍", "live-action", "live action"]):
                info["series_type"] = "live-action"
            elif any(kw in user_message for kw in ["动画", "动漫", "二次元", "anime", "animation", "漫剧"]):
                info["series_type"] = "animation"

        episode_count = self._parse_episode_count(user_message)
        if episode_count and "episode_count" not in info:
            info["episode_count"] = episode_count

        episode_duration = self._parse_episode_duration(user_message)
        if episode_duration and "episode_duration" not in info:
            info["episode_duration"] = episode_duration

        for opt in TARGET_AUDIENCE_OPTIONS:
            if opt in user_message:
                info["target_audience"] = opt
                break
        else:
            if "女性向" in user_message and "target_audience" not in info:
                info["target_audience"] = "年轻女性"
            elif "男性向" in user_message and "target_audience" not in info:
                info["target_audience"] = "年轻男性"

    def _parse_episode_count(self, text: str) -> int | None:
        match = re.search(r"(\d{1,3})\s*集", text)
        if match:
            return int(match.group(1))

        cn_map = {
            "八": 8,
            "十": 10,
            "十二": 12,
            "二十": 20,
            "三十": 30,
            "五十": 50,
        }
        for key, value in cn_map.items():
            if f"{key}集" in text:
                return value
        return None

    def _parse_episode_duration(self, text: str) -> str | None:
        range_match = re.search(
            r"(\d{1,2})\s*(?:-|到|~|至)\s*(\d{1,2})\s*分(?:钟)?", text
        )
        if range_match:
            return f"{range_match.group(1)}-{range_match.group(2)}分钟"

        single_match = re.search(r"(\d{1,2})\s*分(?:钟)?(?:左右)?", text)
        if single_match:
            return f"{single_match.group(1)}分钟左右"
        return None

    def _extract_info(self, info: dict, user_message: str, round_num: int):
        """Extract structured info from user's answer and store per-round."""
        if round_num == 0:
            self._extract_common_preferences(info, user_message)
            if "genre" not in info:
                info["genre"] = "都市爱情"
            if "series_type" not in info:
                info["series_type"] = "live-action"
            return

        self._extract_common_preferences(info, user_message)

        # Store each round's answer for context
        info[f"round{round_num}_answers"] = user_message
        # Also keep legacy field for outline prompt compatibility
        if round_num == 1:
            info["phase1_answers"] = user_message
        elif round_num == 2:
            info["phase2_answers"] = user_message
            info["story_background"] = user_message
            for opt in STYLE_TONE_OPTIONS:
                if opt in user_message:
                    info["style_tone"] = opt
                    break
    def _build_outline_message(self, outline: ScriptOutline) -> str:
        chars = "\n".join(
            [f"- {c['name']}：{c['age']}岁，{c['role']}，{c['description']}" for c in outline.characters]
        )
        episodes = "\n".join(
            [f"- 第{e['range']}集：{e['theme']}" for e in outline.episodes_summary]
        )
        return (
            f"根据您的需求，我已生成以下剧本大纲：\n\n"
            f"## 《{outline.title}》\n\n"
            f"**故事梗概**：{outline.synopsis}\n\n"
            f"**主要角色**：\n{chars}\n\n"
            f"**分集概要**：\n{episodes}\n\n"
            f"请确认这个剧本大纲，确认后将进入全自动制片流程。"
        )

    async def stream_next_questions(
        self, collected: dict, round_num: int = 1
    ):
        """Stream question generation with real-time text output.
        Yields (chunk_type, data) tuples:
        - ('text', str): Text chunk to display
        - ('questions', list[QuestionOption]): Parsed questions
        - ('ready_for_outline', bool): True when LLM decides to stop questioning
        - ('done', None): Stream complete
        """
        MAX_ROUNDS = 5
        genre = collected.get("genre", "短剧")
        initial_idea = collected.get("initial_idea", "")
        missing_fields = []
        if "episode_count" not in collected:
            missing_fields.append("集数")
        if "episode_duration" not in collected:
            missing_fields.append("单集时长")
        if "target_audience" not in collected:
            missing_fields.append("目标观众")

        if not is_llm_configured():
            questions, content = self._fallback_questions(collected, round_num)
            yield "text", content
            yield "questions", questions
            yield "ready_for_outline", round_num >= 2
            yield "done", None
            return

        # Build context — always include full collected info so LLM sees everything
        if round_num == 1:
            context = f"用户想制作一部{genre}AI短剧，初始想法是：{initial_idea}"
        else:
            context = (
                f"用户想制作{genre}AI短剧，已知信息："
                f"{json.dumps(collected, ensure_ascii=False)}"
            )

        instruction = (
            '你是 AI 短剧制片顾问，负责和用户对话，明确创作方向。'
            '根据当前已知信息决定：继续追问（"继续追问"），还是信息已经足够可以生成大纲（"准备生成大纲"）。'
            '追问时优先问：核心冲突、主角类型、故事舞台、悬念钩子、人物关系、反转机制、情绪基调、结局倾向。'
            f"如果以下信息缺失且确实影响方案，可以补问：{', '.join(missing_fields) if missing_fields else '无'}。"
            '已明确的信息不要重复问。严禁询问预算、拍摄成本、演员资源、置景成本。'
            '问题要像创作讨论，不要像制片表格。'
        )

        blockbuster_reference = f"\n\n{SHORT_DRAMA_PROMPT_REFERENCE}"

        # Force first round to include episodes and duration questions
        first_round_instruction = ""
        if round_num == 1:
            first_round_instruction = """\n\n【重要】这是第一轮对话，你的问题中必须包含以下两个问题：
1. 总集数（select，选项建议：6集/8集/10集/12集/自定义）
2. 单集时长（select，选项建议：1分钟/2分钟/3分钟/5分钟/自定义）
以上两个问题必须出现，其余问题自由发挥。"""

        at_max_round = round_num >= MAX_ROUNDS
        round_hint = (
            f"\n注意：这是第 {round_num} 轮追问，已达到上限 {MAX_ROUNDS} 轮，必须输出“准备生成大纲”。"
            if at_max_round else f"\n当前是第 {round_num} 轮对话（最多 {MAX_ROUNDS} 轮）。"
        )

        prompt = f"""{context}
{instruction}
{round_hint}
{blockbuster_reference}
{first_round_instruction}

背景约束：
1. 这是 AI 短剧，不是传统长剧；后续会进入 AI 分镜、资产生成和视频生成流程。
2. 问题应帮助模型产出更适合 AI 生成的内容：人物关系清晰、场景集中、钩子强、反转快。
3. 如果用户已经给出集数、单集时长、目标观众，就不要再问这些。
4. 不要问预算。

请严格以如下 JSON 格式输出（不要输出其他任何文字）：
{{
  "开场白": "一句自然的回应和引导语",
  "决定": "继续追问" 或 "准备生成大纲",
  "问题": [
    {{
      "id": "英文ID，如 story_world",
      "问题": "具体自然的问题文本",
      "类型": "select 或 text",
      "选项": ["仅 select 类型需要，2-4 个选项"],
      "占位符": "仅 text 类型需要"
    }}
  ]
}}

判断标准：
- 如果故事方向清晰、核心冲突明确、人物关系有雏形、用户没有新的补充 → 输出“准备生成大纲”，问题留空。
- 否则 → 输出“继续追问”，提出 2-3 个新问题。
- 如果是 select，选项要有明显区分度。
- 确保 JSON 格式正确。"""

        full_response = ""
        try:
            async for chunk in stream_llm(
                [{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1024,
            ):
                full_response += chunk
                yield "text", chunk

            # Parse structured response
            questions, content, decision = self._parse_structured_response(full_response, round_num)
            
            # Determine if ready for outline
            ready_for_outline = (decision == "准备生成大纲") or at_max_round
            
            yield "questions", questions
            yield "ready_for_outline", ready_for_outline
            yield "done", None

        except Exception as e:
            print(f"Stream question generation failed: {e}")
            questions, content = self._fallback_questions(collected, round_num)
            if not full_response:
                yield "text", content
            yield "questions", questions
            yield "ready_for_outline", round_num >= 2
            yield "done", None

    def _parse_structured_response(
        self, response: str, round_num: int
    ) -> tuple[list[QuestionOption], str, str]:
        """Parse structured JSON response from LLM.
        Returns (questions, opening_remark, decision).
        """
        json_str = ""
        
        # Strategy 1: Extract from <response> tags if present
        response_match = re.search(
            r'<response>\s*([\s\S]*?)\s*</response>',
            response,
            re.DOTALL
        )
        if response_match:
            json_str = response_match.group(1).strip()
        
        # Strategy 2: Try to find JSON block in raw response
        if not json_str:
            cleaned = re.sub(r'^```(?:json)?\s*', '', response.strip())
            cleaned = re.sub(r'\s*```$', '', cleaned)
            start = cleaned.find('{')
            if start >= 0:
                depth = 0
                for i in range(start, len(cleaned)):
                    if cleaned[i] == '{':
                        depth += 1
                    elif cleaned[i] == '}':
                        depth -= 1
                        if depth == 0:
                            json_str = cleaned[start:i+1]
                            break
        
        if not json_str:
            return [], "", "继续追问"
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"JSON parse error in structured response: {e}")
            print(f"JSON string was: {json_str[:200]}")
            return [], "", "继续追问"
        
        questions = []
        for q in data.get("问题", []):
            question_text = (q.get("问题") or "").strip()
            if not question_text:
                continue
            question_type = q.get("类型", "text")
            options = q.get("选项") if question_type == "select" else None
            questions.append(
                QuestionOption(
                    id=q.get("id", f"q_{round_num}_{len(questions)}"),
                    question=question_text,
                    type=question_type,
                    options=options,
                    placeholder=q.get("占位符"),
                )
            )
        
        content = data.get("开场白", "让我继续了解您的需求。")
        decision = data.get("决定", "继续追问")
        return questions, content, decision

    def _parse_streamed_questions(
        self, response: str, phase: int
    ) -> list[QuestionOption]:
        """Parse natural language response into structured questions."""
        questions = []
        # Pattern: question text followed by [opt1|opt2|opt3] or __xxx__
        # Split by common question patterns
        lines = response.split("\n")
        current_q = None
        q_id = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Skip opening remarks (usually first 1-2 non-question lines)
            if not current_q and ("？" in line or "?" in line):
                # This looks like a question
                # Check if it has options
                if "[" in line and "]" in line:
                    # Extract question and options
                    q_match = re.match(r"^(.+？)\s*\[(.+)\]", line)
                    if q_match:
                        q_text = q_match.group(1).strip()
                        opts = [o.strip() for o in q_match.group(2).split("|")]
                        questions.append(
                            QuestionOption(
                                id=f"q_{phase}_{q_id}",
                                question=q_text,
                                type="select",
                                options=opts,
                            )
                        )
                        q_id += 1
                        continue
                # Check for text input placeholder
                if "__" in line:
                    q_text = re.sub(r"__[^_]*__", "", line).strip()
                    if q_text:
                        questions.append(
                            QuestionOption(
                                id=f"q_{phase}_{q_id}",
                                question=q_text,
                                type="text",
                                placeholder="请输入...",
                            )
                        )
                        q_id += 1
                        continue
                # Plain question without markers - treat as text input
                if line.endswith("？") or line.endswith("?"):
                    questions.append(
                        QuestionOption(
                            id=f"q_{phase}_{q_id}",
                            question=line,
                            type="text",
                            placeholder="请输入...",
                        )
                    )
                    q_id += 1

        return questions[:3]  # Max 3 questions
