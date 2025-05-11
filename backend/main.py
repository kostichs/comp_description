from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import sys
from pathlib import Path
import time
import shutil
import aiofiles
import logging
import pandas as pd
from fastapi.responses import PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import json
from datetime import datetime
from src.pipeline import process_companies, run_pipeline_for_file
from src.config import OUTPUT_DIR, load_env_vars, load_llm_config
from typing import Dict, List, Any, Optional
import aiohttp
from openai import AsyncOpenAI
from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR # Example import
from scrapingbee import ScrapingBeeClient

# Need to ensure SESSIONS_DIR and SESSIONS_METADATA_FILE are correctly handled within data_io.py

# Configure basic logging if not already configured elsewhere
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Adjust sys.path to allow importing from src
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Now we can import from src
from src.config import load_env_vars, load_llm_config # Example import
# Need to ensure SESSIONS_DIR and SESSIONS_METADATA_FILE are correctly handled within data_io.py

# --- Import background task runner --- 
from .processing_runner import run_session_pipeline

app = FastAPI(
    title="Company Information API",
    description="API for finding company information and generating descriptions.",
    version="0.1.0"
)

# --- CORS Middleware --- 
# Allow requests from the typical local development frontend origin
# Adjust origins if your frontend server runs on a different port
origins = [
    "http://localhost",         # Base origin
    "http://localhost:8001",    # Default port for python -m http.server often
    "http://127.0.0.1",
    "http://127.0.0.1:8001",
    # Add other origins if needed (e.g., http://localhost:3000 for React dev server)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # Allow cookies if needed later
    allow_methods=["*"],    # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],    # Allow all headers
)

# Configure basic logging if not already configured elsewhere
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Store active WebSocket connections
active_connections: list[WebSocket] = []

# --- Начало изменений: Управление фоновыми задачами ---
# Словарь для хранения активных задач обработки
# Ключ: session_id (str), Значение: asyncio.Task
active_processing_tasks: Dict[str, asyncio.Task] = {}

