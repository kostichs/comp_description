"""
Processing Control Routes

Handles session processing operations:
- Starting session processing
- Cancelling active processing
"""

from ..common import *
from ..common import _processing_task_done_callback

# Create router
router = APIRouter()


@router.post("/{session_id}/start", summary="Start processing for a session")
async def start_session_processing(session_id: str, background_tasks: BackgroundTasks):
    """
    Starts the processing pipeline for a specific session.
    
    This endpoint:
    1. Validates the session exists and is in correct state
    2. Creates a background task for processing
    3. Updates session status to 'running'
    4. Returns immediately while processing continues in background
    """
    # Load session metadata
    all_metadata = load_session_metadata()
    session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
    
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session with ID '{session_id}' not found.")
    
    current_status = session_data.get("status", "unknown")
    if current_status == "running":
        raise HTTPException(status_code=409, detail=f"Session '{session_id}' is already running.")
    elif current_status in ["completed", "cancelled"]:
        # Allow restarting completed/cancelled sessions
        logger.info(f"Restarting session {session_id} from status '{current_status}'")
    
    # Check if there's already an active task for this session
    if session_id in active_processing_tasks:
        task = active_processing_tasks[session_id]
        if not task.done():
            raise HTTPException(status_code=409, detail=f"Session '{session_id}' already has an active processing task.")
        else:
            # Task is done but still in dict, clean it up
            del active_processing_tasks[session_id]
    
    # Update status to running
    session_data['status'] = 'running'
    session_data['error_message'] = None
    session_data['processed_companies'] = 0
    save_session_metadata(all_metadata)
    
    # Create and start background task
    task = asyncio.create_task(
        run_session_pipeline(
            session_id=session_id,
            broadcast_update=broadcast_update
        )
    )
    
    # Add callback to handle task completion
    task.add_done_callback(lambda t: _processing_task_done_callback(t, session_id))
    
    # Store the task
    active_processing_tasks[session_id] = task
    
    logger.info(f"Started processing for session {session_id}")
    
    # Broadcast update to WebSocket clients
    await broadcast_update({
        "type": "session_started",
        "session_id": session_id,
        "status": "running"
    })
    
    return {"message": f"Processing started for session {session_id}", "status": "running"}


@router.post("/{session_id}/cancel", summary="Cancel processing for a session")
async def cancel_processing_session(session_id: str):
    """
    Cancels the active processing task for a specific session.
    
    This endpoint:
    1. Validates the session exists and is running
    2. Cancels the background processing task
    3. Updates session status to 'cancelled'
    """
    # Check if session exists and has an active task
    if session_id not in active_processing_tasks:
        # Session might exist but not be running
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