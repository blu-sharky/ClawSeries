"""Shared prompt reference blocks for AI短剧 content generation."""

HOT_HOOK_REFERENCE = """爆点钩子参考（学习这种一句话抓眼球的叙事方式、极端冲突、身份反转、禁忌感和因果倒置；不要直接照抄题目或情节）：
- 固执奶奶听不懂人话。省考前，我嘱咐别碰我东西。她转头给我笔袋里塞了张小抄。考试时，我被判定为作弊。爸爸和弟弟说要体谅老人苦心。
- 哥哥是全村第一个大学生，庆功宴上妈妈将老鼠药下在了菜里毒死了村里剩下的人，越过哥哥的尸体她抬眼看向我藏身的衣柜，忘了这里还有一只小老鼠…
- 邻居要吸我家气运，可我爸是杀破狼我妈是极阴体我哥霉运缠身。
- 重生后，我默默换成真硫酸，只听到校花惨叫，直播中断！！
- 高考那天，我弟绑定的天才系统果然失效了。而我凭借自己的实力考上了华清。我妈对招生办的人说让弟弟顶替我。
- 高考满分750妹妹考了751，原因她绑定了分数掠夺系统，而不巧我是个会控分的学霸。
- 渣男每背叛我一次，尺寸就减少0.5，最后竟然缩进......"""

SHORT_DRAMA_PROMPT_REFERENCE = f"""{HOT_HOOK_REFERENCE}

爆款短剧题材参考（可根据用户偏好推荐或启发创作方向）：

一、复仇逆袭
公式：重生/底层反杀+职业压制+心理博弈
参考钩子：
- 手术台上，她看着麻醉中的仇人，悄悄调快输血速度：“这一世，换你体会大出血的滋味。”
- 千金炫耀哈佛录取书时，保姆女儿打开投影仪：“不好意思，我是今年面试官。”
- 深夜，渣男手机自动播放已自杀女友的声音：“检测到您第100次撒谎，电击程序启动。”

二、爱情陷阱
公式：人机恋/婆媳战争/替身文学+细思极恐+反套路
参考钩子：
- 男友的浪漫转账备注突然变成：“第3次测试，人类果然会为钱原谅背叛。”
- 新娘当众播放录音：“您当年在牌坊下私会道士的事，要请族老们评评吗？”
- 总裁甩来支票：“滚吧替身。”她反手亮出股权书：“忘了说，您白月光公司被我收购了。”

三、悬疑脑洞
公式：楚门世界/时间悖论/数字幽灵+高智商对抗
参考钩子：
- 女儿在沙发缝发现剧本：《幸福家庭真人秀》第365集——今日剧情：假装爱她。
- 凶案现场DNA检测报告弹出：“与受害者99.9%匹配——样本来源：2035年的您。”
- 遗像前的iPad突然亮起：“您特别关心的@小雨 刚刚点赞了这条殡仪馆定位。”

四、职业反差
公式：阴间职业/赛博玄学/平民英雄+禁忌交易+黑色幽默
参考钩子：
- 顶流明星深夜敲门：“求您帮我画张活人遗照，要像死了三天那种。”
- 师父敲着木鱼念：“404报错是业障，需诵《硅谷心经》三遍。”
- 警察拦车检查时，他猛拍保温箱：“超时扣20，国宝也不行！”

五、奇幻惊悚（极致脑洞）
公式：灵异直播/末日日常/跨物种共生+因果交易
参考钩子：
- 榜一大哥ID突然变红：“感谢您的100亿打赏，已为您父亲延寿10年（注：取自您儿子）。”"""

CHARACTER_SHEET_ANIMATION_TEMPLATE = """best quality, masterpiece, character design reference sheet, pure white background, same character shown in 4 views arranged horizontally left to right, {name}, {role}, {description}.

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

CHARACTER_SHEET_LIVE_ACTION_TEMPLATE = """best quality, masterpiece, photorealistic character design reference sheet, pure white background, same person shown in 4 views arranged horizontally left to right, {name}, {role}, {description}.

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


