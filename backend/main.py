"""
ClawSeries Real Backend - AI短剧自动化制片平台后端服务
SQLite-backed, real state, real task graph.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import conversations, projects, agents, episodes, system, websocket, settings, stream, dubbing
from storage.db import init_db
from config import RENDERS_DIR, OUTPUTS_DIR, ASSETS_DIR, DUBBING_DIR
import uvicorn
from pathlib import Path

app = FastAPI(
    title="ClawSeries API",
    description="AI短剧自动化制片平台 API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file serving for generated assets
for d in [RENDERS_DIR, OUTPUTS_DIR, ASSETS_DIR, DUBBING_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app.mount("/videos", StaticFiles(directory=str(OUTPUTS_DIR)), name="videos")
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
app.mount("/renders", StaticFiles(directory=str(RENDERS_DIR)), name="renders")
app.mount("/dubbing", StaticFiles(directory=str(DUBBING_DIR)), name="dubbing")

# Register routes
app.include_router(conversations.router, prefix="/api/v1", tags=["会话管理"])
app.include_router(projects.router, prefix="/api/v1", tags=["项目管理"])
app.include_router(agents.router, prefix="/api/v1", tags=["智能体状态"])
app.include_router(episodes.router, prefix="/api/v1", tags=["剧集管理"])
app.include_router(system.router, prefix="/api/v1", tags=["系统状态"])
app.include_router(settings.router, prefix="/api/v1", tags=["设置"])
from routers import execution_langgraph as execution
app.include_router(execution.router, prefix="/api/v1", tags=["执行控制"])
app.include_router(stream.router, prefix="/api/v1", tags=["流式输出"])
app.include_router(dubbing.router, prefix="/api/v1", tags=["配音"])
app.include_router(websocket.router, tags=["WebSocket"])


@app.on_event("startup")
async def startup():
    init_db()
    # Start the task worker
    from workers.task_worker import start_worker
    import asyncio
    asyncio.create_task(start_worker())

@app.get("/")
async def root():
    return {"message": "ClawSeries API", "version": "2.0.0"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
