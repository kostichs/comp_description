"""
Sessions API Routes - используем существующую архитектуру
"""

import time
import shutil
import asyncio
import pandas as pd
import aiofiles
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks

# Import existing system components
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR
from backend.models.schemas.session import SessionResponse, SessionStatus, SessionCreate
from backend.services.pipeline_orchestrator import run_session_pipeline

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# Active tasks tracking (simple in-memory storage)
active_tasks = {}

@router.get("/", response_model=List[SessionResponse])
async def get_sessions():
    """Get all sessions"""
    try:
        metadata = load_session_metadata()
        sessions = []
        for session_data in metadata:
            try:
                # Convert legacy status values
                status = session_data.get('status')
                if status == 'running':
                    session_data['status'] = SessionStatus.PROCESSING
                elif isinstance(status, str):
                    try:
                        session_data['status'] = SessionStatus(status)
                    except ValueError:
                        session_data['status'] = SessionStatus.CREATED
                        logger.warning(f"Unknown status '{status}' for session {session_data.get('session_id')}, defaulting to CREATED")
                
                # Make optional fields truly optional
                session_data.setdefault('timestamp_created', '')
                session_data.setdefault('input_filename', '')
                session_data.setdefault('context_text', '')
                session_data.setdefault('run_llm_deep_search_pipeline', True)
                session_data.setdefault('write_to_hubspot', True)
                session_data.setdefault('progress_percentage', 0.0)
                session_data.setdefault('processed_count', 0)
                session_data.setdefault('error_count', 0)
                session_data.setdefault('error_message', '')
                
                sessions.append(SessionResponse(**session_data))
            except Exception as e:
                logger.warning(f"Skipping invalid session data: {e}")
                continue
        return sessions
    except Exception as e:
        logger.error(f"Error loading sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to load sessions")

