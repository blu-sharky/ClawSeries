"""
Conversation routes.
"""

from fastapi import APIRouter, HTTPException
from models import (
    CreateConversationRequest, CreateConversationResponse,
    SendMessageRequest, SendMessageResponse,
    ConfirmRequest, ConfirmResponse, StartProductionResponse,
    ConversationDetail,
)
from services.conversation_service import ConversationService

router = APIRouter()
conversation_service = ConversationService()


@router.post("/conversations", response_model=CreateConversationResponse)
async def create_conversation(request: CreateConversationRequest):
    return await conversation_service.create_conversation(request.initial_idea)


@router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(conversation_id: str, request: SendMessageRequest):
    result = await conversation_service.send_message(conversation_id, request.message)
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str):
    result = conversation_service.get_conversation(conversation_id)
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result


@router.post("/conversations/{conversation_id}/confirm", response_model=ConfirmResponse)
async def confirm_outline(conversation_id: str, request: ConfirmRequest):
    if not request.confirmed:
        raise HTTPException(status_code=400, detail="用户未确认")
    result = conversation_service.confirm_outline(conversation_id)
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result


@router.post("/conversations/{conversation_id}/start-production", response_model=StartProductionResponse)
async def start_production(conversation_id: str, request: ConfirmRequest):
    if not request.confirmed:
        raise HTTPException(status_code=400, detail="用户未确认")
    result = conversation_service.start_production(conversation_id)
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result
