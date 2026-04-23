# Repository Guidelines

ClawSeries is an AI short-drama production platform. Backend: Python FastAPI with LangGraph StateGraph orchestration. Frontend: vanilla JS/HTML/CSS. The system generates scripts, storyboards, assets, and videos for multi-episode short dramas through a 6-stage pipeline.

---

## Architecture & Data Flow

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Routers (backend/routers/)     HTTP endpoints              │
├─────────────────────────────────────────────────────────────┤
│  Services (backend/services/)   Business logic              │
├─────────────────────────────────────────────────────────────┤
│  Repositories (backend/repositories/)  SQLite CRUD          │
├─────────────────────────────────────────────────────────────┤
│  Storage (backend/storage/db.py)  DB connection + schema    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Graphs (backend/graphs/)       LangGraph pipeline          │
├─────────────────────────────────────────────────────────────┤
│  Integrations (backend/integrations/)  External APIs        │
└─────────────────────────────────────────────────────────────┘
```

### Production Pipeline (LangGraph)

```
START → script_node → format_node → assets_node
     → [shots_router: conditional]
     → shots_node (loops per-episode)
     → episode_compose_node (loops per-episode)
     → project_compose_node → END
```

- **6 nodes** in `backend/graphs/nodes/`: script, format, assets, shots, compose
- **3 conditional routers** in `backend/graphs/routers/edge_routers.py`
- **State**: `ProductionState` TypedDict with reducers (`merge_dicts`, `append_list`)
- **Checkpointing**: Separate SQLite DB (`langgraph_checkpoints.db`) to avoid lock contention

### Real-time Communication

1. **WebSocket** (`/ws/{project_id}`): Agent status, stage updates, progress, traces
2. **SSE** (`/api/v1/conversations/.../stream`): LLM streaming for chat/outline generation

### Data Flow

- **Sync path**: Router → Service → Repo → SQLite (via `get_connection()` singleton)
- **Async path**: Router → LangGraph node → Integration (LLM/video) → External API
- **Streaming path**: SSE endpoint → `stream_llm()` → httpx AsyncClient → yield chunks

---

## Key Directories

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI application root |
| `backend/routers/` | HTTP endpoints (10 routers) |
| `backend/services/` | Business logic orchestration (5 services) |
| `backend/repositories/` | SQLite CRUD (7 repos) |
| `backend/graphs/` | LangGraph StateGraph definition |
| `backend/graphs/nodes/` | Pipeline stage implementations |
| `backend/graphs/routers/` | Conditional edge routers |
| `backend/integrations/` | External API wrappers (LLM, image, video, ffmpeg) |
| `backend/storage/` | DB connection singleton + schema |
| `backend/checkpoint/` | LangGraph checkpointer setup |
| `backend/data/` | SQLite DBs, generated assets (gitignored) |
| `frontend/` | Vanilla JS SPA (no build step) |
| `frontend/js/` | 6 JS modules: api, app, chat, project, settings, mock-data |
| `ppt/` | Presentation generation scripts |

---

## Development Commands

```bash
# Install dependencies (uv is required)
uv sync

# Run backend server
uv run uvicorn backend.main:app --reload --port 8000

# Run Python script
uv run python <script.py>

# Type check (if mypy installed)
uv run mypy backend/

# Database location
backend/data/clawseries.db
backend/data/langgraph_checkpoints.db
```

---

## Code Conventions

### Python

- **Async/sync split**: Repos are sync (sqlite3), services mostly sync, integrations async, graph nodes async
- **No ORM**: Raw SQL with `sqlite3.Row` → dict → Pydantic model
- **Singleton DB**: `get_connection()` returns one connection with WAL mode
- **JSON columns**: Stored as TEXT, serialized with `json.dumps(..., ensure_ascii=False)`
- **Error handling**: `HTTPException(status_code=404, detail="中文消息")`
- **Imports**: `sys.path.insert(0, 'backend')` for scripts; normal imports within backend

### LangGraph Nodes

```python
async def script_node(state: ProductionState) -> dict:
    project_id = state["project_id"]
    agent_id = STAGE_AGENT_MAP[ProductionStage.SCRIPT_GENERATING]
    
    # Check precondition
    if not is_stage_completed(project_id, ProductionStage.REQUIREMENTS_CONFIRMED.value):
        init_project_stages(project_id)
    
    # Update stage/agent status
    update_project_stage(project_id, ProductionStage.SCRIPT_GENERATING.value, "in_progress")
    agent_repo.update_agent_state(project_id, agent_id, status="working", ...)
    
    # Do work (LLM calls, etc.)
    ...
    
    # Emit events for observability
    add_production_event(project_id, agent_id, stage, "event_type", title, message)
    
    # Return state updates (partial dict)
    return {"current_stage": ProductionStage.SCRIPT_COMPLETED.value, ...}
```

### Repositories

```python
def get_project(project_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM projects WHERE project_id = ?",
        (project_id,)
    ).fetchone()
    return dict(row) if row else None
```

### Frontend

- **No framework**: Vanilla JS with module pattern
- **API**: `frontend/js/api.js` wraps REST, SSE, WebSocket
- **Mock mode**: `USE_MOCK = false` in api.js
- **Base URL**: `http://localhost:8000/api/v1`

