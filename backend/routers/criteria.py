"""
Роутер для анализа критериев компаний (изолированный микросервис)
"""

import sys
import os
import time
import logging
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import asyncio
import aiofiles
import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse, JSONResponse

# Добавляем путь к criteria_processor в sys.path СРАЗУ
CRITERIA_PROCESSOR_PATH = Path(__file__).parent.parent.parent / "services" / "criteria_processor"
if str(CRITERIA_PROCESSOR_PATH) not in sys.path:
    sys.path.insert(0, str(CRITERIA_PROCESSOR_PATH))

# Также добавляем путь к src папке criteria_processor
CRITERIA_SRC_PATH = CRITERIA_PROCESSOR_PATH / "src"
if str(CRITERIA_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(CRITERIA_SRC_PATH))

# Добавляем корневой путь criteria_processor для внутренних импортов
if str(CRITERIA_PROCESSOR_PATH) not in sys.path:
    sys.path.insert(0, str(CRITERIA_PROCESSOR_PATH))

# Импортируем правильные пути из data_io.py
from src.data_io import SESSIONS_DIR, SESSIONS_METADATA_FILE

def run_criteria_processor(input_file_path: str, load_all_companies: bool = False, session_id: str = None, use_deep_analysis: bool = False, use_parallel: bool = True, max_concurrent: int = 12, selected_products: List[str] = None, selected_criteria_files: List[str] = None, write_to_hubspot_criteria: bool = False):
    """Запускаем criteria_processor как отдельный процесс"""
    import subprocess
    import shutil
    import os
    
    try:
        if load_all_companies:
            cmd = [
                "python", 
                str(CRITERIA_PROCESSOR_PATH / "main.py"),
                "--all-files"
            ]
            if session_id:
                cmd.extend(["--session-id", session_id])
        else:
            # Очищаем папку data от старых файлов перед копированием нового
            data_dir = CRITERIA_PROCESSOR_PATH / "data"
            data_dir.mkdir(exist_ok=True)
            
            # Удаляем все CSV файлы из data папки
            for old_file in data_dir.glob("*.csv"):
                old_file.unlink()
                logger.info(f"Removed old file: {old_file}")
            
            # Копируем новый файл в data папку criteria_processor
            source_path = Path(input_file_path)
            target_path = data_dir / source_path.name
            
            # Логируем пути
            logger.info(f"Copying file: {source_path} -> {target_path}")
            
            # Копируем файл
            shutil.copy2(source_path, target_path)
            
            # Проверяем что файл скопировался
            if target_path.exists():
                logger.info(f"File copied successfully: {target_path}")
            else:
                logger.error(f"File copy failed: {target_path}")
                return {"status": "error", "error": "Failed to copy file to data directory"}
            
            cmd = [
                "python", 
                str(CRITERIA_PROCESSOR_PATH / "main.py"),
                "--file", f"data/{target_path.name}",  # Путь относительно criteria_processor
                "--session-id", session_id  # Передаем session_id для создания отдельной папки
            ]
        
        if use_deep_analysis:
            cmd.append("--deep-analysis")
        
        # Добавляем параметры параллельной обработки
        if use_parallel:
            cmd.append("--parallel")
            cmd.extend(["--max-concurrent", str(max_concurrent)])
        
        # НОВАЯ ЛОГИКА: Обрабатываем выбранные файлы критериев
        if selected_criteria_files:
            # Преобразуем имена файлов в продукты
            # Читаем файлы критериев и извлекаем продукты только из выбранных файлов
            criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
            selected_products_from_files = []
            
            for filename in selected_criteria_files:
                file_path = criteria_dir / filename
                if file_path.exists():
                    try:
                        if file_path.suffix.lower() == '.csv':
                            import pandas as pd
                            df = pd.read_csv(file_path)
                            if 'Product' in df.columns:
                                file_products = df['Product'].unique().tolist()
                                file_products = [p for p in file_products if pd.notna(p) and str(p).strip()]
                                selected_products_from_files.extend(file_products)
                                logger.info(f"From file {filename} extracted products: {file_products}")
                    except Exception as e:
                        logger.error(f"Error reading criteria file {filename}: {e}")
            
            # Удаляем дубликаты
            selected_products_from_files = list(set(selected_products_from_files))
            logger.info(f"Final products from selected files: {selected_products_from_files}")
            
            if selected_products_from_files:
                cmd.append("--selected-products")
                cmd.append(",".join(selected_products_from_files))
                logger.info(f"Adding products from selected files to command: {selected_products_from_files}")
            
        # Fallback к старой логике с selected_products
        elif selected_products:
            cmd.append("--selected-products")
            cmd.append(",".join(selected_products))
            logger.info(f"Adding selected products to command: {selected_products}")
        else:
            logger.info("No selected products or files specified - will process all products")
        
        # Add Circuit Breaker support (enabled by default, can be disabled via env var)
        import os
        if os.getenv('DISABLE_CIRCUIT_BREAKER', 'false').lower() == 'true':
            cmd.append("--disable-circuit-breaker")
            logger.info("Circuit Breaker отключен через переменную окружения")
        
        # Add HubSpot integration flag
        logger.info(f"🔍 HUBSPOT ПАРАМЕТР ПРОВЕРКА:")
        logger.info(f"   🔗 write_to_hubspot_criteria = {write_to_hubspot_criteria}")
        logger.info(f"   📝 Тип параметра: {type(write_to_hubspot_criteria)}")
        
        if write_to_hubspot_criteria:
            cmd.append("--write-to-hubspot-criteria")
            logger.info("✅ HubSpot интеграция включена - добавлен флаг --write-to-hubspot-criteria")
        else:
            logger.info("📝 HubSpot интеграция отключена - флаг НЕ добавлен")
        
        # Log the full command for debugging ПОСЛЕ добавления всех флагов
        logger.info(f"🚀 ИТОГОВАЯ КОМАНДА: {' '.join(cmd)}")
        
        # Меняем рабочую директорию на criteria_processor
        # Устанавливаем UTF-8 кодировку для Windows
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONLEGACYWINDOWSSTDIO'] = '0'
        
        result = subprocess.run(
            cmd, 
            cwd=str(CRITERIA_PROCESSOR_PATH),
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            env=env,
            timeout=None  # Без ограничений - пусть работает сколько нужно
        )
        
        if result.returncode == 0:
            logger.info(f"Criteria processor completed successfully")
            return {"status": "success", "output": result.stdout}
        else:
            logger.error(f"Criteria processor failed: {result.stderr}")
            return {"status": "error", "error": result.stderr}
            
    except subprocess.TimeoutExpired:
        logger.error("Criteria processor timed out")
        return {"status": "error", "error": "Process timed out"}
    except Exception as e:
        logger.error(f"Error running criteria processor: {e}")
        return {"status": "error", "error": str(e)}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/criteria", tags=["Criteria Analysis"])

