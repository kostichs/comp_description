"""
Session Management Routes

Handles session lifecycle operations:
- Creating new processing sessions
- Listing all sessions
- Getting session status and information
"""

from ..common import *

# Create router
router = APIRouter()


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

    # Save uploaded file
    try:
        async with aiofiles.open(input_file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        logger.info(f"Saved input file: {input_file_path}")
    except Exception as e:
        logger.error(f"Failed to save input file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file.")

    # Save context text if provided
    if context_text and context_text.strip():
        try:
            async with aiofiles.open(context_file_path, 'w', encoding='utf-8') as f:
                await f.write(context_text.strip())
            logger.info(f"Saved context file: {context_file_path}")
        except Exception as e:
            logger.error(f"Failed to save context file: {e}")
            # Non-critical error, continue

    # Validate file format and content
    try:
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(input_file_path)
        else:  # Excel files
            df = pd.read_excel(input_file_path)
        
        if df.shape[1] < 2:
            raise HTTPException(
                status_code=400, 
                detail=f"File must have at least 2 columns. Found {df.shape[1]} columns."
            )
        
        if df.empty:
            raise HTTPException(status_code=400, detail="File is empty.")
        
        logger.info(f"File validation passed: {df.shape[0]} rows, {df.shape[1]} columns")
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"File validation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid file format: {str(e)}")

    # Create session metadata
    session_metadata = {
        "session_id": session_id,
        "timestamp_created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "input_filename": file.filename,
        "input_file_path": str(input_file_path.relative_to(PROJECT_ROOT)),
        "context_file_path": str(context_file_path.relative_to(PROJECT_ROOT)) if context_text and context_text.strip() else None,
        "output_csv_path": f"output/sessions/{session_id}/results.csv",
        "pipeline_log_path": f"output/sessions/{session_id}/pipeline.log",
        "scoring_log_path": f"output/sessions/{session_id}/scoring.log",
        "status": "created",
        "run_llm_deep_search_pipeline": run_llm_deep_search_pipeline,
        "write_to_hubspot": write_to_hubspot,
        "total_companies": len(df),
        "processed_companies": 0,
        "error_message": None
    }

    # Add to metadata list and save
    metadata.append(session_metadata)
    save_session_metadata(metadata)
    
    logger.info(f"Created new session: {session_id}")
    return {"session_id": session_id, "message": "Session created successfully", "metadata": session_metadata}


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
    Frontend expects GET /api/descriptions/{session_id} to return session info.
    """
    return await get_session_status(session_id) 