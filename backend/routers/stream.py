"""
SSE streaming router for conversation responses.
Real-time streaming with progressive text output.
"""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from models import SendMessageRequest, ConversationState
from repositories import conversation_repo
from services.conversation_service import ConversationService

router = APIRouter()
conversation_service = ConversationService()


def _sse(data: dict) -> dict:
    """Wrap data in SSE format."""
    return {"data": json.dumps(data, ensure_ascii=False)}


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(conversation_id: str, request: SendMessageRequest):
    """Stream assistant responses with real-time text output."""
    conv = conversation_repo.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    collected = (
        json.loads(conv["collected_info"])
        if isinstance(conv["collected_info"], str)
        else (conv["collected_info"] or {})
    )

    async def event_generator():
        try:
            now = datetime.utcnow().isoformat() + "Z"
            conversation_repo.add_message(conversation_id, "user", request.message)
            conversation_service._extract_info(collected, request.message, collected.get("round_num", 0))
            round_num = collected.get("round_num", 0) + 1
            collected["round_num"] = round_num
            conversation_repo.update_conversation(conversation_id, collected_info=collected)

            # Stream next questions — LLM decides whether to continue
            questions = []
            ready_for_outline = False
            async for event_type, data in conversation_service.stream_next_questions(collected, round_num):
                if event_type == "text":
                    yield _sse({
                        "content": data,
                        "done": False,
                        "agent_id": "agent_director",
                    })
                elif event_type == "questions":
                    questions = data
                elif event_type == "ready_for_outline":
                    ready_for_outline = data
                elif event_type == "done":
                    conversation_repo.add_message(
                        conversation_id, "assistant", "",
                        questions_json=[q.model_dump() for q in questions],
                    )
                    if ready_for_outline:
                        # Transition to outline generation
                        conversation_repo.update_conversation(
                            conversation_id,
                            state="generating_outline",
                            collected_info=collected,
                        )
                        yield _sse({
                            "done": True,
                            "state": "ready_for_outline",
                            "message": {
                                "questions": [q.model_dump() for q in questions],
                                "agent_id": "agent_director",
                            },
                        })
                    else:
                        yield _sse({
                            "done": True,
                            "state": ConversationState.COLLECTING_REQUIREMENTS.value,
                            "message": {
                                "questions": [q.model_dump() for q in questions],
                                "agent_id": "agent_director",
                            },
                        })
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield _sse({"error": str(e), "done": True})

    return EventSourceResponse(event_generator())


@router.post("/conversations/{conversation_id}/generate-outline")
async def generate_outline(conversation_id: str):
    """Generate outline from collected info. Called when user skips or LLM decides to stop."""
    conv = conversation_repo.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    collected = (
        json.loads(conv["collected_info"])
        if isinstance(conv["collected_info"], str)
        else (conv["collected_info"] or {})
    )
    collected["original_request"] = conv.get("initial_idea") or collected.get("initial_idea", "")

    async def event_generator():
        try:
            outline = await conversation_service._generate_outline_with_llm(collected)
            result = conversation_service._finalize_outline_response(
                conversation_id, outline, datetime.utcnow().isoformat() + "Z"
            )

            for paragraph in [p for p in result.message.content.split("\n\n") if p.strip()]:
                yield _sse({
                    "content": paragraph + "\n\n",
                    "done": False,
                    "agent_id": result.message.agent_id,
                })

            yield _sse({
                "done": True,
                "state": result.state.value,
                "message": {
                    "content": result.message.content,
                    "questions": [],
                    "agent_id": result.message.agent_id,
                },
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield _sse({"error": str(e), "done": True})

    return EventSourceResponse(event_generator())


@router.post("/conversations/stream")
async def create_conversation_stream(request: SendMessageRequest):
    """Create a new conversation and stream the first assistant response over SSE."""
    async def event_generator():
        try:
            conv_id = f"conv_{uuid.uuid4().hex[:8]}"
            now = datetime.utcnow().isoformat() + "Z"

            conversation_repo.create_conversation(conv_id, request.message)
            conversation_repo.add_message(conv_id, "user", request.message)

            collected = {"initial_idea": request.message, "round_num": 1}
            conversation_service._extract_common_preferences(collected, request.message)
            conversation_repo.update_conversation(conv_id, collected_info=collected, current_phase=1)

            # Stream questions — round 1
            questions = []
            ready_for_outline = False
            async for event_type, data in conversation_service.stream_next_questions(collected, round_num=1):
                if event_type == "text":
                    yield _sse({
                        "content": data,
                        "done": False,
                        "agent_id": "agent_director",
                    })
                elif event_type == "questions":
                    questions = data
                elif event_type == "ready_for_outline":
                    ready_for_outline = data
                elif event_type == "done":
                    conversation_repo.add_message(
                        conv_id, "assistant", "",
                        questions_json=[q.model_dump() for q in questions],
                    )
                    state = "ready_for_outline" if ready_for_outline else ConversationState.COLLECTING_REQUIREMENTS.value
                    yield _sse({
                        "done": True,
                        "conversation_id": conv_id,
                        "state": state,
                        "message": {
                            "questions": [q.model_dump() for q in questions],
                            "agent_id": "agent_director",
                        },
                    })
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield _sse({"error": str(e), "done": True})

    return EventSourceResponse(event_generator())
