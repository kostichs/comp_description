"""
API Package for Company Canvas Backend

This package contains all API routes organized by business domain:
- descriptions: Company description generation algorithm
- criteria: Company criteria analysis algorithm  
- integrations: External service integrations (Clay, HubSpot, etc.)
- common: Shared utilities and common endpoints
"""

from .descriptions import router as descriptions_router
from .criteria import router as criteria_router
from .integrations.clay.routes import router as clay_router

__version__ = "1.0.0"
__all__ = ["descriptions_router", "criteria_router", "clay_router"] 