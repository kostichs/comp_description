"""
Criteria Analysis Routes - Analysis Endpoints

Содержит endpoints для запуска анализа критериев:
- POST /analyze - анализ из загруженного файла
- POST /analyze_from_session - анализ из существующей сессии
"""

import json
import shutil
import asyncio
import aiofiles
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from starlette.background import BackgroundTasks

from ..common import (
    logger, criteria_sessions, criteria_tasks, 
    generate_criteria_session_id, run_criteria_processor,
    cleanup_old_sessions, cleanup_temp_sessions,
    SESSIONS_DIR, SESSIONS_METADATA_FILE
)

router = APIRouter()

async def run_criteria_analysis_task(
    session_id: str,
    input_file_path: Path,
    load_all_companies: bool = False,
    use_deep_analysis: bool = False,
    use_parallel: bool = True,
    max_concurrent: int = 12,
    selected_products: list = None,
    selected_criteria_files: list = None,
    write_to_hubspot_criteria: bool = False
):
    """Асинхронная задача для запуска анализа критериев"""
    try:
        logger.info(f"Starting criteria analysis for session {session_id}")
        
        # Обновляем статус
        criteria_sessions[session_id]["status"] = "processing"
        criteria_sessions[session_id]["start_time"] = datetime.now().isoformat()
        
        # Запускаем анализ как отдельный процесс
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            run_criteria_processor,
            str(input_file_path),
            load_all_companies,
            session_id,
            use_deep_analysis,
            use_parallel,
            max_concurrent,
            selected_products,
            selected_criteria_files,
            write_to_hubspot_criteria
        )
        
        # Проверяем результат выполнения процесса
        if result["status"] == "success":
            criteria_sessions[session_id].update({
                "status": "completed",
                "end_time": datetime.now().isoformat(),
                "output": result["output"]
            })
            logger.info(f"Completed criteria analysis for session {session_id}")
        else:
            criteria_sessions[session_id].update({
                "status": "failed",
                "error": result["error"],
                "end_time": datetime.now().isoformat()
            })
            logger.error(f"Criteria analysis failed for session {session_id}: {result['error']}")
        
    except Exception as e:
        error_msg = f"Error in criteria analysis for session {session_id}: {e}"
        logger.error(error_msg)
        
        criteria_sessions[session_id].update({
            "status": "failed",
            "error": str(e),
            "end_time": datetime.now().isoformat()
        })
    finally:
        # Удаляем задачу из активных
        if session_id in criteria_tasks:
            del criteria_tasks[session_id]

