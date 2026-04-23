/**
 * 模拟数据 - 后端未启动时使用的前端 mock 数据
 */

const MOCK = {
    // 会话对话流程
    conversationPhases: [
        {
            phase: "genre",
            assistantMsg: "好的！很高兴为您制作短剧。首先，您想做哪种类型的短剧？",
            questions: [
                { id: "genre", question: "您想做哪种类型的短剧？", type: "select", options: ["都市爱情", "悬疑推理", "古风仙侠", "职场商战"] }
            ]
        },
        {
            phase: "basic_info",
            assistantMsg: "不错的选择！接下来让我了解一些基本信息。",
            questions: [
                { id: "episode_count", question: "您计划制作多少集？", type: "select", options: ["10集", "20集", "30集", "50集"] },
                { id: "episode_duration", question: "每集大概多长时间？", type: "select", options: ["1-2分钟", "3-5分钟", "5-10分钟"] },
                { id: "target_audience", question: "目标观众是？", type: "select", options: ["年轻女性", "年轻男性", "全年龄向", "中年群体"] }
            ]
        },
        {
            phase: "detail_setting",
            assistantMsg: "很好！现在让我了解一下更具体的设定。",
            questions: [
                { id: "story_background", question: "您希望故事发生在什么背景？", type: "text", placeholder: "例如：现代都市上海、架空仙界..." },
                { id: "style_tone", question: "您偏好什么风格基调？", type: "select", options: ["轻松幽默", "紧张刺激", "温馨治愈", "暗黑深沉"] },
                { id: "special_elements", question: "有没有特别想加入的元素？", type: "text", placeholder: "例如：重生、复仇、霸道总裁..." }
            ]
        }
    ],

    // 剧本模板
    scriptTemplates: {
        "都市爱情": {
            title: "上海之恋",
            synopsis: "职场新人林小夏在上海打拼时，意外邂逅了集团继承人陆景琛。从欢喜冤家到相知相爱，两人经历了职场阴谋、家族阻挠、误会分离，最终携手走向幸福。",
            characters: [
                { name: "林小夏", age: 24, role: "女主角", description: "市场部新人，活泼开朗，正义感强" },
                { name: "陆景琛", age: 28, role: "男主角", description: "集团继承人，外冷内热，心思缜密" },
                { name: "苏婉清", age: 26, role: "女配角", description: "名门千金，心机深沉" },
                { name: "周子轩", age: 27, role: "男配角", description: "林小夏的青梅竹马，暖男律师" }
            ],
            episodes_summary: [
                { range: "1-5", theme: "相遇与误会" },
                { range: "6-10", theme: "相知与心动" },
                { range: "11-15", theme: "波折与考验" },
                { range: "16-20", theme: "重逢与圆满" }
            ]
        },
        "悬疑推理": {
            title: "暗夜追踪",
            synopsis: "天才犯罪心理学教授顾言，被卷入一起连环失踪案。随着调查深入，他发现所有线索都指向十年前的一桩旧案...",
            characters: [
                { name: "顾言", age: 32, role: "男主角", description: "犯罪心理学教授，冷静理性" },
                { name: "沈薇", age: 28, role: "女主角", description: "刑侦记者，胆大心细" },
                { name: "韩墨", age: 35, role: "反派", description: "神秘企业家，心思难测" }
            ],
            episodes_summary: [
                { range: "1-5", theme: "案件初现" },
                { range: "6-10", theme: "层层迷雾" },
                { range: "11-15", theme: "真相浮现" },
                { range: "16-20", theme: "终局对决" }
            ]
        },
        "古风仙侠": {
            title: "苍穹诀",
            synopsis: "废柴少女叶灵溪意外觉醒上古血脉，踏上修仙之路。她与冷面仙尊之间的宿命纠葛，跨越千年的爱恨情仇...",
            characters: [
                { name: "叶灵溪", age: 18, role: "女主角", description: "活泼少女，上古血脉觉醒者" },
                { name: "凤九渊", age: 500, role: "男主角", description: "仙界至尊，冷面寡言" },
                { name: "墨尘", age: 200, role: "男配角", description: "魔族王子，亦正亦邪" }
            ],
            episodes_summary: [
                { range: "1-5", theme: "血脉觉醒" },
                { range: "6-10", theme: "仙门试炼" },
                { range: "11-15", theme: "正邪之战" },
                { range: "16-20", theme: "宿命终章" }
            ]
        },
        "职场商战": {
            title: "逆风翻盘",
            synopsis: "前投行精英陈默被合伙人背叛，失去一切后从底层重新开始，用智慧与胆识一步步夺回属于自己的帝国。",
            characters: [
                { name: "陈默", age: 30, role: "男主角", description: "前投行精英，沉稳果决" },
                { name: "方晓薇", age: 28, role: "女主角", description: "创业公司CEO，雷厉风行" },
                { name: "赵鹏飞", age: 35, role: "反派", description: "投行合伙人，阴险狡诈" }
            ],
            episodes_summary: [
                { range: "1-5", theme: "跌入谷底" },
                { range: "6-10", theme: "暗中布局" },
                { range: "11-15", theme: "正面交锋" },
                { range: "16-20", theme: "王者归来" }
            ]
        }
    },

    // 智能体定义
    agents: [
        { agent_id: "agent_director", name: "项目总监", icon: "PD", tasks_total: 120 },
        { agent_id: "agent_chief_director", name: "总导演", icon: "CD", tasks_total: 20 },
        { agent_id: "agent_visual", name: "视觉总监", icon: "VC", tasks_total: 40 },
        { agent_id: "agent_prompt", name: "提示词架构师", icon: "PA", tasks_total: 80 },
        { agent_id: "agent_editor", name: "自动化剪辑师", icon: "AE", tasks_total: 20 }
    ],

    // 剧集标题
    episodeTitles: [
        "意外的相遇", "电梯风波", "不打不相识", "暗生情愫", "心动的瞬间",
        "第一次约会", "甜蜜日常", "职场风波", "误会重重", "信任危机",
        "真相大白", "冰释前嫌", "患难见真情", "暗中守护", "命运转折",
        "最终抉择", "破茧重生", "勇敢面对", "携手并进", "幸福结局",
        "新的开始", "并肩作战", "风雨同路", "拨云见日", "逆风翻盘",
        "曙光初现", "步步为营", "绝地反击", "峰回路转", "大结局"
    ],

    // 智能体日志模板
    agentLogs: {
        agent_director: [
            { level: "info", message: "检查各环节进度" },
            { level: "info", message: "调度 API 负载均衡" },
            { level: "success", message: "任务分配完成" },
            { level: "info", message: "监控渲染队列状态" }
        ],
        agent_chief_director: [
            { level: "info", message: "开始编写第8集剧本" },
            { level: "info", message: "生成分镜：场景1 - 办公室" },
            { level: "success", message: "分镜生成完成，共12个镜头" },
            { level: "info", message: "设置第8集结尾悬念" },
            { level: "success", message: "剧本编写完成" }
        ],
        agent_visual: [
            { level: "info", message: "生成角色三视图：林小夏" },
            { level: "success", message: "三视图生成完成：林小夏" },
            { level: "info", message: "生成场景素材：陆家嘴写字楼" },
            { level: "info", message: "锁定角色面部特征" },
            { level: "success", message: "视觉素材生成完成" }
        ],
        agent_prompt: [
            { level: "info", message: "将文学分镜转化为 Prompt" },
            { level: "info", message: "优化镜头提示词" },
            { level: "success", message: "Prompt 矩阵生成完成" },
            { level: "info", message: "应用避坑规则" }
        ],
        agent_editor: [
            { level: "info", message: "开始剪辑第5集" },
            { level: "info", message: "拼接分镜片段" },
            { level: "info", message: "添加 BGM" },
            { level: "info", message: "对齐字幕" },
            { level: "success", message: "剪辑完成，开始压制" }
        ]
    }
};