# Гипотетическая функция, запускающая ваш пайплайн. 
# АДАПТИРУЙТЕ ЕЕ И ЕЕ ПАРАМЕТРЫ ПОД ВАШУ РЕАЛЬНУЮ ФУНКЦИЮ
async def execute_pipeline_for_session_async(
    session_id: str, 
    input_file: Path, 
    output_csv_file: Path,
    pipeline_log_path: Path, 
    scoring_log_path: Path,  
    context_text: Optional[str],
    llm_config: dict 
):
    logger.info(f"[EXECUTE_PIPELINE] Starting for session_id: {session_id}")
    logger.info(f"[EXECUTE_PIPELINE] Input file: {input_file}")
    logger.info(f"[EXECUTE_PIPELINE] Output CSV: {output_csv_file}")
    logger.info(f"[EXECUTE_PIPELINE] Pipeline Log: {pipeline_log_path}")
    logger.info(f"[EXECUTE_PIPELINE] Scoring Log: {scoring_log_path}")
    logger.info(f"[EXECUTE_PIPELINE] Context provided: {bool(context_text)}")
    logger.info(f"[EXECUTE_PIPELINE] LLM Config keys: {list(llm_config.keys()) if llm_config else 'None'}")

    try:
        logger.info("[EXECUTE_PIPELINE] Loading environment variables...")
        env_vars = load_env_vars()
        scrapingbee_api_key = env_vars[0] 
        openai_api_key = env_vars[1]
        serper_api_key = env_vars[2]
        logger.info("[EXECUTE_PIPELINE] Environment variables loaded.")
    except Exception as e_env:
        logger.error(f"[EXECUTE_PIPELINE] Failed to load env_vars: {e_env}", exc_info=True)
        return

    # --- Определение полей CSV --- 
    base_ordered_fields = ["name", "homepage", "linkedin", "description", "timestamp"]
    # logger.info(f"[EXECUTE_PIPELINE] Defined base_ordered_fields: {base_ordered_fields}") # Можно оставить для отладки
    
    additional_llm_fields = []
    if isinstance(llm_config.get("response_format"), dict) and \
       llm_config["response_format"].get("type") == "json_object":
        try:
            if "expected_json_keys" in llm_config: 
                llm_keys = [f"llm_{k}" for k in llm_config["expected_json_keys"]]
                additional_llm_fields.extend(llm_keys)
        except Exception as e_llm_keys:
            logger.warning(f"[EXECUTE_PIPELINE] Could not dynamically determine LLM output keys: {e_llm_keys}")
    
    # Формируем окончательный список полей
    temp_fieldnames = list(base_ordered_fields) # Начинаем с базовых
    for field in additional_llm_fields:
        if field not in temp_fieldnames:
            temp_fieldnames.append(field)
    expected_csv_fieldnames = temp_fieldnames
    
    logger.info(f"[EXECUTE_PIPELINE] Determined expected_csv_fieldnames for session {session_id}: {expected_csv_fieldnames}") # <--- КЛЮЧЕВОЙ ЛОГ
    
    logger.info("[EXECUTE_PIPELINE] Initializing API clients and aiohttp session...")
    async with aiohttp.ClientSession() as aiohttp_session:
        logger.info("[EXECUTE_PIPELINE] aiohttp.ClientSession created.")
        sb_client = ScrapingBeeClient(api_key=scrapingbee_api_key) 
        logger.info("[EXECUTE_PIPELINE] ScrapingBeeClient created.")
        openai_async_client = AsyncOpenAI(api_key=openai_api_key)
        logger.info("[EXECUTE_PIPELINE] AsyncOpenAI client created.")
        
        try:
            logger.info(f"[EXECUTE_PIPELINE] Calling run_pipeline_for_file for session {session_id}...")
            await run_pipeline_for_file( 
                input_file_path=input_file,
                output_csv_path=output_csv_file,
                pipeline_log_path=str(pipeline_log_path), 
                scoring_log_path=str(scoring_log_path),
                context_text=context_text,
                company_col_index=0, 
                aiohttp_session=aiohttp_session, 
                sb_client=sb_client, 
                llm_config=llm_config,
                openai_client=openai_async_client, 
                serper_api_key=serper_api_key,
                expected_csv_fieldnames=expected_csv_fieldnames, 
                broadcast_update=None, # Ваша функция broadcast_update
                main_batch_size=50 
            )
            logger.info(f"[EXECUTE_PIPELINE] Pipeline execution for session_id: {session_id} completed.")
        except asyncio.CancelledError:
            logger.info(f"[EXECUTE_PIPELINE] Pipeline execution for session_id: {session_id} was cancelled.")
            raise 
        except Exception as e:
            logger.error(f"[EXECUTE_PIPELINE] Error during run_pipeline_for_file for session_id {session_id}: {e}", exc_info=True)
    logger.info(f"[EXECUTE_PIPELINE] Finished for session_id: {session_id}")

# Callback-функция для задач
def _processing_task_done_callback(task: asyncio.Task, session_id: str):
    try:
        task.result()  # Проверяем, не было ли исключений в задаче
        logger.info(f"Processing task for session {session_id} finished successfully (via callback).")
        # Обновить метаданные: статус = "completed"
        # update_session_status(session_id, "completed") # Пример
    except asyncio.CancelledError:
        logger.info(f"Processing task for session {session_id} was cancelled (via callback).")
        # Обновить метаданные: статус = "cancelled"
        # update_session_status(session_id, "cancelled") # Пример
    except Exception as e:
        logger.error(f"Processing task for session {session_id} failed with error (via callback): {e}", exc_info=True)
        # Обновить метаданные: статус = "error", message = str(e)
        # update_session_status(session_id, "error", str(e)) # Пример
    finally:
        if session_id in active_processing_tasks:
            del active_processing_tasks[session_id]
            logger.debug(f"Removed task for session {session_id} from active_processing_tasks.")

# --- Конец изменений: Управление фоновыми задачами ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)

async def broadcast_update(data: dict):
    """Broadcast update to all connected clients"""
    for connection in active_connections:
        try:
            await connection.send_json(data)
        except:
            # Remove dead connections
            active_connections.remove(connection)

# Маршрут для главной страницы
@app.get("/")
async def read_root():
    return FileResponse("frontend/index.html")

