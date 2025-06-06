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
from typing import Dict, List, Any, Optional
import aiohttp
from openai import AsyncOpenAI
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient
import tempfile # Added for temporary file for zip archive
import numpy as np

# Adjust sys.path to allow importing from src
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Обновленные импорты для использования новой структуры
from src.pipeline import run_pipeline  # Новая публичная функция запуска пайплайна
from src.pipeline.adapter import PipelineAdapter  # Класс с методом run_pipeline_for_file
from src.pipeline.core import process_companies  # Перенесенная функция
from src.pipeline.utils.logging import setup_session_logging  # Перенесенная функция
from src.config import OUTPUT_DIR, load_env_vars, load_llm_config
from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR

# --- Import background task runner --- 
from .processing_runner import run_session_pipeline

# --- Import routers ---
from .routers import sessions  # Импортируем роутер сессий
from .routers import criteria  # Импортируем роутер критериев

# Configure basic logging if not already configured elsewhere
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

# --- Регистрируем роутеры ---
app.include_router(sessions.router, prefix="/api")
app.include_router(criteria.router, prefix="/api")

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

    # Определяем базовые поля для CSV
    base_ordered_fields = ["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp", "validation_status", "validation_warning"]
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
        sb_client = CustomScrapingBeeClient(api_key=scrapingbee_api_key) 
        logger.info("[EXECUTE_PIPELINE] ScrapingBeeClient created.")
        openai_async_client = AsyncOpenAI(api_key=openai_api_key)
        logger.info("[EXECUTE_PIPELINE] AsyncOpenAI client created.")
        
        try:
            logger.info(f"[EXECUTE_PIPELINE] Using PipelineAdapter for session {session_id}...")
            
            # Используем PipelineAdapter вместо прямого вызова функции
            pipeline_adapter = PipelineAdapter(
                config_path="llm_config.yaml", 
                input_file=input_file,
                session_id=session_id,  # Передаем session_id в адаптер
                use_raw_llm_data_as_description=True  # Используем сырые данные LLM как описание
            )
            
            # Настраиваем адаптер
            pipeline_adapter.company_col_index = 0
            pipeline_adapter.output_csv_path = output_csv_file
            pipeline_adapter.pipeline_log_path = Path(str(pipeline_log_path))
            if hasattr(pipeline_adapter, "scoring_log_path"):
                pipeline_adapter.scoring_log_path = Path(str(scoring_log_path))
            
            # Инициализируем клиентов напрямую
            pipeline_adapter.openai_client = openai_async_client
            pipeline_adapter.sb_client = sb_client
            pipeline_adapter.aiohttp_session = aiohttp_session
            pipeline_adapter.llm_config = llm_config
            pipeline_adapter.api_keys = {
                "openai": openai_api_key,
                "serper": serper_api_key,
                "scrapingbee": scrapingbee_api_key
            }
            
            # Запускаем пайплайн
            await pipeline_adapter.run()
            
            logger.info(f"[EXECUTE_PIPELINE] Pipeline execution for session_id: {session_id} completed.")
        except asyncio.CancelledError:
            logger.info(f"[EXECUTE_PIPELINE] Pipeline execution for session_id: {session_id} was cancelled.")
            raise 
        except Exception as e:
            logger.error(f"[EXECUTE_PIPELINE] Error during pipeline execution for session_id {session_id}: {e}", exc_info=True)
    logger.info(f"[EXECUTE_PIPELINE] Finished for session_id: {session_id}")

# Callback-функция для задач
def _processing_task_done_callback(task: asyncio.Task, session_id: str):
    try:
        task.result()  # Проверяем, не было ли исключений в задаче
        logger.info(f"Processing task for session {session_id} finished successfully (via callback).")
        # Обновляем метаданные: статус = "completed"
        try:
            all_metadata = load_session_metadata()
            session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
            if session_data and session_data.get('status') != 'cancelled':  # Не перезаписываем статус cancelled
                session_data['status'] = 'completed'
                save_session_metadata(all_metadata)
                logger.info(f"Updated session {session_id} status to 'completed' in metadata")
        except Exception as e:
            logger.error(f"Failed to update session {session_id} metadata to completed: {e}")
    except asyncio.CancelledError:
        logger.info(f"Processing task for session {session_id} was cancelled (via callback).")
        # Обновляем метаданные: статус = "cancelled"
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
        # Обновляем метаданные: статус = "error"
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
        if session_id in active_processing_tasks:
            del active_processing_tasks[session_id]
            logger.info(f"Removed task for session {session_id} from active_processing_tasks.")

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

