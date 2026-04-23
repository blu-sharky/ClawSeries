# ClawSeries API 文档

## 基础信息

- **Base URL**: `http://localhost:8000/api/v1`
- **数据格式**: JSON
- **字符编码**: UTF-8

---

## 1. 会话管理 (Conversation)

### 1.1 创建新会话

**请求**
```
POST /conversations
```

**请求体**
```json
{
  "initial_idea": "我想做一个都市爱情短剧"
}
```

**响应**
```json
{
  "conversation_id": "conv_abc123",
  "message": {
    "role": "assistant",
    "content": "好的！很高兴为您制作短剧。首先，您想做哪种类型的短剧？",
    "agent_id": "agent_director",
    "questions": [
      {
        "id": "genre",
        "question": "您想做哪种类型的短剧？",
        "type": "select",
        "options": ["都市爱情", "悬疑推理", "古风仙侠", "职场商战"]
      }
    ]
  },
  "state": "collecting_requirements"
}
```

### 1.2 继续会话

**请求**
```
POST /conversations/{conversation_id}/messages
```

**请求体**
```json
{
  "message": "都市爱情，20集"
}
```

**响应**
```json
{
  "conversation_id": "conv_abc123",
  "message": {
    "role": "assistant",
    "content": "...",
    "agent_id": "agent_director",
    "questions": [...]
  },
  "state": "collecting_requirements"
}
```

### 1.3 获取会话历史

**请求**
```
GET /conversations/{conversation_id}
```

**响应**
```json
{
  "conversation_id": "conv_abc123",
  "state": "collecting_requirements",
  "messages": [
    {
      "role": "user",
      "content": "我想做一个都市爱情短剧",
      "timestamp": "2026-04-22T10:00:00Z"
    },
    {
      "role": "assistant",
      "content": "好的！...",
      "timestamp": "2026-04-22T10:00:05Z",
      "agent_id": "agent_director"
    }
  ],
  "collected_info": {
    "episode_count": 20,
    "episode_duration": "3-5分钟",
    "genre": "都市爱情"
  }
}
```

### 1.4 确认并生成剧本大纲

**请求**
```
POST /conversations/{conversation_id}/confirm
```

**请求体**
```json
{
  "confirmed": true
}
```

**响应**
```json
{
  "conversation_id": "conv_abc123",
  "project_id": "proj_xyz789",
  "message": {
    "role": "assistant",
    "content": "剧本大纲已确认！...",
    "agent_id": "agent_director"
  },
  "script_outline": {
    "title": "上海之恋",
    "synopsis": "...",
    "characters": [...],
    "episodes_summary": [...]
  },
  "state": "confirmed"
}
```

### 1.5 最终确认并启动工作流

**请求**
```
POST /conversations/{conversation_id}/start-production
```

**请求体**
```json
{
  "confirmed": true
}
```

**响应**
```json
{
  "project_id": "proj_xyz789",
  "status": "production_started",
  "message": "制片工作流已启动！您可以在项目面板中查看实时进度。",
  "estimated_completion_time": null
}
```

---

## 2. 项目管理 (Project)

### 2.1 获取项目列表

**请求**
```
GET /projects
```

**响应**
```json
{
  "projects": [
    {
      "project_id": "proj_xyz789",
      "title": "上海之恋",
      "status": "in_progress",
      "progress": 35,
      "created_at": "2026-04-22T10:00:00Z",
      "episode_count": 20,
      "completed_episodes": 7,
      "current_stage": "shots_generating",
      "current_agent": "agent_visual",
      "stages": null
    }
  ],
  "total": 1
}
```

### 2.2 获取项目详情

**请求**
```
GET /projects/{project_id}
```

**响应**
```json
{
  "project_id": "proj_xyz789",
  "title": "上海之恋",
  "status": "in_progress",
  "progress": 35,
  "created_at": "2026-04-22T10:00:00Z",
  "config": {
    "episode_count": 20,
    "episode_duration": "3-5分钟",
    "genre": "都市爱情",
    "style": "甜宠"
  },
  "characters": [...],
  "episodes": [...],
  "current_stage": "shots_generating",
  "current_agent": "agent_visual",
  "stages": [
    {
      "stage": "requirements_confirmed",
      "agent_id": "agent_director",
      "status": "completed",
      "title": "需求确认"
    },
    {
      "stage": "script_generating",
      "agent_id": "agent_chief_director",
      "status": "completed",
      "title": "剧本生成中"
    },
    {
      "stage": "script_completed",
      "agent_id": "agent_chief_director",
      "status": "completed",
      "title": "剧本完成"
    }
  ]
}
```

---

## 3. 智能体状态 (Agents)

### 3.1 获取所有智能体状态

**请求**
```
GET /projects/{project_id}/agents
```

