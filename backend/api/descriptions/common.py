"""
Common utilities and imports for Descriptions API

This module contains shared functionality used across all description processing endpoints:
- Common imports and dependencies
- Shared utility functions
- Global variables and configurations
- Task management utilities
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import PlainTextResponse, FileResponse
from starlette.background import BackgroundTask
from typing import Optional, Dict, List, Any
import asyncio
import logging
import time
import shutil
import tempfile
import aiofiles
import pandas as pd
import numpy as np
from pathlib import Path

# Import from existing system
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # backend/api/descriptions -> backend/api -> backend -> project root
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR
from backend.services import run_session_pipeline

# Global variable for tracking active tasks
# TODO: Move this to TaskService in future refactoring
active_processing_tasks: Dict[str, asyncio.Task] = {}

# Setup logger for this module - keep original name for frontend compatibility
logger = logging.getLogger("backend.api.descriptions.routes")


def _processing_task_done_callback(task: asyncio.Task, session_id: str):
    """
    Callback function executed when a processing task is completed.
    
    This function:
    1. Updates session metadata based on task completion status
    2. Handles task cancellation and errors
    3. Cleans up the task from active_processing_tasks
    
    TODO: Move this logic to TaskService in future refactoring
    """
    try:
        task.result()  # Check if task completed successfully
        logger.info(f"Processing task for session {session_id} finished successfully (via callback).")
        
        # Update metadata: status = "completed"
        try:
            all_metadata = load_session_metadata()
            session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
            if session_data and session_data.get('status') != 'cancelled':
                session_data['status'] = 'completed'
                save_session_metadata(all_metadata)
                logger.info(f"Updated session {session_id} status to 'completed' in metadata")
        except Exception as e:
            logger.error(f"Failed to update session {session_id} metadata to completed: {e}")
            
    except asyncio.CancelledError:
        logger.info(f"Processing task for session {session_id} was cancelled (via callback).")
        
        # Update metadata: status = "cancelled"
        try:
            all_metadata = load_session_metadata()
            session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
            if session_data:
                session_data['status'] = 'cancelled'
                session_data['error_message'] = 'Processing cancelled by user'
                save_session_metadata(all_metadata)
                logger.info(f"Updated session {session_id} status to 'cancelled' in metadata")
        except Exception as e:
            logger.error(f"Failed to update session {session_id} metadata to cancelled: {e}")
            
    except Exception as e:
        logger.error(f"Processing task for session {session_id} failed with error (via callback): {e}", exc_info=True)
        
        # Update metadata: status = "error"
        try:
            all_metadata = load_session_metadata()
            session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
            if session_data:
                session_data['status'] = 'error'
                session_data['error_message'] = str(e)
                save_session_metadata(all_metadata)
                logger.info(f"Updated session {session_id} status to 'error' in metadata")
        except Exception as meta_e:
            logger.error(f"Failed to update session {session_id} metadata to error: {meta_e}")
    finally:
        # Always clean up the task from active tasks
        if session_id in active_processing_tasks:
            del active_processing_tasks[session_id]
            logger.info(f"Removed task for session {session_id} from active_processing_tasks.")


# Temporary broadcast function - will be moved to WebSocketService
# TODO: Move WebSocket functionality to dedicated service
async def broadcast_update(data: dict):
    """
    Temporary function for broadcasting updates to WebSocket clients.
    
    This is a placeholder implementation. The real broadcast_update
    is in main.py and handles WebSocket connections.
    
    TODO: Create WebSocketService to handle this properly
    """
    logger.debug(f"Broadcast update (placeholder): {data}")
    # In production, this should broadcast to WebSocket clients


def clean_for_json(obj):
    """
    Clean pandas/numpy objects for JSON serialization.
    
    Args:
        obj: Object to clean (can be pandas/numpy type or regular Python type)
        
    Returns:
        JSON-serializable object
    """
    if pd.isna(obj):
        return None
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj) if not pd.isna(obj) else None
    else:
        return obj 