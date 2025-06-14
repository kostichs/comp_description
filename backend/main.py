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
from .api.routes.sessions import router as sessions_router  # NEW: Improved sessions router
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
app.include_router(sessions_router)  # NEW: Sessions API with /api/sessions prefix
app.include_router(criteria.router, prefix="/api")

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Store active WebSocket connections
active_connections: list[WebSocket] = []

# --- Начало изменений: Управление фоновыми задачами ---
# NOTE: active_processing_tasks moved to api/routes/sessions.py

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
    base_ordered_fields = ["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp", "validation_status", "validation_warning", "HubSpot_Company_ID", "Predator_ID"]
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
        # NOTE: active_processing_tasks cleanup moved to api/routes/sessions.py
        logger.info(f"Task cleanup for session {session_id} handled by sessions router.")

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

# --- Session Management Endpoints MOVED to api/routes/sessions.py ---

# --- Session endpoints MOVED to api/routes/sessions.py ---

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

# --- Session cancel/status endpoints MOVED to api/routes/sessions.py ---

# Важно: При завершении работы сервера FastAPI (graceful shutdown),
# нужно попытаться отменить все активные задачи.
# NOTE: active_processing_tasks moved to api/routes/sessions.py
@app.on_event("shutdown")
async def app_shutdown():
    logger.info("Application shutdown initiated.")
    # TODO: Import and cancel active_processing_tasks from sessions router
    # from .api.routes.sessions import active_processing_tasks
    # for session_id, task in list(active_processing_tasks.items()):
    #     if not task.done():
    #         task.cancel()
    logger.info("Shutdown completed.")

# --- Конец примера изменений ---

if __name__ == "__main__":
    # This is for local development testing
    # Ensure the CWD is the backend directory or adjust paths accordingly if run differently
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True) 