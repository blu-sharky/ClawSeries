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