# --- Session Management Endpoints --- 

@app.get("/api/sessions", tags=["Sessions"], summary="List all processing sessions")
async def get_sessions():
    """Retrieves metadata for all recorded processing sessions."""
    metadata = load_session_metadata()
    # Optional: Sort sessions by timestamp_created descending?
    # metadata.sort(key=lambda s: s.get('timestamp_created', ''), reverse=True)
    return metadata

@app.get("/api/sessions/{session_id}", tags=["Sessions"], summary="Get specific session details")
async def get_session_details(session_id: str):
    """Retrieves metadata for a specific session by its ID."""
    metadata = load_session_metadata()
    session_data = next((s for s in metadata if s.get('session_id') == session_id), None)
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session with ID '{session_id}' not found.")
    return session_data

@app.post("/api/sessions", tags=["Sessions"], summary="Create a new processing session")
async def create_new_session(
    file: UploadFile = File(...), 
    context_text: Optional[str] = Form(None), 
    run_standard_pipeline: bool = Form(True),
    run_llm_deep_search_pipeline: bool = Form(True)
):
    """
    Creates a new processing session by uploading an input file (CSV/XLSX) 
    and optional context text. Both standard and LLM deep search pipelines will run by default.
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
        logging.warning(f"Session ID collision detected, generated new ID: {session_id}")

    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Created session directory: {session_dir}")
    except OSError as e:
        logging.error(f"Could not create session directory {session_dir}. Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session directory.")

    input_file_path = session_dir / f"input_{file.filename}"
    context_file_path = session_dir / "context_used.txt"

    file_saved_successfully = False
    try:
        async with aiofiles.open(input_file_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024):
                await out_file.write(content)
        logging.info(f"Saved uploaded file to: {input_file_path}")
        file_saved_successfully = True
    except Exception as e:
        logging.error(f"Failed to save uploaded file {input_file_path}: {e}")
        try: shutil.rmtree(session_dir); logging.info(f"Cleaned up session dir due to file save error: {session_dir}")
        except Exception as e_clean: logging.error(f"Failed to cleanup session dir {session_dir}: {e_clean}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file.")
    finally:
        await file.close()

    context_saved_successfully = True
    if context_text:
        try:
            async with aiofiles.open(context_file_path, 'w', encoding='utf-8') as context_file:
                await context_file.write(context_text)
            logging.info(f"Saved context text to: {context_file_path}")
        except Exception as e:
            logging.error(f"Failed to save context file {context_file_path}: {e}")
            context_saved_successfully = False

    if file_saved_successfully:
        try:
            if str(input_file_path).endswith('.csv'):
                df = pd.read_csv(input_file_path)
            else:
                df = pd.read_excel(input_file_path)
            total_companies = len(df)
        except Exception:
            total_companies = None
        
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
            "total_companies": total_companies,
            "error_message": None if context_saved_successfully else "Failed to save context file",
            "run_standard_pipeline": run_standard_pipeline,
            "run_llm_deep_search_pipeline": run_llm_deep_search_pipeline
        }
        
        metadata.append(new_session_data)
        try:
            save_session_metadata(metadata)
            logging.info(f"Added new session metadata for ID: {session_id}")
        except Exception as e:
             logging.error(f"Failed to save session metadata after creating session {session_id}: {e}")
             raise HTTPException(status_code=500, detail="Failed to save session metadata.")

        return new_session_data
    else:
        logging.error(f"File saving reported failure, metadata not saved for potential session {session_id}.")
        return { "detail": "Internal server error during file processing." }

@app.post("/api/sessions/{session_id}/start", tags=["Sessions"], summary="Start processing for a session")
async def start_session_processing(session_id: str, background_tasks: BackgroundTasks):
    """
    Starts the data processing pipeline for the specified session in the background.
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
        logging.info(f"Re-running session '{session_id}' which previously ended in error.")
        # Allow re-running errored sessions
        
    # 3. Check if input file exists (sanity check)
    input_file_path_rel = session_data.get("input_file_path")
    if not input_file_path_rel or not (PROJECT_ROOT / input_file_path_rel).exists():
        logging.error(f"Input file path missing or file not found for session {session_id}: {input_file_path_rel}")
        # Update status to error maybe?
        session_data['status'] = 'error'
        session_data['error_message'] = "Input file missing or path invalid in metadata."
        save_session_metadata(all_metadata)
        raise HTTPException(status_code=400, detail="Input file path missing or invalid in session metadata.")

    # --- Wrap task adding in try/except --- 
    try:
        # Update status to 'queued' or 'starting' immediately before adding task?
        # Might be better to update status to 'running' inside the task itself.
        # For now, we just add the task.
        
        background_tasks.add_task(run_session_pipeline, session_id, broadcast_update)
        logging.info(f"Added pipeline run for session {session_id} to background tasks.")
        
        # Update status IN METADATA immediately after successfully adding task?
        # This prevents UI showing old status until task actually starts running.
        session_data['status'] = 'queued' # Or 'starting'
        session_data['error_message'] = None # Clear previous errors on restart
        save_session_metadata(all_metadata)
        logging.info(f"Updated session {session_id} status to 'queued' in metadata.")
        
    except Exception as e_task:
        logging.error(f"Failed to add background task for session {session_id}: {e_task}")
        # Don't change status if adding task failed
        raise HTTPException(status_code=500, detail=f"Failed to queue processing task for session {session_id}.")
    # --- End Wrap --- 

    # 5. Return immediate response
    return {"message": f"Processing queued in background for session {session_id}"}

