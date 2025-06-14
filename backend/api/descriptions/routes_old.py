"""
Sessions API Router

This module contains all API endpoints related to session management:
- Creating new processing sessions
- Starting/stopping session processing
- Retrieving session results and logs
- Managing session lifecycle

Extracted from main.py to improve code organization and maintainability.
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
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # backend/api/sessions -> backend/api -> backend -> project root
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR
from backend.services import run_session_pipeline

# Global variable for tracking active tasks
# TODO: Move this to TaskService in future refactoring
active_processing_tasks: Dict[str, asyncio.Task] = {}

# Create router
router = APIRouter(prefix="/descriptions", tags=["Company Descriptions"])

# Setup logger for this module
logger = logging.getLogger(__name__)


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


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/", summary="List all processing sessions")
async def get_sessions():
    """
    Retrieves metadata for all recorded processing sessions.
    
    Returns:
        List[Dict]: List of session metadata objects
        
    This endpoint is used by the frontend to populate the session selector
    and show the history of all processing sessions.
    """
    try:
        metadata = load_session_metadata()
        logger.info(f"Retrieved {len(metadata)} sessions from metadata")
        
        # Optional: Sort sessions by timestamp_created descending
        # metadata.sort(key=lambda s: s.get('timestamp_created', ''), reverse=True)
        
        return metadata
    except Exception as e:
        logger.error(f"Error loading sessions metadata: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to load sessions metadata"
        )


@router.post("/", summary="Create a new processing session")
async def create_new_session(
    file: UploadFile = File(...), 
    context_text: Optional[str] = Form(None), 
    run_llm_deep_search_pipeline: bool = Form(True),
    write_to_hubspot: bool = Form(True)
):
    """
    Creates a new processing session by uploading an input file (CSV/XLSX) 
    and optional context text. Only files with two columns (Company Name and Website URL) are accepted.
    
    This is the most complex endpoint as it:
    1. Validates the uploaded file
    2. Creates a unique session ID and directory
    3. Saves the file and optional context
    4. Validates file format and content
    5. Creates session metadata
    """
    # Basic validation for filename/extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")
    allowed_extensions = (".csv", ".xlsx", ".xls")
    if not file.filename.lower().endswith(allowed_extensions):
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {allowed_extensions}")

    # Generate session ID
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    base_filename = Path(file.filename).stem
    session_id = f"{timestamp}_{base_filename}"
    session_dir = SESSIONS_DIR / session_id

    metadata = load_session_metadata()
    if any(s.get('session_id') == session_id for s in metadata):
        session_id += f"_{int(time.time() * 1000) % 1000}"
        session_dir = SESSIONS_DIR / session_id
        logger.warning(f"Session ID collision detected, generated new ID: {session_id}")

    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created session directory: {session_dir}")
    except OSError as e:
        logger.error(f"Could not create session directory {session_dir}. Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session directory.")

    input_file_path = session_dir / f"input_{file.filename}"
    context_file_path = session_dir / "context_used.txt"

    file_saved_successfully = False
    try:
        async with aiofiles.open(input_file_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024):
                await out_file.write(content)
        logger.info(f"Saved uploaded file to: {input_file_path}")
        file_saved_successfully = True
    except Exception as e:
        logger.error(f"Failed to save uploaded file {input_file_path}: {e}")
        try: 
            shutil.rmtree(session_dir)
            logger.info(f"Cleaned up session dir due to file save error: {session_dir}")
        except Exception as e_clean: 
            logger.error(f"Failed to cleanup session dir {session_dir}: {e_clean}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file.")
    finally:
        await file.close()

    context_saved_successfully = True
    if context_text:
        try:
            async with aiofiles.open(context_file_path, 'w', encoding='utf-8') as context_file:
                await context_file.write(context_text)
            logger.info(f"Saved context text to: {context_file_path}")
        except Exception as e:
            logger.error(f"Failed to save context file {context_file_path}: {e}")
            context_saved_successfully = False

    if file_saved_successfully:
        try:
            if str(input_file_path).endswith('.csv'):
                df = pd.read_csv(input_file_path)
            else:
                df = pd.read_excel(input_file_path)
            
            # Валидация: файл должен содержать минимум две колонки
            if df.shape[1] < 2:
                try: 
                    shutil.rmtree(session_dir)
                    logger.info(f"Cleaned up session dir due to validation error: {session_dir}")
                except Exception as e_clean: 
                    logger.error(f"Failed to cleanup session dir {session_dir}: {e_clean}")
                raise HTTPException(status_code=400, detail="File must contain exactly two columns: Company Name and Website URL")
            
            initial_upload_count = len(df)
        except HTTPException:
            raise  # Re-raise HTTP exceptions
        except Exception:
            initial_upload_count = 0 # Или None, если предпочитаете, но 0 безопаснее для UI
        
        new_session_data = {
            "session_id": session_id,
            "timestamp_created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "original_input_filename": file.filename, 
            "input_file_path": str(input_file_path.relative_to(PROJECT_ROOT)), 
            "context_used_path": str(context_file_path.relative_to(PROJECT_ROOT)) if context_text else None,
            "context_provided": bool(context_text),
            "status": "created",
            "output_csv_path": None, 
            "pipeline_log_path": None,
            "scoring_log_path": None,
            "last_processed_count": 0,
            "initial_upload_count": initial_upload_count, # Новое поле
            "total_companies": 0, # Инициализируем нулем
            "companies_count": 0, # Инициализируем нулем
            "deduplication_info": None, # Явно инициализируем
            "processing_messages": [],   # Явно инициализируем
            "error_message": None if context_saved_successfully else "Failed to save context file",
            "run_llm_deep_search_pipeline": run_llm_deep_search_pipeline,
            "write_to_hubspot": write_to_hubspot
        }
        
        metadata.append(new_session_data)
        try:
            save_session_metadata(metadata)
            logger.info(f"Added new session metadata for ID: {session_id}")
        except Exception as e:
             logger.error(f"Failed to save session metadata after creating session {session_id}: {e}")
             raise HTTPException(status_code=500, detail="Failed to save session metadata.")

        return new_session_data
    else:
        logger.error(f"File saving reported failure, metadata not saved for potential session {session_id}.")
        return { "detail": "Internal server error during file processing." }


@router.post("/{session_id}/start", summary="Start processing for a session")
async def start_session_processing(session_id: str, background_tasks: BackgroundTasks):
    """
    Starts the data processing pipeline for the specified session in the background.
    
    This endpoint:
    1. Validates session exists and is not already running
    2. Creates an async task for processing
    3. Adds callback for task completion handling
    4. Updates session status to 'queued'
    """
    # 1. Find session metadata
    all_metadata = load_session_metadata()
    session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
    
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session with ID '{session_id}' not found.")
        
    # 2. Check current status
    current_status = session_data.get("status")
    if current_status == "running":
        raise HTTPException(status_code=409, detail=f"Session '{session_id}' is already running.")
    if current_status == "completed":
        # Optionally allow re-running? For now, prevent.
        raise HTTPException(status_code=409, detail=f"Session '{session_id}' has already completed.")
    if current_status == "error":
        logger.info(f"Re-running session '{session_id}' which previously ended in error.")
        # Allow re-running errored sessions
        
    # 3. Check if input file exists (sanity check)
    input_file_path_rel = session_data.get("input_file_path")
    if not input_file_path_rel or not (PROJECT_ROOT / input_file_path_rel).exists():
        logger.error(f"Input file path missing or file not found for session {session_id}: {input_file_path_rel}")
        # Update status to error maybe?
        session_data['status'] = 'error'
        session_data['error_message'] = "Input file missing or path invalid in metadata."
        save_session_metadata(all_metadata)
        raise HTTPException(status_code=400, detail="Input file path missing or invalid in session metadata.")

    # --- Wrap task adding in try/except --- 
    try:
        # Создаем задачу и регистрируем её в active_processing_tasks
        task = asyncio.create_task(run_session_pipeline(session_id, broadcast_update))
        active_processing_tasks[session_id] = task
        
        # Добавляем callback для очистки задачи после завершения
        task.add_done_callback(lambda t: _processing_task_done_callback(t, session_id))
        
        logger.info(f"Added pipeline run for session {session_id} to background tasks and active_processing_tasks.")
        
        # Update status IN METADATA immediately after successfully adding task?
        # This prevents UI showing old status until task actually starts running.
        session_data['status'] = 'queued' # Or 'starting'
        session_data['error_message'] = None # Clear previous errors on restart
        save_session_metadata(all_metadata)
        logger.info(f"Updated session {session_id} status to 'queued' in metadata.")
        
    except Exception as e_task:
        logger.error(f"Failed to add background task for session {session_id}: {e_task}")
        # Don't change status if adding task failed
        raise HTTPException(status_code=500, detail=f"Failed to queue processing task for session {session_id}.")
    # --- End Wrap --- 

    # 5. Return immediate response
    return {"message": f"Processing queued in background for session {session_id}"}


@router.post("/{session_id}/cancel", summary="Cancel processing for a session")
async def cancel_processing_session(session_id: str):
    """
    Cancels the running processing task for the specified session.
    
    This endpoint:
    1. Finds the active task in active_processing_tasks
    2. Cancels the asyncio task
    3. Updates session status to 'cancelled'
    """
    # Check if there's an active task for this session
    if session_id not in active_processing_tasks:
        # Maybe it's not running, or already completed/cancelled
        # Check session metadata to give more specific error
        all_metadata = load_session_metadata()
        session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
        
        if not session_data:
            raise HTTPException(status_code=404, detail=f"Session with ID '{session_id}' not found.")
        
        current_status = session_data.get("status", "unknown")
        if current_status in ["completed", "cancelled", "error"]:
            raise HTTPException(status_code=409, detail=f"Session '{session_id}' is not running (status: {current_status}).")
        else:
            # Status says running but no active task found - might be a stale state
            raise HTTPException(status_code=404, detail=f"No active processing task found for session '{session_id}'.")
    
    # Cancel the task
    task = active_processing_tasks[session_id]
    task.cancel()
    logger.info(f"Cancelled processing task for session {session_id}.")
    
    # The task's done_callback will handle updating the metadata status to 'cancelled'
    # and cleaning up the task from active_processing_tasks.
    
    return {"message": f"Processing cancelled for session {session_id}"}


@router.get("/{session_id}/results", summary="Get session results")
async def get_session_results(session_id: str):
    """
    Retrieves the processed results from the session's CSV file.
    
    Returns the results as JSON, or empty list if no results yet.
    """
    all_metadata = load_session_metadata()
    session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
    
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session with ID '{session_id}' not found.")
        
    output_csv_path_rel = session_data.get("output_csv_path")
    if not output_csv_path_rel:
        # Maybe processing hasn't started or path wasn't stored correctly
        raise HTTPException(status_code=404, detail=f"Results file path not found in metadata for session '{session_id}'.")
        
    output_csv_path = PROJECT_ROOT / output_csv_path_rel
    
    if not output_csv_path.exists():
        # File doesn't exist yet (maybe processing started but hasn't written anything)
        # Return empty list instead of 404? Consistent with empty file.
        logger.warning(f"Results file {output_csv_path} not found for session {session_id}, returning empty list.")
        return []
    
    try:
        # Load CSV and convert to list of dictionaries
        df = pd.read_csv(output_csv_path)
        
        # Clean the data for JSON serialization
        def clean_for_json(obj):
            if pd.isna(obj):
                return None
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj) if not pd.isna(obj) else None
            else:
                return obj
        
        # Convert DataFrame to list of dictionaries with cleaned values
        results = []
        for _, row in df.iterrows():
            cleaned_row = {col: clean_for_json(row[col]) for col in df.columns}
            results.append(cleaned_row)
        
        logger.info(f"Loaded {len(results)} results for session {session_id}")
        return results
        
    except Exception as e:
        logger.error(f"Error loading results for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load session results")


@router.get("/{session_id}/logs/{log_type}", summary="Get session log file content")
async def get_session_log(session_id: str, log_type: str):
    """
    Returns the content of a log file for the specified session.
    
    Args:
        session_id: The session identifier
        log_type: Type of log ('pipeline' or 'scoring')
    """
    if log_type not in ["pipeline", "scoring"]:
        raise HTTPException(status_code=400, detail="log_type must be 'pipeline' or 'scoring'")
    
    all_metadata = load_session_metadata()
    session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
    
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session with ID '{session_id}' not found.")
    
    log_path_key = f"{log_type}_log_path"
    log_path_rel = session_data.get(log_path_key)
    
    if not log_path_rel:
        raise HTTPException(status_code=404, detail=f"Log path for '{log_type}' not found in session metadata.")
    
    log_path = PROJECT_ROOT / log_path_rel
    
    if not log_path.exists():
        return PlainTextResponse(f"Log file not found: {log_path_rel}", status_code=404)
    
    try:
        async with aiofiles.open(log_path, 'r', encoding='utf-8') as log_file:
            content = await log_file.read()
        return PlainTextResponse(content, media_type="text/plain")
    except Exception as e:
        logger.error(f"Error reading log file {log_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read {log_type} log file")


@router.get("/{session_id}/status", summary="Get session status")
async def get_session_status(session_id: str):
    """
    Returns the current status and metadata for a specific session.
    
    This endpoint is used by the frontend to check processing progress
    and update the UI accordingly.
    """
    all_metadata = load_session_metadata()
    session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
    
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session with ID '{session_id}' not found.")
    
    return session_data


@router.get("/{session_id}", summary="Get session information")
async def get_session_info(session_id: str):
    """
    Returns the session information (alias for /status endpoint).
    
    This endpoint exists for frontend compatibility.
    Frontend expects GET /api/sessions/{session_id} to return session info.
    """
    return await get_session_status(session_id)


@router.get("/{session_id}/download_archive", summary="Download session archive")
async def download_session_archive(session_id: str):
    """
    Creates and downloads a ZIP archive containing all files from a session.
    
    Includes:
    - Input files
    - Results CSV
    - Pipeline logs
    - JSON data
    - Raw data files
    """
    import zipfile
    import tempfile
    from pathlib import Path
    from fastapi.responses import FileResponse
    
    # Load session metadata to verify session exists
    all_metadata = load_session_metadata()
    session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
    
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session with ID '{session_id}' not found.")
    
    # Get session directory path
    session_dir = PROJECT_ROOT / "output" / "sessions" / session_id
    
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session directory not found: {session_dir}")
    
    # Create temporary ZIP file
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    temp_zip.close()
    
    try:
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add all files from session directory recursively
            for file_path in session_dir.rglob('*'):
                if file_path.is_file():
                    # Create relative path for archive
                    arcname = file_path.relative_to(session_dir)
                    zipf.write(file_path, arcname)
        
        # Return ZIP file as download
        return FileResponse(
            path=temp_zip.name,
            filename=f"{session_id}_archive.zip",
            media_type="application/zip",
            background=BackgroundTask(lambda: Path(temp_zip.name).unlink(missing_ok=True))
        )
        
    except Exception as e:
        # Clean up temp file on error
        Path(temp_zip.name).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to create archive: {str(e)}") 