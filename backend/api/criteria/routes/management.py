"""
Criteria Analysis Routes - Management & Utilities

Содержит endpoints для управления и мониторинга:
- GET /health - health check сервиса
"""

import json
from datetime import datetime
from fastapi import APIRouter, HTTPException

from ..common import (
    logger, criteria_sessions,
    CRITERIA_PROCESSOR_PATH
)

router = APIRouter()

@router.get("/health")
async def criteria_service_health():
    """Health check для сервиса анализа критериев"""
    try:
        # Проверяем что папка criteria_processor существует
        if not CRITERIA_PROCESSOR_PATH.exists():
            raise Exception("Criteria processor path not found")
        
        return {
            "service": "criteria_analysis",
            "status": "healthy",
            "active_sessions": len([s for s in criteria_sessions.values() if s["status"] == "processing"]),
            "total_sessions": len(criteria_sessions),
            "criteria_processor_path": str(CRITERIA_PROCESSOR_PATH)
        }
    except Exception as e:
        return {
            "service": "criteria_analysis", 
            "status": "unhealthy",
            "error": str(e)
        } 