@app.get("/api/sessions/{session_id}/results", tags=["Sessions"], summary="Get session results")
async def get_session_results(session_id: str):
    """Retrieves the processed results from the session's CSV file."""
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
        logging.warning(f"Results file {output_csv_path} not found for session {session_id}, returning empty list.")
        return [] 
        
    try:
        # Check if file is empty or only has header
        if output_csv_path.stat().st_size < 50: # Small threshold
             logging.info(f"Results file {output_csv_path} is empty or header only for session {session_id}. Returning empty list.")
             return []
             
        # Read CSV using pandas, assuming comma separator from our writer
        df = pd.read_csv(output_csv_path, sep=',', encoding='utf-8-sig')
        # Convert NaN/NaT to None (which becomes null in JSON)
        df = df.where(pd.notnull(df), None)
        results = df.to_dict(orient='records')
        return results
    except pd.errors.EmptyDataError:
        logging.warning(f"Results file {output_csv_path} is empty for session {session_id}. Returning empty list.")
        return []
    except Exception as e:
        logging.error(f"Error reading results CSV for session {session_id} from {output_csv_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read or parse results file for session '{session_id}'.")

@app.get("/api/sessions/{session_id}/logs/{log_type}", tags=["Sessions"], summary="Get session log file content")
async def get_session_log(session_id: str, log_type: str):
    """
    Retrieves the content of a specific log file (pipeline or scoring) for a session.
    Returns the content as plain text.
    """
    if log_type not in ["pipeline", "scoring"]:
        raise HTTPException(status_code=400, detail="Invalid log_type. Must be 'pipeline' or 'scoring'.")
        
    all_metadata = load_session_metadata()
    session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
    
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session with ID '{session_id}' not found.")
        
    log_path_key = f"{log_type}_log_path" # e.g., pipeline_log_path
    log_file_path_rel = session_data.get(log_path_key)
    
    if not log_file_path_rel:
        raise HTTPException(status_code=404, detail=f"Log file path for '{log_type}' not found in metadata for session '{session_id}'.")
        
    log_file_path = PROJECT_ROOT / log_file_path_rel
    
    if not log_file_path.exists():
        logging.warning(f"Log file {log_file_path} not found for session {session_id}, log_type {log_type}. Returning empty response.")
        # Return empty text or 404? 404 seems more accurate if the file path exists in metadata but file is missing
        raise HTTPException(status_code=404, detail=f"{log_type.capitalize()} log file not found at expected path for session '{session_id}'.")
        
    try:
        # Read the entire log file content (for potentially large logs, consider reading last N lines or streaming)
        async with aiofiles.open(log_file_path, mode='r', encoding='utf-8') as log_file:
            content = await log_file.read()
        return PlainTextResponse(content=content)
        
    except Exception as e:
        logging.error(f"Error reading log file {log_file_path} for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read {log_type} log file for session '{session_id}'.")

