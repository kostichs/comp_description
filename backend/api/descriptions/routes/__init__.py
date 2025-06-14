"""
Descriptions API Routes

This module combines all description processing routes into a single router.
Modular structure for better maintainability and testing.
"""

from fastapi import APIRouter
from . import sessions, processing, results

# Create main router
router = APIRouter(prefix="/descriptions", tags=["Company Descriptions"])

# Include all sub-routers
router.include_router(sessions.router)
router.include_router(processing.router)  
router.include_router(results.router) 