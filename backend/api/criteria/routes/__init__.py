"""
Criteria Analysis Routes

Объединяет все роутеры criteria analysis в один главный роутер
"""

from fastapi import APIRouter
from .analysis import router as analysis_router
from .sessions import router as sessions_router  
from .results import router as results_router
from .files import router as files_router
from .management import router as management_router

# Создаем главный роутер
router = APIRouter(prefix="/criteria", tags=["Criteria Analysis"])

# Включаем все под-роутеры
router.include_router(analysis_router)
router.include_router(sessions_router)
router.include_router(results_router)
router.include_router(files_router)
router.include_router(management_router)

__all__ = ["router"] 