---

## Important Files

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app entry, router registration, startup |
| `backend/storage/db.py` | SQLite singleton, schema DDL (14 tables) |
| `backend/models.py` | Pydantic models, `ProductionStage` enum, stage mappings |
| `backend/graphs/production_graph.py` | StateGraph definition, node wiring |
| `backend/graphs/state.py` | `ProductionState` TypedDict with reducers |
| `backend/routers/execution_langgraph.py` | Active execution engine (LangGraph) |
| `backend/integrations/llm.py` | LLM integration (OpenAI/Google) |
| `backend/prompt_reference.py` | Shared prompt templates (hooks, genres) |
| `pyproject.toml` | Dependencies, Python >=3.11 |
| `API.md` | API documentation |

---

## Runtime/Tooling

- **Python**: >=3.11 (tested on 3.12.13)
- **Package manager**: `uv` (NOT pip)
- **Backend framework**: FastAPI + uvicorn
- **Agent orchestration**: LangGraph >=0.4.0
- **LLM**: OpenAI-compatible APIs or Google Gen AI (Vertex AI)
- **DB**: SQLite with WAL mode
- **Frontend**: No build step, served as static files

---

## Key Patterns

### Stage-Gated Pipeline

Each stage checks `STAGE_PRECONDITIONS` before execution:

```python
# From models.py
STAGE_PRECONDITIONS = {
    ProductionStage.SCRIPT_GENERATING: ProductionStage.REQUIREMENTS_CONFIRMED,
    ProductionStage.FORMAT_GENERATING: ProductionStage.SCRIPT_COMPLETED,
    ProductionStage.ASSETS_GENERATING: ProductionStage.FORMAT_COMPLETED,
    ...
}
```

### Agent-Stage Mapping

```python
# From models.py
STAGE_AGENT_MAP = {
    ProductionStage.SCRIPT_GENERATING: "agent_director",
    ProductionStage.FORMAT_GENERATING: "agent_chief_director",
    ProductionStage.ASSETS_GENERATING: "agent_visual",
    ProductionStage.SHOTS_GENERATING: "agent_prompt",
    ProductionStage.EPISODE_COMPOSING: "agent_editor",
    ...
}
```

### Production Events (Observability)

```python
add_production_event(
    project_id, agent_id, stage,
    "prompt_issued",  # event_type
    "第1集剧本提示词",  # title
    "开始为《意外的相遇》生成剧本",  # message
    episode_id=episode_id,
    payload={"prompt": prompt[:200]}
)
```

### WebSocket Broadcasting

```python
await send_agent_monitor(
    project_id, agent_id,
    stage=ProductionStage.SCRIPT_GENERATING.value,
    output_chunk=chunk,
    episode_id=episode_id,
    event_type="output_chunk",
)
```

---

## Testing & QA

No formal test suite. Manual testing via:

1. Start server: `uv run uvicorn backend.main:app --reload`
2. Open frontend: `frontend/index.html` (or serve via backend static mount)
3. Create project via chat interface
4. Monitor via WebSocket (browser devtools → Network → WS)
5. Check DB: `sqlite3 backend/data/clawseries.db`

---

## Common Tasks

### Adding a New Pipeline Stage

1. Add enum value to `ProductionStage` in `backend/models.py`
2. Add to `STAGE_AGENT_MAP` and `STAGE_PRECONDITIONS`
3. Create node in `backend/graphs/nodes/<name>.py`
4. Add to graph in `backend/graphs/production_graph.py`
5. Update `SCHEMA` in `backend/storage/db.py` if new tables needed

### Adding a New LLM Provider

1. Add provider detection in `backend/integrations/llm.py`
2. Implement streaming function following `stream_llm()` pattern
3. Add to `test_llm_connection()` dispatch

### Modifying Frontend

1. Edit files in `frontend/js/` or `frontend/css/`
2. No build step — refresh browser
3. Check `api.js` for endpoint changes

---

## Database Schema

14 tables (see `backend/storage/db.py`):

- `settings` — Key-value config (LLM API keys, etc.)
- `conversations` — Chat sessions for requirement collection
- `messages` — Conversation messages
- `projects` — Drama projects
- `characters` — Character definitions
- `episodes` — Episode metadata + script/storyboard JSON
- `shots` — Shot definitions
- `tasks` — Task queue (legacy)
- `agent_states` — 5 agent status per project
- `agent_logs` — Agent log entries
- `shot_traces` — Observability traces
- `production_events` — Structured event stream
- `assets` — Asset metadata
- `project_stages` — Stage status tracking

---

## Notes

- **Two execution engines**: `execution.py` (legacy polling) and `execution_langgraph.py` (active). Both registered in `main.py`, but LangGraph routes override due to import order.
- **Separate checkpoint DB**: LangGraph uses `langgraph_checkpoints.db` to avoid SQLite lock contention with main app DB.
- **Chinese UI**: All user-facing messages in Chinese.
- **No auth**: API is open (CORS `*`). Intended for local/single-user deployment.
