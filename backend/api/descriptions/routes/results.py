"""
Results and Logs Routes

Handles retrieval of session results and logs:
- Getting processed results
- Accessing log files
- Downloading session archives
"""

from ..common import *
import zipfile

# Create router
router = APIRouter()


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