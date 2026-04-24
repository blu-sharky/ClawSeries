"""
Data models for ClawSeries API.
Includes production stage definitions and preconditions.
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


# === Production Stage Definitions ===
# These define the strict linear pipeline.
# Each stage has a precondition: the previous stage must have produced its output.

class ProductionStage(str, Enum):
    # Project-level stages
    REQUIREMENTS_CONFIRMED = "requirements_confirmed"
    SCRIPT_GENERATING = "script_generating"
    SCRIPT_COMPLETED = "script_completed"
    FORMAT_GENERATING = "format_generating"
    FORMAT_COMPLETED = "format_completed"
    ASSETS_GENERATING = "assets_generating"
    ASSETS_COMPLETED = "assets_completed"
    # Episode-level stages
    SHOTS_GENERATING = "shots_generating"
    SHOTS_COMPLETED = "shots_completed"
    EPISODE_COMPOSING = "episode_composing"
    EPISODE_COMPLETED = "episode_completed"
    # Final project stage
    PROJECT_COMPOSING = "project_composing"
    PROJECT_COMPLETED = "project_completed"


# Stage → agent mapping (which agent owns each stage)
STAGE_AGENT_MAP = {
    ProductionStage.REQUIREMENTS_CONFIRMED: "agent_director",
    ProductionStage.SCRIPT_GENERATING: "agent_chief_director",
    ProductionStage.SCRIPT_COMPLETED: "agent_chief_director",
    ProductionStage.FORMAT_GENERATING: "agent_prompt",
    ProductionStage.FORMAT_COMPLETED: "agent_prompt",
    ProductionStage.ASSETS_GENERATING: "agent_visual",
    ProductionStage.ASSETS_COMPLETED: "agent_visual",
    ProductionStage.SHOTS_GENERATING: "agent_visual",
    ProductionStage.SHOTS_COMPLETED: "agent_visual",
    ProductionStage.EPISODE_COMPOSING: "agent_editor",
    ProductionStage.EPISODE_COMPLETED: "agent_editor",
    ProductionStage.PROJECT_COMPOSING: "agent_editor",
    ProductionStage.PROJECT_COMPLETED: "agent_editor",
}


# Precondition: what must be true before a stage can start
STAGE_PRECONDITIONS = {
    ProductionStage.SCRIPT_GENERATING: ProductionStage.REQUIREMENTS_CONFIRMED,
    ProductionStage.FORMAT_GENERATING: ProductionStage.SCRIPT_COMPLETED,
    ProductionStage.ASSETS_GENERATING: ProductionStage.FORMAT_COMPLETED,
    ProductionStage.SHOTS_GENERATING: ProductionStage.ASSETS_COMPLETED,
    ProductionStage.EPISODE_COMPOSING: ProductionStage.SHOTS_COMPLETED,
    ProductionStage.PROJECT_COMPOSING: ProductionStage.EPISODE_COMPLETED,
}


# Which task_type in the task queue maps to which stages
TASK_TYPE_TO_STAGE = {
    "project_script": ProductionStage.SCRIPT_GENERATING,
    "project_format": ProductionStage.FORMAT_GENERATING,
    "project_assets": ProductionStage.ASSETS_GENERATING,
    "episode_shot_video": ProductionStage.SHOTS_GENERATING,
    "episode_compose": ProductionStage.EPISODE_COMPOSING,
    "project_compose": ProductionStage.PROJECT_COMPOSING,
}


class ProjectStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class EpisodeStatus(str, Enum):
    PENDING = "pending"
    SCRIPTING = "scripting"
    STORYBOARDING = "storyboarding"
    ASSET_GENERATING = "asset_generating"
    RENDERING = "rendering"
    EDITING = "editing"
    QC_CHECKING = "qc_checking"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    ERROR = "error"


class ConversationState(str, Enum):
    COLLECTING_REQUIREMENTS = "collecting_requirements"
    AWAITING_FINAL_CONFIRMATION = "awaiting_final_confirmation"
    CONFIRMED = "confirmed"
    PRODUCTION_STARTED = "production_started"


# Request models
class CreateConversationRequest(BaseModel):
    initial_idea: str


class SendMessageRequest(BaseModel):
    message: str


class ConfirmRequest(BaseModel):
    confirmed: bool


class QuestionOption(BaseModel):
    id: str
    question: str
    type: str
    options: Optional[List[str]] = None
    placeholder: Optional[str] = None


class Message(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None
    questions: Optional[List[QuestionOption]] = None
    agent_id: Optional[str] = None  # Which agent is speaking

# Response models
class CreateConversationResponse(BaseModel):
    conversation_id: str
    message: Message
    state: ConversationState


class SendMessageResponse(BaseModel):
    conversation_id: str
    message: Message
    state: ConversationState


class ConversationDetail(BaseModel):
    conversation_id: str
    state: ConversationState
    messages: List[Dict[str, Any]]
    collected_info: Dict[str, Any]


class Character(BaseModel):
    character_id: str
    name: str
    age: int
    role: str
    description: str
    visual_assets: Optional[Dict[str, Any]] = None


class EpisodeSummary(BaseModel):
    episode_id: str
    episode_number: int
    title: str
    status: str
    progress: Optional[int] = None
    duration: Optional[str] = None
    video_url: Optional[str] = None


class ProjectSummary(BaseModel):
    project_id: str
    title: str
    status: str
    progress: int
    created_at: str
    episode_count: int
    completed_episodes: int


class ProjectDetail(BaseModel):
    project_id: str
    title: str
    status: str
    progress: int
    created_at: str
    config: Dict[str, Any]
    characters: List[Character]
    episodes: List[EpisodeSummary]


class AgentInfo(BaseModel):
    agent_id: str
    name: str
    status: str
    current_task: Optional[str] = None
    completed_tasks: int
    total_tasks: int


class AgentLog(BaseModel):
    timestamp: str
    level: str
    message: str


class ScriptOutline(BaseModel):
    title: str
    synopsis: str
    characters: List[Dict[str, Any]]
    episodes_summary: List[Dict[str, Any]]


class ConfirmResponse(BaseModel):
    conversation_id: str
    project_id: str
    message: Message
    script_outline: ScriptOutline
    state: ConversationState


class StartProductionResponse(BaseModel):
    project_id: str
    status: str
    message: str
    estimated_completion_time: Optional[str] = None


class SystemStatus(BaseModel):
    status: str
    active_projects: int
    queue_length: int
    api_status: Dict[str, str]
    resources: Dict[str, str]


# Settings models
class LLMProviderConfig(BaseModel):
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = "gpt-4o"


class VideoProviderConfig(BaseModel):
    provider: str = "seedance"
    base_url: str = ""
    api_key: str = ""
    model: str = "seedance-2.0"


class ImageProviderConfig(BaseModel):
    provider: str = "openai"  # openai, google_genai, siliconflow, stability, custom
    base_url: str = ""
    api_key: str = ""
    model: str = "dall-e-3"  # dall-e-3, imagen-4.0-generate-001, Kwai-Kolors/Kolors, etc.
    image_size: str = "1024x1024"
    num_inference_steps: int = 20
    guidance_scale: float = 7.5


class GoogleCloudConfig(BaseModel):
    project: str = ""
    location: str = "us-central1"


class ModelsConfig(BaseModel):
    llm: Optional[LLMProviderConfig] = None
    image: Optional[ImageProviderConfig] = None
    video: Optional[VideoProviderConfig] = None
    google: Optional[GoogleCloudConfig] = None
    video_generation_mode: str = "manual"
    video_demo_mode: bool = False
    image_demo_mode: bool = False


class TestConnectionRequest(BaseModel):
    provider_type: str  # "llm", "image", or "video"


# === Production Event Model ===
class ProductionEventInfo(BaseModel):
    event_id: int
    project_id: str
    episode_id: Optional[str] = None
    shot_id: Optional[str] = None
    agent_id: str
    stage: str
    event_type: str
    title: str
    message: str
    payload: Optional[Dict[str, Any]] = None
    created_at: str


# === Asset Model ===
class AssetInfo(BaseModel):
    asset_id: str
    project_id: str
    episode_id: Optional[str] = None
    type: str  # character, scene, prop
    name: str
    description: str
    prompt: Optional[str] = None
    image_path: Optional[str] = None
    anchor_prompt: Optional[str] = None
    reference_image_path: Optional[str] = None
    created_at: Optional[str] = None


# === Stage Info for API responses ===
class StageInfo(BaseModel):
    stage: str
    agent_id: str
    status: str  # pending, in_progress, completed, failed
    title: str
    description: Optional[str] = None


# === Project Detail extended with stages ===
class ProjectSummaryExtended(BaseModel):
    project_id: str
    title: str
    status: str
    progress: int
    created_at: str
    episode_count: int
    completed_episodes: int
    current_stage: Optional[str] = None
    current_agent: Optional[str] = None
    stages: Optional[List[StageInfo]] = None