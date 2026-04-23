"""
System status route.
"""

from fastapi import APIRouter
from services.system_service import SystemService

router = APIRouter()
system_service = SystemService()


@router.get("/system/status")
async def get_system_status():
    return system_service.get_status()
