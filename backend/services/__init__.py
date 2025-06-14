"""
Backend Services Package

This package contains shared services used across different API domains:
- pipeline_orchestrator: Universal pipeline execution orchestrator
- session_manager: Session metadata management
- config_loader: Configuration and API keys loading
"""

from .pipeline_orchestrator import run_session_pipeline

__all__ = ['run_session_pipeline'] 