def build_character_sheet_prompt(
    name: str, role: str, description: str, series_type: str,
    age: int | str | None = None, gender: str | None = None,
) -> str:
    template = (
        CHARACTER_SHEET_ANIMATION_TEMPLATE
        if series_type == "animation"
        else CHARACTER_SHEET_LIVE_ACTION_TEMPLATE
    )
    details = []
    if age:
        details.append(f"Age: {age}")
    if gender:
        details.append(f"Gender: {gender}")
    details.append(f"Detailed character background: {description}")
    return template.format(name=name, role=role, description=". ".join(details))


def build_scene_asset_prompt(scene_name: str, scene_descriptions: list[str] | None, series_type: str) -> str:
    style = (
        "anime style establishing shot, vibrant, cel-shaded, cinematic composition, illustration"
        if series_type == "animation"
        else "photorealistic establishing shot, cinematic, natural lighting, high quality, wide angle"
    )
    context_items = [d.strip() for d in (scene_descriptions or []) if d and d.strip()]
    context = ""
    if context_items:
        context = " Visual context from the script: " + " | ".join(context_items[:4])
    return (
        f"{scene_name}, {style}. "
        "Create a clear environment reference image of this location, showing the physical space, layout, lighting, atmosphere, and production design. "
        "Use any script context only to infer the place design; do not render plot events, character action, readable screen content, subtitles, labels, logos, or watermarks."
        f"{context}"
    )