**响应**
```json
{
  "agents": [
    {
      "agent_id": "agent_director",
      "name": "项目总监",
      "status": "idle",
      "current_task": null,
      "completed_tasks": 45,
      "total_tasks": 120
    },
    {
      "agent_id": "agent_chief_director",
      "name": "总导演",
      "status": "working",
      "current_task": "编写第8集剧本",
      "completed_tasks": 7,
      "total_tasks": 20
    }
  ]
}
```

### 3.2 获取智能体工作日志

**请求**
```
GET /projects/{project_id}/agents/{agent_id}/logs
```

**响应**
```json
{
  "agent_id": "agent_chief_director",
  "logs": [
    {
      "timestamp": "2026-04-22T10:30:15Z",
      "level": "info",
      "message": "开始编写第8集剧本"
    }
  ]
}
```

### 3.3 获取智能体生产事件

**请求**
```
GET /projects/{project_id}/agents/{agent_id}/events
```

**响应**
```json
{
  "agent_id": "agent_chief_director",
  "events": [
    {
      "id": 42,
      "project_id": "proj_xyz789",
      "episode_id": "ep_008",
      "shot_id": null,
      "agent_id": "agent_chief_director",
      "stage": "script_generating",
      "event_type": "episode_script_completed",
      "title": "第8集剧本完成",
      "message": "已完成《心动时刻》剧本编写",
      "payload": {"scene_count": 5},
      "created_at": "2026-04-22T10:30:25Z"
    }
  ]
}
```

---

## 4. 剧集管理 (Episodes)

### 4.1 获取剧集详情

**请求**
```
GET /projects/{project_id}/episodes/{episode_id}
```

**响应**
```json
{
  "episode_id": "ep_001",
  "episode_number": 1,
  "title": "意外的相遇",
  "status": "completed",
  "progress": 100,
  "duration": "4:32",
  "has_script": true,
  "has_storyboard": true,
  "script": {
    "scenes": [...]
  },
  "storyboard": [...],
  "assets": {"videos": [], "audios": [], "images": []},
  "video_url": "/videos/ep_001.mp4",
  "shots": [...],
  "timeline": [
    {
      "id": 1,
      "project_id": "proj_xyz789",
      "episode_id": "ep_001",
      "agent_id": "agent_chief_director",
      "stage": "script_generating",
      "event_type": "episode_script_completed",
      "title": "第1集剧本完成",
      "message": "已完成剧本编写",
      "created_at": "2026-04-22T10:05:00Z"
    }
  ]
}
```

### 4.2 获取剧集视频

**请求**
```
GET /projects/{project_id}/episodes/{episode_id}/video
```

**响应**
```json
{
  "video_url": "/videos/ep_001.mp4"
}
```

### 4.3 获取剧集执行追踪

**请求**
```
GET /projects/{project_id}/episodes/{episode_id}/traces
```

**响应**
```json
{
  "episode_id": "ep_001",
  "traces": [
    {
      "id": 1,
      "shot_id": "ep_001_shot_1",
      "project_id": "proj_xyz789",
      "agent_id": "agent_visual",
      "stage": "video_generation",
      "prompt_summary": "...",
      "provider_name": "seedance",
      "model_name": "seedance-2.0",
      "output_path": "/renders/ep_001_shot_1.mp4",
      "created_at": "2026-04-22T10:15:00Z"
    }
  ]
}
```

---

## 5. 线性制片控制 (Production Pipeline)

### 5.1 启动制片流程（LangGraph 流式执行）

启动 LangGraph StateGraph 制片流水线，返回 SSE 流式事件。

**请求**
```
POST /projects/{project_id}/start-production
```

**前置条件**: 项目状态为 pending 或 paused

**响应**: SSE 流式事件
```
event: state_update
data: {"current_stage": "script_generating", "status": "in_progress", ...}

event: state_update
data: {"current_stage": "script_completed", "episodes": [...], ...}

event: error
data: {"error": "..."}
```

### 5.2 获取 LangGraph 状态

**请求**
```
GET /projects/{project_id}/state
```

**响应**
```json
{
  "project_id": "proj_xyz789",
  "current_stage": "shots_generating",
  "status": "in_progress",
  "events": [...],
  "errors": [],
  "awaiting_input": false,
  "interrupt_data": null
}
```

### 5.3 恢复中断的制片流程

当视频生成模式为手动时，流程会中断等待人工决策。

**请求**
```
POST /projects/{project_id}/resume
```

**请求体**
```json
{
  "skip": true,
  "continue": false
}
```

**响应**: SSE 流式事件（同 5.1）

### 5.4 继续制片流程

从当前状态继续执行（用于暂停的项目）。

**请求**
```
POST /projects/{project_id}/continue
```

**响应**: SSE 流式事件（同 5.1）


### 5.6 获取项目阶段状态

**请求**
```
GET /projects/{project_id}/stages
```