@app.post("/api/sessions", tags=["Sessions"], summary="Create a new processing session")
async def create_new_session(
    file: UploadFile = File(...), 
    context_text: Optional[str] = Form(None), 
    run_llm_deep_search_pipeline: bool = Form(True),
    write_to_hubspot: bool = Form(True)
):
    """
    Creates a new processing session by uploading an input file (CSV/XLSX) 
    and optional context text. Only files with two columns (Company Name and Website URL) are accepted.
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
            
            # Валидация: файл должен содержать минимум две колонки
            if df.shape[1] < 2:
                try: shutil.rmtree(session_dir); logging.info(f"Cleaned up session dir due to validation error: {session_dir}")
                except Exception as e_clean: logging.error(f"Failed to cleanup session dir {session_dir}: {e_clean}")
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
        # Создаем задачу и регистрируем её в active_processing_tasks
        task = asyncio.create_task(run_session_pipeline(session_id, broadcast_update))
        active_processing_tasks[session_id] = task
        
        # Добавляем callback для очистки задачи после завершения
        task.add_done_callback(lambda t: _processing_task_done_callback(t, session_id))
        
        logging.info(f"Added pipeline run for session {session_id} to background tasks and active_processing_tasks.")
        
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
        
        # Обрабатываем специальные числовые значения, которые не могут быть сериализованы в JSON
        for col in df.select_dtypes(include=['float', 'float64']).columns:
            df[col] = df[col].apply(lambda x: None if pd.isna(x) or np.isinf(x) else x)
            
        # Конвертируем DataFrame в словари
        results = df.to_dict(orient='records')
        
        # Дополнительная очистка для JSON сериализации
        def clean_for_json(obj):
            if isinstance(obj, float):
                if np.isnan(obj) or np.isinf(obj):
                    return None
                return obj
            elif isinstance(obj, (np.integer, np.floating)):
                return obj.item()
            elif obj is pd.NaT or obj is None:
                return None
            elif isinstance(obj, str):
                return obj
            else:
                return str(obj)
        
        # Применяем очистку ко всем значениям
        cleaned_results = []
        for result in results:
            cleaned_result = {key: clean_for_json(value) for key, value in result.items()}
            cleaned_results.append(cleaned_result)
            
        return cleaned_results
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

@app.get("/api/sessions/{session_id}/download_archive", tags=["Sessions"], summary="Download session archive")
async def download_session_archive(session_id: str, background_tasks: BackgroundTasks):
    """
    Downloads a ZIP archive of the entire specified session directory.
    """
    all_metadata = load_session_metadata()
    session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)

    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session with ID '{session_id}' not found.")

    session_dir_path = SESSIONS_DIR / session_id
    if not session_dir_path.is_dir():
        logger.error(f"Session directory not found for session_id: {session_id} at path: {session_dir_path}")
        raise HTTPException(status_code=404, detail=f"Session directory for ID '{session_id}' not found on server.")

    # Create a temporary file for the archive
    try:
        # We need a temporary file path that shutil.make_archive can write to.
        # tempfile.NamedTemporaryFile creates a file, make_archive needs a base name for the archive.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmpfile:
            temp_zip_path_obj = Path(tmpfile.name)
        
        # shutil.make_archive will append '.zip' to base_name if format is 'zip'
        # So, we give it the path without the .zip suffix.
        archive_base_name = temp_zip_path_obj.with_suffix('') 
        
        archive_path_str = shutil.make_archive(
            base_name=str(archive_base_name), 
            format='zip', 
            root_dir=str(SESSIONS_DIR), # Archive contents relative to SESSIONS_DIR
            base_dir=session_id        # The directory to archive within SESSIONS_DIR
        )
        
        archive_path = Path(archive_path_str) # Convert back to Path object

        if not archive_path.exists():
            logger.error(f"Failed to create archive for session {session_id} at {archive_path}")
            raise HTTPException(status_code=500, detail="Failed to create session archive.")

        # Schedule the removal of the temporary archive file after the response is sent
        background_tasks.add_task(os.remove, archive_path)

        return FileResponse(
            path=archive_path,
            filename=f"{session_id}_archive.zip",
            media_type='application/zip'
        )
    except Exception as e:
        logger.error(f"Error creating or serving session archive for {session_id}: {e}", exc_info=True)
        # Clean up temp file if it exists and an error occurred before FileResponse
        if 'archive_path' in locals() and archive_path.exists(): # type: ignore
            try:
                os.remove(archive_path) # type: ignore
            except Exception as e_clean:
                logger.error(f"Failed to clean up temporary archive {archive_path} after error: {e_clean}") # type: ignore
        elif 'temp_zip_path_obj' in locals() and temp_zip_path_obj.exists(): # type: ignore
             try:
                os.remove(temp_zip_path_obj) # type: ignore
             except Exception as e_clean:
                logger.error(f"Failed to clean up temporary file {temp_zip_path_obj} after error: {e_clean}") # type: ignore
        raise HTTPException(status_code=500, detail=f"Could not create or serve session archive: {str(e)}")

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
    file_path = OUTPUT_DIR / "sessions" / session_dir / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, filename=filename)

@app.get("/style.css")
async def read_css():
    return FileResponse("frontend/style.css")

# Пример существующего эндпоинта для запуска сессии (адаптируйте под ваш)
@app.post("/api/sessions/{session_id}/cancel", tags=["Sessions"], summary="Cancel processing for a session")
async def cancel_processing_session(session_id: str):
    logger.info(f"Request to cancel processing for session_id: {session_id}")
    
    # Обновляем статус в метаданных
    try:
        all_metadata = load_session_metadata()
        session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
        if session_data:
            session_data['status'] = 'cancelled'
            session_data['error_message'] = 'Processing cancelled by user'
            save_session_metadata(all_metadata)
            logger.info(f"Updated session {session_id} status to 'cancelled' in metadata")
    except Exception as e:
        logger.error(f"Failed to update session {session_id} metadata during cancellation: {e}")
    
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