def build_shot_dual_prompt_request(
    shot: dict,
    storyboard_entry: dict | None,
    scene: dict | None,
    appearing_characters: list[dict],
    series_type: str = "live-action",
) -> tuple[list[dict], dict]:
    """Build LLM messages for generating per-shot image_prompt and video_prompt.

    Returns (messages, context_info) where messages is the LLM chat messages.
    """
    import json as _json

    shot_number = shot.get("shot_number", "?")
    description = shot.get("description", "")
    camera_movement = shot.get("camera_movement", "")
    duration = shot.get("duration", "")

    # Build dialogue text
    dialogues = []
    if storyboard_entry:
        dialogues = storyboard_entry.get("dialogues", [])
    elif scene:
        dialogues = scene.get("dialogues", [])

    dialogue_lines = []
    for d in dialogues:
        char = d.get("character", "")
        line = d.get("line", "")
        emotion = d.get("emotion", "")
        if line:
            dialogue_lines.append(f"{char}（{emotion}）：{line}" if emotion else f"{char}：{line}")
    dialogue_text = "\n".join(dialogue_lines)

    # Build scene info
    scene_info = ""
    if scene:
        parts = []
        if scene.get("location"):
            parts.append(f"地点：{scene['location']}")
        if scene.get("time_of_day"):
            parts.append(f"时间：{scene['time_of_day']}")
        if scene.get("description"):
            parts.append(f"场景描述：{scene['description']}")
        if scene.get("actions"):
            parts.append(f"动作：{_json.dumps(scene['actions'], ensure_ascii=False)}")
        scene_info = "\n".join(parts)
    elif description:
        scene_info = f"镜头描述：{description}"

    # Build character details
    char_details = []
    for c in appearing_characters:
        detail = {"name": c.get("name", "")}
        if c.get("description"):
            detail["description"] = c["description"]
        if c.get("age"):
            detail["age"] = c["age"]
        if c.get("role"):
            detail["role"] = c["role"]
        if c.get("anchor_prompt"):
            detail["visual_anchor"] = c["anchor_prompt"]
        char_details.append(detail)

    style_note = ""
    if series_type == "animation":
        style_note = "（动画漫剧风格：anime style, cel-shaded, vibrant colors）"
    else:
        style_note = "（真人短剧风格：photorealistic, cinematic lighting, natural）"

    system_msg = {
        "role": "system",
        "content": (
            "你是一个专业的AI短剧画面提示词工程师。你生成的提示词会直接影响视频画面质量。\n\n"
            "【核心原则】\n"
            "- 提示词必须用英文输出（给AI模型用）\n"
            "- 只描述能直接看到/听到的内容，不要使用文学化的修辞、比喻、意境描述\n"
            "- 不需要描述背景环境设定（已由参考图片提供）\n"
            "- 当前视频链路固定为 8 秒单镜头，提示词必须服务于 8 秒内可完成的动作与信息量\n"
            "- 台词/对话内容必须体现在提示词中\n\n"
            "【image_prompt 规则（给图片生成模型 Nano Banana Pro）】\n"
            "- 这张图片是视频镜头的首帧（first frame），必须精确呈现该镜头开始瞬间的画面状态\n"
            "- 描述画面中人物的具体外观：位置、表情、服装细节、动作姿态（必须是动作的起始姿态，而非中间或结束姿态）\n"
            "- 如果有台词，描述人物说话时的表情和口型\n"
            "- 禁止生成任何叠加文字：不要标题字、不要居中大字、不要字幕、不要 caption、不要 logo、不要 watermark\n"
            "- 不要描述摄影机运动，这是静态首帧图片\n"
            f"- 风格标注：{style_note}\n\n"
            "【video_prompt 规则（给视频生成模型 VEO）】\n"
            "- 必须使用镜头语言：camera angle（俯拍/仰拍/平视）、camera movement（dolly in/out、pan left/right、tilt、tracking shot、static）、transition（cut、dissolve）\n"
            "- 描述画面中人物的具体动作和表情变化过程\n"
            "- 如果有台词，必须使用 spoken dialogue 标注，且 spoken dialogue 的内容必须明确写成中文台词，不要写英文对白、不要写拼音、不要写“Chinese dialogue”这种占位说明\n"
            "- 强制要求：视频里任何可听见的人物对白都必须是中文；如果场景不需要人物说话，就不要凭空添加对白\n"
            "- 描述画面节奏：slow motion、normal speed、quick cut 等\n"
            "- 必须按 8-second single shot 来写，不要暗示超过 8 秒才能完成的大段情节或多次复杂换景\n"
            f"- 风格标注：{style_note}\n\n"
            "【输出格式 - 绝对遵守】\n"
            "直接输出纯JSON，禁止使用markdown代码块。\n"
            '{"image_prompt": "英文图片提示词...", "video_prompt": "英文视频提示词..."}'
        ),
    }

    user_content = f"""请为以下镜头生成 image_prompt 和 video_prompt：

【镜头信息】
- 镜头编号：{shot_number}
- 原始描述：{description}
- 摄影机运动：{camera_movement}
- 时长：{duration}

【场景详情】
{scene_info}

【台词/对话】
{dialogue_text if dialogue_text else "（无台词）"}

【出场角色】
{_json.dumps(char_details, ensure_ascii=False, indent=2) if char_details else "（无特定角色）"}

请输出JSON："""

    messages = [system_msg, {"role": "user", "content": user_content}]

    context_info = {
        "shot_number": shot_number,
        "dialogue_count": len(dialogue_lines),
        "character_count": len(appearing_characters),
        "has_scene": scene is not None,
    }

    return messages, context_info


def build_default_dual_prompts(shot: dict, storyboard_entry: dict | None = None) -> dict:
    """Fallback dual prompts when LLM is unavailable."""
    desc = shot.get("description", "")
    camera = shot.get("camera_movement", "") or (storyboard_entry or {}).get("camera_movement", "")
    dialogues = (storyboard_entry or {}).get("dialogues", [])
    dialogue_text = " ".join(d.get("line", "") for d in dialogues if d.get("line"))

    image_prompt = f"{desc}, first frame of video shot, cinematic film still, no text overlay, no title text, no large centered text, no subtitles, no captions, no logo, no watermark"
    if dialogue_text:
        image_prompt += f", dialogue: {dialogue_text[:150]}"

    video_prompt = desc
    if camera:
        video_prompt += f", {camera} camera movement"
    if dialogue_text:
        video_prompt += f", spoken dialogue: {dialogue_text[:150]}"

    return {"image_prompt": image_prompt, "video_prompt": video_prompt}
