"""
Sessions API Module

Handles all session-related operations:
- Creating new processing sessions
- Managing session lifecycle (start/stop/cancel)
- Retrieving session results and logs
- File upload and validation
"""

from .routes import router

__all__ = ["router"] 