# Хранилище активных сессий анализа критериев
# Формат: {"session_id": {"status": "processing|completed|failed", "result_path": "...", ...}}
criteria_sessions: Dict[str, Dict[str, Any]] = {}

# Хранилище активных задач
criteria_tasks: Dict[str, asyncio.Task] = {}

def generate_criteria_session_id() -> str:
    """Генерирует уникальный ID сессии с префиксом crit_"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"crit_{timestamp}"

# Функция cleanup_old_backups удалена - backup файлы больше не создаются

async def run_criteria_analysis_task(
    session_id: str,
    input_file_path: Path,
    load_all_companies: bool = False,
    use_deep_analysis: bool = False,
    use_parallel: bool = True,
    max_concurrent: int = 12,
    selected_products: List[str] = None,
    selected_criteria_files: List[str] = None,
    write_to_hubspot_criteria: bool = False
):
    """Асинхронная задача для запуска анализа критериев"""
    log_info = None
    log_error = None
    
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
    selected_products: str = Form("[]"),  # Backward compatibility
    selected_criteria_files: str = Form("[]"),  # NEW: JSON string of selected criteria files
    write_to_hubspot_criteria: bool = Form(False)  # NEW: HubSpot integration flag
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
        import json
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
        # Parse selected criteria files or fallback to selected products
        import json
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
        import json
        
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
        import glob
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
            "file_size": os.path.getsize(input_file_path),
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

@router.get("/sessions")
async def get_criteria_sessions():
    """Получить список всех сессий анализа критериев"""
    return list(criteria_sessions.values())

@router.get("/sessions/{session_id}")
async def get_criteria_session(session_id: str):
    """Получить информацию о конкретной сессии анализа критериев"""
    if session_id not in criteria_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return criteria_sessions[session_id]

@router.get("/sessions/{session_id}/status")
async def get_criteria_session_status(session_id: str):
    """Получить только статус сессии анализа критериев"""
    if session_id not in criteria_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_data = criteria_sessions[session_id]
    return {
        "session_id": session_id,
        "status": session_data["status"],
        "progress": "In progress..." if session_data["status"] == "processing" else "Complete"
    }

@router.get("/sessions/{session_id}/results")
async def get_criteria_session_results(session_id: str):
    """Получить результаты анализа критериев"""
    if session_id not in criteria_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_data = criteria_sessions[session_id]
    
    if session_data["status"] != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"Analysis not completed. Current status: {session_data['status']}"
        )
    
    # Ищем файлы результатов в папке сессии
    session_results_dir = CRITERIA_PROCESSOR_PATH / "output" / session_id
    
    logger.info(f"Looking for results in: {session_results_dir}")
    
    if not session_results_dir.exists():
        logger.error(f"Session results directory not found: {session_results_dir}")
        return {
            "session_id": session_id, 
            "status": "completed",
            "results_count": 0,
            "results": [],
            "message": f"Session results directory not found: {session_results_dir}"
        }
    
    result_files = []
    
    # Поиск CSV и JSON файлов с результатами в папке сессии
    for pattern in ["*.csv", "*.json"]:
        found_files = list(session_results_dir.glob(pattern))
        result_files.extend(found_files)
        logger.info(f"Found {len(found_files)} files with pattern {pattern}: {[f.name for f in found_files]}")
    
    logger.info(f"Total result files found: {len(result_files)}")
    
    # Возвращаем результирующие файлы, отдавая приоритет файлам с результатами
    if result_files:
        # Приоритет файлам с "results" или "analysis" в названии
        results_files = [f for f in result_files if any(keyword in f.name.lower() for keyword in ['results', 'analysis'])]
        
        if results_files:
            # Из файлов результатов берем самый свежий
            latest_file = max(results_files, key=lambda f: f.stat().st_mtime)
            logger.info(f"Selected results file: {latest_file.name} from {len(results_files)} result files")
        else:
            # Если нет файлов с результатами, берем самый свежий из всех
            latest_file = max(result_files, key=lambda f: f.stat().st_mtime)
            logger.info(f"No dedicated results files found, selected: {latest_file.name}")
        
        try:
            if latest_file.suffix == '.csv':
                # Читаем CSV как DataFrame и конвертируем в JSON
                df = pd.read_csv(latest_file)
                # Агрессивная очистка данных для корректной JSON сериализации
                import numpy as np
                df = df.replace([float('inf'), float('-inf'), np.inf, -np.inf], None)
                df = df.where(pd.notnull(df), None)
                
                # Парсим JSON в колонке All_Results
                if 'All_Results' in df.columns:
                    import json
                    def parse_json_column(value):
                        if pd.isna(value) or value is None:
                            return None
                        try:
                            if isinstance(value, str):
                                return json.loads(value)
                            return value
                        except (json.JSONDecodeError, TypeError):
                            return value
                    
                    df['All_Results'] = df['All_Results'].apply(parse_json_column)
                
                # Конвертируем в records и дополнительно очищаем
                records = df.to_dict('records')
                
                # Дополнительная очистка каждой записи
                def clean_data_recursive(obj):
                    """Рекурсивно очищает данные от некорректных float значений"""
                    if isinstance(obj, dict):
                        return {k: clean_data_recursive(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [clean_data_recursive(item) for item in obj]
                    elif isinstance(obj, float):
                        if np.isnan(obj) or np.isinf(obj):
                            return None
                        return obj
                    elif pd.isna(obj):
                        return None
                    else:
                        return obj
                
                cleaned_records = []
                for record in records:
                    cleaned_record = clean_data_recursive(record)
                    cleaned_records.append(cleaned_record)
                
                results = cleaned_records
            else:
                # Читаем JSON файл
                import json
                with open(latest_file, 'r', encoding='utf-8') as f:
                    results = json.load(f)
            
            logger.info(f"Results loaded successfully: {len(results) if isinstance(results, list) else 1} records from {latest_file.name}")
            logger.info(f"Sample data (first record): {results[0] if isinstance(results, list) and len(results) > 0 else 'No records'}")
            
            return {
                "session_id": session_id,
                "status": "completed",
                "results_count": len(results) if isinstance(results, list) else 1,
                "results": results,
                "result_file": str(latest_file)
            }
            
        except Exception as e:
            logger.error(f"Error reading results file {latest_file}: {e}")
            logger.error(f"File details: {latest_file.stat()}")
            raise HTTPException(status_code=500, detail=f"Failed to read results: {str(e)}")
    
    else:
        logger.error(f"No result files found in {session_results_dir}")
        logger.error(f"Directory contents: {list(session_results_dir.iterdir()) if session_results_dir.exists() else 'Directory does not exist'}")
        return {
            "session_id": session_id, 
            "status": "completed",
            "results_count": 0,
            "results": [],
            "message": "No result files found"
        }

@router.get("/sessions/{session_id}/download")
async def download_criteria_results(session_id: str):
    """Скачивает CSV файл с результатами анализа для указанной сессии."""
    if session_id not in criteria_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session_info = criteria_sessions[session_id]
    if session_info["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analysis is not completed yet")
        
    # Путь к файлу с результатами внутри папки output микросервиса
    # Мы используем session_id, чтобы найти правильный файл
    output_dir = CRITERIA_PROCESSOR_PATH / "output" / session_id
    result_files = list(output_dir.glob("*.csv"))
    
    if not result_files:
        raise HTTPException(status_code=404, detail="Result file not found in session directory")
        
    # Берем первый найденный CSV файл
    result_file_path = result_files[0]
    
    return FileResponse(
        path=result_file_path,
        filename=f"criteria_analysis_{session_id}.csv",
        media_type="text/csv"
    )

@router.get("/sessions/{session_id}/scrapingbee_logs")
async def download_scrapingbee_logs(session_id: str):
    """Скачивает единый, читаемый файл .log с результатами ScrapingBee."""
    if session_id not in criteria_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session_info = criteria_sessions[session_id]
    if session_info["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analysis is not completed yet")

    log_file_path = CRITERIA_PROCESSOR_PATH / "output" / session_id / "scrapingbee_logs" / "scrapingbee_session.log"

    if not log_file_path.is_file():
        raise HTTPException(status_code=404, detail="No ScrapingBee logs found for this session.")

    return FileResponse(
        path=log_file_path,
        filename=f"scrapingbee_logs_{session_id}.log",
        media_type="text/plain"
    )

@router.post("/sessions/{session_id}/cancel")
async def cancel_criteria_analysis(session_id: str):
    """Отменяет текущую задачу анализа критериев."""
    if session_id not in criteria_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Отменяем задачу если она активна
    if session_id in criteria_tasks:
        criteria_tasks[session_id].cancel()
        del criteria_tasks[session_id]
    
    # Обновляем статус
    criteria_sessions[session_id].update({
        "status": "cancelled",
        "end_time": datetime.now().isoformat()
    })
    
    return {
        "session_id": session_id,
        "status": "cancelled",
        "message": "Analysis cancelled successfully"
    }

@router.get("/files")
async def get_criteria_files():
    """Получить список всех файлов критериев с информацией о продуктах"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    
    if not criteria_dir.exists():
        return {"files": [], "products": []}
    
    files = []
    all_products = set()
    
    # Поддерживаем как CSV, так и XLSX файлы
    for pattern in ["*.csv", "*.xlsx"]:
        for file_path in criteria_dir.glob(pattern):
            # Исключаем backup файлы из отображения (на случай если они остались от старых версий)
            if ".backup_" in file_path.name or ".deleted_" in file_path.name:
                continue
            try:
                # Читаем файл в зависимости от расширения
                if file_path.suffix.lower() == '.csv':
                    df = pd.read_csv(file_path)
                elif file_path.suffix.lower() == '.xlsx':
                    df = pd.read_excel(file_path)
                else:
                    continue  # Пропускаем неподдерживаемые файлы
                
                # ФИЛЬТРАЦИЯ ПУСТЫХ СТРОК для правильного подсчета
                # Основные колонки для критериев
                main_columns = ['Product', 'Criteria', 'Target Audience']
                existing_columns = [col for col in main_columns if col in df.columns]
                
                if existing_columns:
                    # Удаляем строки где ВСЕ основные колонки пустые
                    df_filtered = df.dropna(subset=existing_columns, how='all')
                    df_filtered = df_filtered[df_filtered[existing_columns].ne('').any(axis=1)]
                    actual_rows = len(df_filtered)
                else:
                    # Если нет основных колонок, считаем все непустые строки
                    actual_rows = len(df.dropna(how='all'))
                
                # Извлекаем продукты из файла
                file_products = []
                if 'Product' in df.columns:
                    file_products = df['Product'].unique().tolist()
                    # Убираем NaN значения
                    file_products = [p for p in file_products if pd.notna(p) and str(p).strip()]
                    all_products.update(file_products)
                
                files.append({
                    "filename": file_path.name,
                    "full_path": str(file_path),
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                    "rows_preview": min(5, actual_rows),  # Показываем до 5 строк для preview
                    "total_rows": actual_rows,  # РЕАЛЬНОЕ количество строк с данными
                    "columns": list(df.columns) if not df.empty else [],
                    "products": file_products  # Продукты в этом файле
                })
            except Exception as e:
                logger.error(f"Error reading criteria file {file_path}: {e}")
                files.append({
                    "filename": file_path.name,
                    "full_path": str(file_path),
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                    "error": str(e),
                    "products": []
                })
    
    return {
        "files": files,
        "products": sorted(list(all_products))  # Все уникальные продукты
    }