# --- Placeholder for future routes --- 
# Example:
# from .routers import sessions # Assuming routes are split into routers
# app.include_router(sessions.router)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # Create session directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = os.path.join(OUTPUT_DIR, f"{timestamp}_input_{file.filename}")
    os.makedirs(session_dir, exist_ok=True)
    
    # Save uploaded file
    file_path = os.path.join(session_dir, file.filename)
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Start processing in background
    asyncio.create_task(process_companies(file_path, session_dir, broadcast_update))
    
    return {"message": "File uploaded and processing started", "session_dir": session_dir}

@app.get("/download/{session_dir}/{filename}")
async def download_file(session_dir: str, filename: str):
    file_path = os.path.join(OUTPUT_DIR, session_dir, filename)
    return FileResponse(file_path, filename=filename)

@app.get("/app.js")
async def read_js():
    return FileResponse("frontend/app.js")

@app.get("/style.css")
async def read_css():
    return FileResponse("frontend/style.css")

# Пример существующего эндпоинта для запуска сессии (адаптируйте под ваш)
@app.post("/api/sessions/{session_id}/start", tags=["Sessions"], summary="Start processing for a session")
async def start_processing_session(session_id: str): # Убрал BackgroundTasks, так как управляем явно
    # 1. Проверка существования сессии и ее статуса (не "processing" или "completed")
    #    Это важно, чтобы не запускать обработку для уже обработанной или обрабатываемой сессии.
    #    (Логика получения метаданных сессии, например, из JSON файла)
    #    sessions_metadata = load_session_metadata()
    #    session_meta = next((s for s in sessions_metadata if s["id"] == session_id), None)
    #    if not session_meta:
    #        raise HTTPException(status_code=404, detail="Session not found")
    #    if session_meta.get("status") == "processing":
    #        raise HTTPException(status_code=400, detail="Session is already processing")
    #    if session_meta.get("status") == "completed":
    #        logger.info(f"Session {session_id} is already completed. No action taken.")
    #        return {"status": "already_completed", "session_id": session_id}

    logger.info(f"Request to start processing for session_id: {session_id}")

    # 2. Отмена предыдущей задачи, если она существует и активна для этой сессии
    if session_id in active_processing_tasks and not active_processing_tasks[session_id].done():
        logger.warning(f"Session {session_id} has an active processing task. Cancelling it before starting a new one.")
        active_processing_tasks[session_id].cancel()
        try:
            await asyncio.wait_for(active_processing_tasks[session_id], timeout=10.0) # Даем время на отмену
        except asyncio.CancelledError:
            logger.info(f"Previous task for session {session_id} was successfully cancelled.")
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for previous task for session {session_id} to cancel. It might still be running.")
        except Exception as e:
            logger.error(f"Error awaiting previous cancelled task for session {session_id}: {e}")
        # Удаление из словаря произойдет в колбэке отмененной задачи
    
    # 3. Подготовка путей и параметров для пайплайна
    #    Эти пути должны быть уникальными для сессии!
    #    Пример:
    base_session_dir = Path("sessions_data") / session_id
    base_session_dir.mkdir(parents=True, exist_ok=True) # Создаем директорию сессии

    input_file_name = "uploaded_file.csv" # Имя файла должно браться из метаданных сессии
    input_file = base_session_dir / input_file_name # Путь к загруженному файлу для этой сессии
    
    # Убедитесь, что input_file существует (был загружен ранее)
    if not input_file.exists():
        logger.error(f"Input file {input_file} not found for session {session_id}.")
        raise HTTPException(status_code=404, detail=f"Input file for session {session_id} not found.")

    output_csv_file = base_session_dir / "results.csv"
    
    # Уникальные логи для сессии
    logs_dir = Path("output") / "logs" / session_id
    logs_dir.mkdir(parents=True, exist_ok=True)
    pipeline_log_path = logs_dir / f"pipeline_{session_id}.log"
    scoring_log_path = logs_dir / f"scoring_{session_id}.log"

    # Получение контекста (если есть)
    # context_text = session_meta.get("context_text") 
    context_text: Optional[str] = None # Заглушка

    # Обновление статуса сессии на "processing"
    # update_session_status(session_id, "processing") # Пример

    # 4. Создание и запуск новой задачи
    logger.info(f"Creating processing task for session: {session_id}")
    task = asyncio.create_task(
        execute_pipeline_for_session_async(
            session_id, 
            input_file, 
            output_csv_file,
            pipeline_log_path,
            scoring_log_path,
            context_text,
            llm_config={} # Заглушка, так как llm_config не передается в этом вызове
        )
    )
    active_processing_tasks[session_id] = task
    task.add_done_callback(lambda t: _processing_task_done_callback(t, session_id))

    logger.info(f"Processing task for session {session_id} created and started.")
    return {"status": "processing_started", "session_id": session_id}