@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get specific session by ID"""
    try:
        metadata = load_session_metadata()
        session_data = next((s for s in metadata if s.get('session_id') == session_id), None)
        if not session_data:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        # Convert legacy status values
        status = session_data.get('status')
        if status == 'running':
            session_data['status'] = SessionStatus.PROCESSING
        elif isinstance(status, str):
            try:
                session_data['status'] = SessionStatus(status)
            except ValueError:
                session_data['status'] = SessionStatus.CREATED
                logger.warning(f"Unknown status '{status}' for session {session_id}, defaulting to CREATED")
        
        # Make optional fields truly optional
        session_data.setdefault('timestamp_created', '')
        session_data.setdefault('input_filename', '')
        session_data.setdefault('context_text', '')
        session_data.setdefault('run_llm_deep_search_pipeline', True)
        session_data.setdefault('write_to_hubspot', True)
        session_data.setdefault('progress_percentage', 0.0)
        session_data.setdefault('processed_count', 0)
        session_data.setdefault('error_count', 0)
        session_data.setdefault('error_message', '')
            
        return SessionResponse(**session_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get session")

@router.post("/", response_model=SessionResponse)
async def create_session(
    file: UploadFile = File(...),
    context_text: str = Form(""),
    run_llm_deep_search_pipeline: bool = Form(True),
    write_to_hubspot: bool = Form(True)
):
    """Create new session with file upload"""
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
        
    allowed_extensions = (".csv", ".xlsx", ".xls")
    if not file.filename.lower().endswith(allowed_extensions):
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed: {allowed_extensions}"
        )
    
    # Generate unique session ID
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    base_filename = Path(file.filename).stem
    session_id = f"{timestamp}_{base_filename}"
    
    # Handle ID collision
    metadata = load_session_metadata()
    if any(s.get('session_id') == session_id for s in metadata):
        session_id += f"_{int(time.time() * 1000) % 1000}"
        
    session_dir = SESSIONS_DIR / session_id
    
    try:
        # Create session directory
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Save uploaded file
        input_file_path = session_dir / f"input_{file.filename}"
        async with aiofiles.open(input_file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
            
        # Save context if provided
        context_path = None
        if context_text and context_text.strip():
            context_path = session_dir / "context_used.txt"
            async with aiofiles.open(context_path, 'w', encoding='utf-8') as f:
                await f.write(context_text.strip())
        
        # Validate file content
        await _validate_input_file(input_file_path)
        
        # Create session metadata using existing system format
        new_session = {
            'session_id': session_id,
            'status': SessionStatus.CREATED.value,
            'timestamp_created': time.strftime("%Y-%m-%d %H:%M:%S"),
            'input_filename': file.filename,
            'input_file_path': str(input_file_path.relative_to(PROJECT_ROOT)),
            'context_text': context_text.strip() if context_text else '',
            'context_used_path': str(context_path.relative_to(PROJECT_ROOT)) if context_path else '',
            'run_llm_deep_search_pipeline': run_llm_deep_search_pipeline,
            'write_to_hubspot': write_to_hubspot,
            'progress_percentage': 0.0,
            'processed_count': 0,
            'error_count': 0,
            'error_message': ''
        }
        
        metadata.append(new_session)
        save_session_metadata(metadata)
        
        logger.info(f"Created session {session_id}")
        new_session['status'] = SessionStatus.CREATED  # Convert back to enum for response
        return SessionResponse(**new_session)
        
    except Exception as e:
        # Cleanup on error
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

@router.post("/{session_id}/start")
async def start_processing(session_id: str, background_tasks: BackgroundTasks):
    """Start session processing"""
    try:
        # Check if session exists
        metadata = load_session_metadata()
        session_data = next((s for s in metadata if s.get('session_id') == session_id), None)
        if not session_data:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        # Check if already processing
        if session_id in active_tasks:
            task = active_tasks[session_id]
            if not task.done():
                return {"message": "Session is already processing", "session_id": session_id}
        
        # Update status to processing
        session_data['status'] = 'processing'
        save_session_metadata(metadata)
        
        # Create processing task using existing orchestrator
        task = asyncio.create_task(run_session_pipeline(session_id))
        task.add_done_callback(lambda t: _task_done_callback(t, session_id))
        active_tasks[session_id] = task
        
        logger.info(f"Started processing for session {session_id}")
        return {"message": "Processing started", "session_id": session_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start processing for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to start processing")

@router.post("/{session_id}/cancel")
async def cancel_processing(session_id: str):
    """Cancel session processing"""
    try:
        if session_id not in active_tasks:
            raise HTTPException(status_code=404, detail="No active processing found for this session")
        
        task = active_tasks[session_id]
        if task.done():
            return {"message": "Processing already completed", "session_id": session_id}
        
        # Cancel the task
        task.cancel()
        
        # Update session status
        metadata = load_session_metadata()
        session_data = next((s for s in metadata if s.get('session_id') == session_id), None)
        if session_data:
            session_data['status'] = 'cancelled'
            session_data['error_message'] = 'Processing cancelled by user'
            save_session_metadata(metadata)
        
        logger.info(f"Cancelled processing for session {session_id}")
        return {"message": "Processing cancelled", "session_id": session_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel processing for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel processing")

@router.get("/{session_id}/results")
async def get_results(session_id: str):
    """Get session results"""
    try:
        session_dir = SESSIONS_DIR / session_id
        results_file = session_dir / f"{session_id}_results.csv"
        
        if not results_file.exists():
            raise HTTPException(status_code=404, detail="Results file not found")
        
        # Read and return CSV data
        df = pd.read_csv(results_file)
        return {
            "session_id": session_id,
            "total_rows": len(df),
            "columns": df.columns.tolist(),
            "data": df.to_dict('records')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get results for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get results")

@router.get("/{session_id}/logs/{log_type}")
async def get_logs(session_id: str, log_type: str):
    """Get session logs"""
    try:
        session_dir = SESSIONS_DIR / session_id
        
        if log_type == "pipeline":
            log_file = session_dir / "pipeline.log"
        else:
            raise HTTPException(status_code=400, detail="Invalid log type")
        
        if not log_file.exists():
            return {"session_id": session_id, "log_type": log_type, "content": ""}
        
        async with aiofiles.open(log_file, 'r', encoding='utf-8') as f:
            content = await f.read()
        
        return {
            "session_id": session_id,
            "log_type": log_type,
            "content": content
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get logs for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get logs")

@router.get("/{session_id}/download_archive")
async def download_archive(session_id: str):
    """Download session archive"""
    try:
        session_dir = SESSIONS_DIR / session_id
        
        if not session_dir.exists():
            raise HTTPException(status_code=404, detail="Session directory not found")
        
        # Create archive (simplified - just return directory info for now)
        files = list(session_dir.glob("*"))
        return {
            "session_id": session_id,
            "files": [f.name for f in files if f.is_file()],
            "archive_ready": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create archive for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create archive")

# Helper functions

async def _validate_input_file(file_path: Path):
    """Validate input file format and content"""
    try:
        if file_path.suffix.lower() == '.csv':
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
                
        if len(df.columns) != 2:
            raise ValueError(f"Expected 2 columns, got {len(df.columns)}")
            
        if df.empty:
            raise ValueError("File is empty")
            
    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file format: {str(e)}"
        )

def _task_done_callback(task: asyncio.Task, session_id: str):
    """Callback when processing task is done"""
    try:
        if session_id in active_tasks:
            del active_tasks[session_id]
        
        if task.cancelled():
            logger.info(f"Task for session {session_id} was cancelled")
        elif task.exception():
            logger.error(f"Task for session {session_id} failed: {task.exception()}")
        else:
            logger.info(f"Task for session {session_id} completed successfully")
            
    except Exception as e:
        logger.error(f"Error in task callback for session {session_id}: {e}") 