@router.get("/files/{filename}")
async def get_criteria_file_content(filename: str):
    """Получить содержимое файла критериев"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    file_path = criteria_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Criteria file not found")
    
    if not file_path.suffix.lower() == '.csv':
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    try:
        df = pd.read_csv(file_path)
        
        # Заменяем NaN и Infinity значения на None/null для корректной JSON сериализации
        df = df.replace([float('inf'), float('-inf')], None)
        df = df.where(pd.notnull(df), None)
        
        return {
            "filename": filename,
            "columns": list(df.columns),
            "data": df.to_dict('records'),
            "total_rows": len(df),
            "file_info": {
                "size": file_path.stat().st_size,
                "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error reading criteria file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

@router.put("/files/{filename}")
async def update_criteria_file(filename: str, file_data: dict):
    """Обновить содержимое файла критериев"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    file_path = criteria_dir / filename
    
    if not filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    try:
        # Валидируем структуру данных
        if "data" not in file_data or "columns" not in file_data:
            raise HTTPException(status_code=400, detail="Invalid data format. Expected 'data' and 'columns' fields")
        
        # Создаем DataFrame из переданных данных
        df = pd.DataFrame(file_data["data"], columns=file_data["columns"])
        
        # НЕ создаем backup файлы - пользователи их все равно не смогут достать
        
        # Сохраняем новый файл
        df.to_csv(file_path, index=False)
        
        logger.info(f"Updated criteria file: {filename}")
        
        return {
            "message": "File updated successfully",
            "filename": filename,
            "rows_saved": len(df),
            "timestamp": datetime.now().isoformat()
        }
        
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="Empty data provided")
    except Exception as e:
        logger.error(f"Error updating criteria file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating file: {str(e)}")