@app.post("/api/sessions/{session_id}/cancel", tags=["Sessions"], summary="Cancel processing for a session")
async def cancel_processing_session(session_id: str):
    logger.info(f"Request to cancel processing for session_id: {session_id}")
    if session_id in active_processing_tasks:
        task = active_processing_tasks[session_id]
        if not task.done():
            task.cancel()
            logger.info(f"Cancellation request sent to task for session {session_id}.")
            # Удаление из active_processing_tasks произойдет в _processing_task_done_callback
            return {"status": "cancellation_requested", "session_id": session_id}
        else:
            logger.info(f"Task for session {session_id} is already done. Nothing to cancel.")
            # Можно удалить из словаря, если колбэк по какой-то причине не сработал
            if session_id in active_processing_tasks: del active_processing_tasks[session_id]
            return {"status": "task_already_done", "session_id": session_id}
    else:
        logger.warning(f"No active task found for session {session_id} to cancel.")
        return {"status": "no_active_task", "session_id": session_id, "message": "No active processing task found for this session."}

# Пример эндпоинта для получения статуса (нужно адаптировать)
@app.get("/api/sessions/{session_id}/status", tags=["Sessions"], summary="Get session status")
async def get_session_status(session_id: str):
    # Здесь должна быть логика чтения метаданных сессии (например, из JSON файла)
    # sessions_metadata = load_session_metadata()
    # session_meta = next((s for s in sessions_metadata if s["id"] == session_id), None)
    # if not session_meta:
    #     raise HTTPException(status_code=404, detail="Session not found")

    status = "unknown" # session_meta.get("status", "unknown")
    message = "" # session_meta.get("message", "")
    
    if session_id in active_processing_tasks and not active_processing_tasks[session_id].done():
        status = "processing"
        message = "Processing is ongoing."
    
    # Дополнительно: можно добавить информацию о прогрессе, если ваш пайплайн ее как-то обновляет
    # progress = get_session_progress(session_id) # Ваша функция для получения прогресса

    return {"session_id": session_id, "status": status, "message": message} #, "progress": progress}

# Важно: При завершении работы сервера FastAPI (graceful shutdown),
# нужно попытаться отменить все активные задачи.
@app.on_event("shutdown")
async def app_shutdown():
    logger.info("Application shutdown initiated. Cancelling all active processing tasks...")
    for session_id, task in list(active_processing_tasks.items()): # list() для копии, т.к. словарь может меняться
        if not task.done():
            logger.info(f"Cancelling task for session {session_id} during app shutdown.")
            task.cancel()
            try:
                # Даем немного времени на обработку отмены
                await asyncio.wait_for(task, timeout=10.0) 
            except asyncio.CancelledError:
                logger.info(f"Task for session {session_id} successfully cancelled during shutdown.")
            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for task {session_id} to cancel during shutdown. It might not have fully cleaned up.")
            except Exception as e:
                logger.error(f"Error during task cancellation for session {session_id} on shutdown: {e}")
        if session_id in active_processing_tasks: # Проверяем снова, т.к. колбэк мог уже удалить
            del active_processing_tasks[session_id]
    logger.info("All active tasks processed for cancellation during shutdown.")

# --- Конец примера изменений ---

if __name__ == "__main__":
    # This is for local development testing
    # Ensure the CWD is the backend directory or adjust paths accordingly if run differently
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True) 