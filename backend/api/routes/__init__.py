# Routes package for API endpoints
# Each domain has its own router file

from .sessions import router as sessions_router

__all__ = ["sessions_router"] 