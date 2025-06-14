"""
Company Descriptions Generation Domain

This module contains all functionality related to generating company descriptions:
- Session management for description generation
- Processing pipeline management
- Results and logs retrieval
- Session archiving
- LLM-based company description generation
"""

from .routes import router

__all__ = ["router"] 