@router.post("/files")
async def create_criteria_file(file_data: dict):
    """Создать новый файл критериев"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    
    if "filename" not in file_data:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    filename = file_data["filename"]
    if not filename.endswith('.csv'):
        filename += '.csv'
    
    file_path = criteria_dir / filename
    
    if file_path.exists():
        raise HTTPException(status_code=400, detail="File already exists")
    
    try:
        # Создаем DataFrame с данными или пустой шаблон
        if "data" in file_data and "columns" in file_data:
            df = pd.DataFrame(file_data["data"], columns=file_data["columns"])
        else:
            # Создаем стандартный шаблон для критериев
            df = pd.DataFrame(columns=[
                "Product", "Target Audience", "Criteria Type", "Criteria", 
                "Place", "Search Query", "Signals"
            ])
            # Добавляем примерную строку
            df.loc[0] = [
                "New Product", "Target Audience", "Qualification", 
                "Sample criteria", "description", "sample query", "sample signals"
            ]
        
        df.to_csv(file_path, index=False)
        
        logger.info(f"Created new criteria file: {filename}")
        
        return {
            "message": "File created successfully",
            "filename": filename,
            "rows_created": len(df),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error creating criteria file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating file: {str(e)}")

@router.post("/upload")
async def upload_criteria_file(file: UploadFile = File(...)):
    """Загрузить файл критериев через multipart/form-data"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    
    # Проверяем формат файла
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(
            status_code=400, 
            detail="Unsupported file format. Use CSV or Excel files."
        )
    
    file_path = criteria_dir / file.filename
    
    if file_path.exists():
        raise HTTPException(status_code=400, detail="File already exists")
    
    try:
        # Сохраняем загруженный файл
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        logger.info(f"Uploaded criteria file: {file.filename}")
        
        return {
            "message": "File uploaded successfully",
            "filename": file.filename,
            "size": len(content),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error uploading criteria file {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")

@router.delete("/files/{filename}")
async def delete_criteria_file(filename: str):
    """Удалить файл критериев"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    file_path = criteria_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Criteria file not found")
    
    try:
        # Удаляем файл БЕЗ создания backup
        file_path.unlink()
        
        logger.info(f"Deleted criteria file: {filename}")
        
        return {
            "message": "File deleted successfully",
            "filename": filename,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error deleting criteria file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")

# Эндпоинт cleanup-backups удален - backup файлы больше не создаются

@router.get("/health")
async def criteria_service_health():
    """Health check для сервиса анализа критериев"""
    try:
        # Проверяем что папка criteria_processor существует
        if not CRITERIA_PROCESSOR_PATH.exists():
            raise Exception("Criteria processor path not found")
        
        return {
            "service": "criteria_analysis",
            "status": "healthy",
            "active_sessions": len([s for s in criteria_sessions.values() if s["status"] == "processing"]),
            "total_sessions": len(criteria_sessions),
            "criteria_processor_path": str(CRITERIA_PROCESSOR_PATH)
        }
    except Exception as e:
        return {
            "service": "criteria_analysis", 
            "status": "unhealthy",
            "error": str(e)
        }

@router.get("/sessions/{session_id}/progress")
async def get_criteria_session_progress(session_id: str):
    """Получить детальный прогресс анализа критериев с счетчиками"""
    if session_id not in criteria_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Проверяем, есть ли файл прогресса в output папке criteria_processor
        progress_file = CRITERIA_PROCESSOR_PATH / "output" / session_id / f"{session_id}_progress.json"
        
        if not progress_file.exists():
            # Если файла нет, проверим есть ли результаты - возможно процесс завершился без progress файла
            session_data = criteria_sessions[session_id]
            
            # Проверяем есть ли результирующий CSV файл
            output_dir = CRITERIA_PROCESSOR_PATH / "output" / session_id
            result_files = []
            if output_dir.exists():
                result_files = list(output_dir.glob("*.csv"))
            
            # Если есть результаты но нет progress файла - процесс завершился некорректно
            if result_files and session_data["status"] == "processing":
                # Обновляем статус в памяти
                criteria_sessions[session_id]["status"] = "completed"
                criteria_sessions[session_id]["end_time"] = datetime.now().isoformat()
                
                return {
                    "session_id": session_id,
                    "status": "completed",
                    "progress": {
                        "criteria": "N/A",
                        "companies": "N/A", 
                        "processed": len(result_files),
                        "failed": 0
                    },
                    "current": {
                        "product": None,
                        "company": None,
                        "audience": None,
                        "stage": "completed"
                    },
                    "percentage": 100,
                    "message": f"Analysis completed! Found {len(result_files)} result files.",
                    "detailed_progress": False,
                    "note": "Process completed without progress tracking (legacy mode)"
                }
            
            # Проверим не зависла ли задача слишком долго
            start_time_str = session_data.get("start_time")
            if start_time_str and session_data["status"] == "processing":
                try:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    time_elapsed = datetime.now() - start_time.replace(tzinfo=None)
                    
                    # Если прошло больше 30 минут без progress файла - считаем что процесс завис
                    if time_elapsed.total_seconds() > 1800:  # 30 минут
                        criteria_sessions[session_id]["status"] = "failed"
                        criteria_sessions[session_id]["error"] = "Process timeout - no progress detected"
                        criteria_sessions[session_id]["end_time"] = datetime.now().isoformat()
                        
                        return {
                            "session_id": session_id,
                            "status": "failed",
                            "progress": {
                                "criteria": "0/0",
                                "companies": "0/0",
                                "processed": 0,
                                "failed": 0
                            },
                            "current": {
                                "product": None,
                                "company": None,
                                "audience": None,
                                "stage": "timeout"
                            },
                            "percentage": 0,
                            "message": "Analysis timed out - process may have crashed during initialization",
                            "detailed_progress": False,
                            "error": "Process timeout after 30 minutes"
                        }
                except Exception:
                    pass
            
            # Стандартная обработка для инициализации
            return {
                "session_id": session_id,
                "status": session_data["status"],
                "progress": {
                    "criteria": "0/0",
                    "companies": "0/0",
                    "processed": 0,
                    "failed": 0
                },
                "current": {
                    "product": None,
                    "company": None,
                    "audience": None,
                    "stage": "initialization"
                },
                "percentage": 0,
                "message": "Initializing...",
                "detailed_progress": False
            }
        
        # Читаем детальный прогресс из файла ProcessingStateManager
        import json
        with open(progress_file, 'r', encoding='utf-8') as f:
            progress_data = json.load(f)
        
        # Рассчитываем процент выполнения
        total_companies = progress_data.get("total_companies", 0)
        processed_companies = progress_data.get("processed_companies", 0)
        total_criteria = progress_data.get("total_criteria", 0)
        processed_criteria = progress_data.get("processed_criteria", 0)
        
        # Приоритет для критериев, если они доступны
        if total_criteria > 0:
            percentage = min(100, int((processed_criteria / total_criteria) * 100))
        elif total_companies > 0:
            percentage = min(100, int((processed_companies / total_companies) * 100))
        else:
            percentage = 0
        
        # Создаем описательное сообщение
        current_stage = progress_data.get("current_stage", "unknown")
        current_product = progress_data.get("current_product")
        current_company = progress_data.get("current_company")
        
        if current_stage == "general_criteria":
            message = "Checking general criteria..."
        elif current_stage == "product_start":
            message = f"Starting analysis for {current_product}"
        elif current_stage == "processing":
            if current_company:
                message = f"Analyzing {current_company} for {current_product or 'products'}"
            else:
                message = "Processing companies..."
        elif current_stage == "product_completed":
            message = f"Completed {current_product}"
        else:
            message = f"Stage: {current_stage}"
        
        # Создаем информацию о критериях
        criteria_breakdown = progress_data.get("criteria_breakdown", {})
        criteria_summary = ""
        if criteria_breakdown:
            for crit_type, stats in criteria_breakdown.items():
                if stats.get("total", 0) > 0:
                    criteria_summary += f"{crit_type.title()}: {stats.get('processed', 0)}/{stats.get('total', 0)} "
        
        return {
            "session_id": session_id,
            "status": progress_data.get("status", "unknown"),
            "progress": {
                "criteria": f"{processed_criteria}/{total_criteria}" if total_criteria > 0 else "0/0",
                "companies": f"{processed_companies}/{total_companies}",
                "processed": processed_companies,
                "failed": progress_data.get("failed_companies", 0)
            },
            "current": {
                "product": current_product,
                "company": current_company,
                "audience": progress_data.get("current_audience"),
                "stage": current_stage
            },
            "percentage": percentage,
            "message": message,
            "criteria_breakdown": criteria_breakdown,
            "criteria_summary": criteria_summary.strip(),
            "detailed_progress": True,
            "last_updated": progress_data.get("updated_at"),
            "circuit_breaker_events": len(progress_data.get("circuit_breaker_events", []))
        }
        
    except Exception as e:
        logger.error(f"Error reading progress for session {session_id}: {e}")
        # Fallback к базовой информации
        session_data = criteria_sessions[session_id]
        return {
            "session_id": session_id,
            "status": session_data["status"],
            "progress": {
                "criteria": "0/0",
                "companies": "0/0",
                "processed": 0,
                "failed": 0
            },
            "current": {
                "product": None,
                "company": None,
                "audience": None,
                "stage": "error"
            },
            "percentage": 0,
            "message": f"Error reading progress: {str(e)}",
            "detailed_progress": False,
            "error": str(e)
        } 