**响应**
```json
{
  "project_id": "proj_xyz789",
  "stages": [
    {"project_id": "proj_xyz789", "stage": "requirements_confirmed", "status": "completed", "started_at": "...", "completed_at": "...", "error_message": null},
    {"project_id": "proj_xyz789", "stage": "script_generating", "status": "in_progress", "started_at": "...", "completed_at": null, "error_message": null}
  ],
  "current_stage": {"project_id": "proj_xyz789", "stage": "script_generating", "status": "in_progress"}
}
```

### 5.3 获取项目生产时间线

**请求**
```
GET /projects/{project_id}/timeline
```

**响应**
```json
{
  "project_id": "proj_xyz789",
  "timeline": [
    {
      "id": 1,
      "project_id": "proj_xyz789",
      "episode_id": null,
      "shot_id": null,
      "agent_id": "agent_director",
      "stage": "requirements_confirmed",
      "event_type": "production_started",
      "title": "制片流程已启动",
      "message": "项目已创建，即将开始生成剧本...",
      "payload": {},
      "created_at": "2026-04-22T10:00:00Z"
    }
  ]
}
```

### 5.7 阶段接口（已迁移至 LangGraph）

以下接口已由 LangGraph StateGraph 自动编排替代，无需手动调用：

| 接口 | 说明 |
|------|------|
| `POST /projects/{id}/generate-script` | 现由 script_node 自动执行 |
| `POST /projects/{id}/format-script` | 现由 format_node 自动执行 |
| `POST /projects/{id}/generate-assets` | 现由 assets_node 自动执行 |
| `POST /projects/{id}/generate-shots` | 现由 shots_node 自动执行 |
| `POST /projects/{id}/compose` | 现由 project_compose_node 自动执行 |

### 5.8 已废弃接口

| 接口 | 替代方案 |
|------|----------|
| `POST /projects/{id}/run` | 使用 `/start-production` |
| `POST /projects/{id}/episodes/{ep_id}/run` | LangGraph 自动编排 |
| `POST /projects/{id}/episodes/{ep_id}/shots/{shot_id}/run` | 已禁用 |

---

## 6. 系统状态 (System)

### 6.1 获取系统概览

**请求**
```
GET /system/status
```

---

## 7. 设置 (Settings)

### 7.1 获取模型配置

**请求**
```
GET /settings/models
```

### 7.2 更新模型配置

**请求**
```
PUT /settings/models
```

### 7.3 测试连接

**请求**
```
POST /settings/test
```

---

## 8. WebSocket 实时通信

### 8.1 连接端点

```
ws://localhost:8000/ws/{project_id}
```

### 8.2 消息格式

**项目进度更新**
```json
{
  "type": "progress_update",
  "data": {
    "project_id": "proj_xyz789",
    "overall_progress": 36,
    "episode_progress": {
      "episode_id": "ep_002",
      "progress": 68
    }
  }
}
```

**智能体状态更新**
```json
{
  "type": "agent_update",
  "data": {
    "agent_id": "agent_editor",
    "status": "working",
    "current_task": "剪辑第5集"
  }
}
```

**剧集完成通知**
```json
{
  "type": "episode_completed",
  "data": {
    "episode_id": "ep_005",
    "episode_number": 5,
    "title": "心动时刻",
    "video_url": "/videos/ep_005.mp4"
  }
}
```

**项目完成通知**
```json
{
  "type": "project_completed",
  "data": {
    "project_id": "proj_xyz789",
    "title": "上海之恋",
    "total_episodes": 20,
    "completed_at": "2026-04-22T12:00:00Z"
  }
}
```

---

## 9. 状态枚举

### 项目状态 (Project Status)
- `pending` - 等待开始
- `in_progress` - 进行中
- `paused` - 已暂停
- `completed` - 已完成
- `failed` - 失败

### 剧集状态 (Episode Status)
- `pending` - 等待处理
- `scripting` - 剧本编写中
- `storyboarding` - 分镜设计中
- `asset_generating` - 素材生成中
- `rendering` - 渲染中
- `editing` - 剪辑中
- `qc_checking` - 质检中
- `completed` - 已完成
- `failed` - 失败

### 智能体状态 (Agent Status)
- `idle` - 空闲
- `working` - 工作中
- `error` - 错误

### 制片阶段 (Production Stages)
- `requirements_confirmed` - 需求确认
- `script_generating` / `script_completed` - 剧本
- `format_generating` / `format_completed` - 分镜格式化
- `assets_generating` / `assets_completed` - 资产生成
- `shots_generating` / `shots_completed` - 镜头视频
- `episode_composing` / `episode_completed` - 剧集合成
- `project_composing` / `project_completed` - 项目合成

### 五大智能体 (Agents)
| agent_id | 名称 | 职责 |
|----------|------|------|
| `agent_director` | 项目总监 | 全局状态管理、流程控制 |
| `agent_chief_director` | 总导演 | 剧本编写、创作方向 |
| `agent_prompt` | 提示词架构师 | 分镜格式化、Prompt 优化 |
| `agent_visual` | 视觉总监 | 资产生成、视频生成 |
| `agent_editor` | 自动化剪辑师 | 合成、字幕、最终输出 |
