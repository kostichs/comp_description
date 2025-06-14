"""
External Integrations Domain

This module contains all functionality related to external service integrations:
- Clay webhook integration
- HubSpot integration
- Other third-party service integrations
"""

from .clay.routes import router as clay_router

__all__ = ["clay_router"] 