@router.post("/analyze")
async def create_criteria_analysis(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    load_all_companies: bool = Form(False),
    use_deep_analysis: bool = Form(False),
    use_parallel: bool = Form(True),
    max_concurrent: int = Form(12),
    selected_products: str = Form("[]"),
    selected_criteria_files: str = Form("[]"),
    write_to_hubspot_criteria: bool = Form(False)
):
    """
    Создает новую сессию анализа критериев
    
    - **file**: CSV файл с описаниями компаний 
    - **load_all_companies**: Загружать ли все файлы из папки data
    - **use_deep_analysis**: Использовать ли глубокий анализ
    - **use_parallel**: Параллельная обработка компаний (включена по умолчанию)
    - **max_concurrent**: Максимальное количество одновременно обрабатываемых компаний (по умолчанию 12)
    """
    try:
        # Очищаем старые сессии перед запуском нового анализа
        cleanup_old_sessions(max_sessions=10)
        cleanup_temp_sessions(max_sessions=10)
        
        # Проверяем формат файла
        if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
            raise HTTPException(
                status_code=400, 
                detail="Unsupported file format. Use CSV or Excel files."
            )
        
        # Генерируем ID сессии
        session_id = generate_criteria_session_id()
        
        # Создаем временную папку для этой сессии
        session_dir = Path("temp") / "criteria_analysis" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем загруженный файл с правильной обработкой кодировки
        input_file_path = session_dir / file.filename
        async with aiofiles.open(input_file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Log basic file info
        logger.info(f"Uploaded file: {file.filename} ({len(content)} bytes)")
        
        # Parse selected criteria files or fallback to selected products
        try:
            selected_criteria_files_list = json.loads(selected_criteria_files) if selected_criteria_files != "[]" else []
        except json.JSONDecodeError:
            selected_criteria_files_list = []
        
        # Fallback to selected_products for backward compatibility
        if not selected_criteria_files_list:
            try:
                selected_products_list = json.loads(selected_products) if selected_products else []
            except json.JSONDecodeError:
                selected_products_list = []
        else:
            selected_products_list = []
        
        logger.info(f"Selected criteria files for session analysis: {selected_criteria_files_list}")
        logger.info(f"Selected products (fallback) for session analysis: {selected_products_list}")

        # Создаем метаданные сессии
        criteria_sessions[session_id] = {
            "session_id": session_id,
            "status": "created",
            "created_time": datetime.now().isoformat(),
            "filename": file.filename,
            "file_size": len(content),
            "input_file_path": str(input_file_path),
            "load_all_companies": load_all_companies,
            "use_deep_analysis": use_deep_analysis,
            "use_parallel": use_parallel,
            "max_concurrent": max_concurrent,
            "selected_products": selected_products_list,
            "selected_criteria_files": selected_criteria_files_list
        }
        
        # Запускаем анализ в фоновой задаче
        task = asyncio.create_task(
            run_criteria_analysis_task(
                session_id, 
                input_file_path, 
                load_all_companies,
                use_deep_analysis,
                use_parallel,
                max_concurrent,
                selected_products_list,
                selected_criteria_files_list,
                write_to_hubspot_criteria
            )
        )
        criteria_tasks[session_id] = task
        
        logger.info(f"Created criteria analysis session: {session_id}")
        
        return {
            "session_id": session_id,
            "status": "created",
            "message": "Criteria analysis session created and started"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating criteria analysis session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create analysis session: {str(e)}")

@router.post("/analyze_from_session")
async def create_criteria_analysis_from_session(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    load_all_companies: bool = Form(False),
    use_deep_analysis: bool = Form(False),
    use_parallel: bool = Form(True),
    max_concurrent: int = Form(12),
    selected_products: str = Form("[]"),  # Backward compatibility
    selected_criteria_files: str = Form("[]"),  # NEW: JSON string of selected criteria files
    write_to_hubspot_criteria: bool = Form(False)  # NEW: HubSpot integration flag
):
    """
    Создает новую сессию анализа критериев используя результаты из существующей сессии
    
    - **session_id**: ID сессии из которой взять результаты
    - **load_all_companies**: Загружать ли все файлы из папки data
    - **use_deep_analysis**: Использовать ли глубокий анализ
    - **use_parallel**: Параллельная обработка компаний (включена по умолчанию)
    - **max_concurrent**: Максимальное количество одновременно обрабатываемых компаний (по умолчанию 12)
    - **selected_products**: JSON string выбранных продуктов для анализа
    """
    try:
        # Очищаем старые сессии перед запуском нового анализа
        cleanup_old_sessions(max_sessions=10)
        cleanup_temp_sessions(max_sessions=10)
        
        # Parse selected criteria files or fallback to selected products
        try:
            selected_criteria_files_list = json.loads(selected_criteria_files) if selected_criteria_files != "[]" else []
        except json.JSONDecodeError:
            selected_criteria_files_list = []
        
        # Fallback to selected_products for backward compatibility
        if not selected_criteria_files_list:
            try:
                selected_products_list = json.loads(selected_products) if selected_products else []
            except json.JSONDecodeError:
                selected_products_list = []
        else:
            selected_products_list = []
        
        logger.info(f"Selected criteria files for session analysis: {selected_criteria_files_list}")
        logger.info(f"Selected products (fallback) for session analysis: {selected_products_list}")
        
        # Получаем информацию о существующей сессии
        # Загружаем метаданные сессий через data_io.py (работает и локально и в Docker)
        metadata = []
        if SESSIONS_METADATA_FILE.exists():
            try:
                with open(SESSIONS_METADATA_FILE, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    if not isinstance(metadata, list):
                        metadata = []
            except Exception as e:
                logger.error(f"Error loading session metadata: {e}")
                metadata = []
        
        source_session = next((m for m in metadata if m.get("session_id") == session_id), None)
        
        if not source_session:
            raise HTTPException(status_code=404, detail=f"Source session {session_id} not found")
        
        if source_session.get("status") != "completed":
            raise HTTPException(status_code=400, detail=f"Source session {session_id} is not completed")
        
        # Ищем CSV файл с результатами в папке сессии
        session_dir = SESSIONS_DIR / session_id  # Используем динамический путь
        
        if not session_dir.exists():
            raise HTTPException(status_code=404, detail=f"Session directory not found for session {session_id}")
        
        # Ищем CSV файлы с результатами
        csv_files = list(session_dir.glob("*results*.csv"))
        if not csv_files:
            # Пытаемся найти любой CSV файл
            csv_files = list(session_dir.glob("*.csv"))
        
        if not csv_files:
            raise HTTPException(status_code=404, detail=f"No CSV results file found for session {session_id}")
        
        # Берем самый новый файл
        source_file_path = max(csv_files, key=lambda p: p.stat().st_ctime)
        
        # Генерируем ID новой сессии анализа критериев
        new_session_id = generate_criteria_session_id()
        
        # Создаем временную папку для новой сессии
        session_dir = Path("temp") / "criteria_analysis" / new_session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Копируем файл результатов в папку новой сессии
        input_file_path = session_dir / "source_results.csv"
        shutil.copy2(source_file_path, input_file_path)
        
        # Создаем метаданные новой сессии
        criteria_sessions[new_session_id] = {
            "session_id": new_session_id,
            "status": "created",
            "created_time": datetime.now().isoformat(),
            "filename": f"Results from session {session_id}",
            "source_session_id": session_id,
            "file_size": input_file_path.stat().st_size,
            "input_file_path": str(input_file_path),
            "load_all_companies": load_all_companies,
            "use_deep_analysis": use_deep_analysis,
            "use_parallel": use_parallel,
            "max_concurrent": max_concurrent,
            "selected_products": selected_products_list,
            "selected_criteria_files": selected_criteria_files_list
        }
        
        # Запускаем анализ в фоновой задаче
        task = asyncio.create_task(
            run_criteria_analysis_task(
                new_session_id, 
                input_file_path, 
                load_all_companies,
                use_deep_analysis,
                use_parallel,
                max_concurrent,
                selected_products_list,
                selected_criteria_files_list,
                write_to_hubspot_criteria
            )
        )
        criteria_tasks[new_session_id] = task
        
        logger.info(f"Created criteria analysis session from existing session: {new_session_id} (source: {session_id})")
        
        return {
            "session_id": new_session_id,
            "status": "created",
            "source_session_id": session_id,
            "message": f"Criteria analysis session created using results from session {session_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating criteria analysis session from existing session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create analysis session: {str(e)}") 