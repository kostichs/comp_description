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

def run_criteria_processor(input_file_path: str, load_all_companies: bool = False):
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
        else:
            # Копируем файл в data папку criteria_processor
            source_path = Path(input_file_path)
            target_path = CRITERIA_PROCESSOR_PATH / "data" / source_path.name
            
            # Создаем data папку если не существует
            target_path.parent.mkdir(exist_ok=True)
            
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
                "--file", f"data/{target_path.name}"  # Путь относительно criteria_processor
            ]
        
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

def cleanup_old_backups(original_file_path: Path, max_backups: int = 5):
    """Очищает старые бэкап файлы, оставляя только последние max_backups штук"""
    try:
        criteria_dir = original_file_path.parent
        base_name = original_file_path.stem  # Имя без расширения
        
        # Находим все бэкап файлы для данного файла
        backup_files = []
        for backup_file in criteria_dir.glob(f"{base_name}.backup_*.csv"):
            backup_files.append(backup_file)
        
        # Сортируем по времени модификации (новые в конце)
        backup_files.sort(key=lambda x: x.stat().st_mtime)
        
        # Удаляем старые, оставляем только последние max_backups
        if len(backup_files) > max_backups:
            files_to_delete = backup_files[:-max_backups]
            for old_backup in files_to_delete:
                old_backup.unlink()
                logger.info(f"Deleted old backup: {old_backup}")
                
    except Exception as e:
        logger.error(f"Error cleaning up backups for {original_file_path}: {e}")

async def run_criteria_analysis_task(
    session_id: str,
    input_file_path: Path,
    load_all_companies: bool = False
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
            load_all_companies
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
    load_all_companies: bool = Form(False)
):
    """
    Создает новую сессию анализа критериев
    
    - **file**: CSV файл с описаниями компаний 
    - **load_all_companies**: Загружать ли все файлы из папки data
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
        
        # Сохраняем загруженный файл
        input_file_path = session_dir / file.filename
        async with aiofiles.open(input_file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Создаем метаданные сессии
        criteria_sessions[session_id] = {
            "session_id": session_id,
            "status": "created",
            "created_time": datetime.now().isoformat(),
            "filename": file.filename,
            "file_size": len(content),
            "input_file_path": str(input_file_path),
            "load_all_companies": load_all_companies
        }
        
        # Запускаем анализ в фоновой задаче
        task = asyncio.create_task(
            run_criteria_analysis_task(
                session_id, 
                input_file_path, 
                load_all_companies
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
    
    # Ищем файлы результатов в output папке criteria_processor
    results_dir = CRITERIA_PROCESSOR_PATH / "output"
    result_files = []
    
    # Поиск CSV и JSON файлов с результатами
    for pattern in ["*.csv", "*.json"]:
        result_files.extend(results_dir.glob(f"**/{pattern}"))
    
    # Возвращаем последние созданные файлы (предполагаем что это наши результаты)
    if result_files:
        # Берем самый свежий файл
        latest_file = max(result_files, key=os.path.getctime)
        
        try:
            if latest_file.suffix == '.csv':
                # Читаем CSV как DataFrame и конвертируем в JSON
                df = pd.read_csv(latest_file)
                # Агрессивная очистка данных для корректной JSON сериализации
                import numpy as np
                df = df.replace([float('inf'), float('-inf'), np.inf, -np.inf], None)
                df = df.where(pd.notnull(df), None)
                
                # Конвертируем в records и дополнительно очищаем
                records = df.to_dict('records')
                
                # Дополнительная очистка каждой записи
                cleaned_records = []
                for record in records:
                    cleaned_record = {}
                    for key, value in record.items():
                        if pd.isna(value) or value is None:
                            cleaned_record[key] = None
                        elif isinstance(value, float) and (np.isinf(value) or np.isnan(value)):
                            cleaned_record[key] = None
                        else:
                            cleaned_record[key] = value
                    cleaned_records.append(cleaned_record)
                
                results = cleaned_records
            else:
                # Читаем JSON файл
                import json
                with open(latest_file, 'r', encoding='utf-8') as f:
                    results = json.load(f)
            
            return {
                "session_id": session_id,
                "status": "completed",
                "results_count": len(results) if isinstance(results, list) else 1,
                "results": results,
                "result_file": str(latest_file)
            }
            
        except Exception as e:
            logger.error(f"Error reading results file {latest_file}: {e}")
            raise HTTPException(status_code=500, detail="Failed to read results")
    
    else:
        return {
            "session_id": session_id, 
            "status": "completed",
            "results_count": 0,
            "results": [],
            "message": "No result files found"
        }

@router.get("/sessions/{session_id}/download")
async def download_criteria_results(session_id: str):
    """Скачать файл результатов анализа критериев"""
    if session_id not in criteria_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_data = criteria_sessions[session_id]
    
    if session_data["status"] != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"Analysis not completed. Current status: {session_data['status']}"
        )
    
    # Ищем файлы результатов в папке criteria_processor/output
    results_dir = CRITERIA_PROCESSOR_PATH / "output"
    result_files = list(results_dir.glob("**/*.csv"))
    
    if result_files:
        # Берем самый свежий CSV файл
        latest_file = max(result_files, key=os.path.getctime)
        
        return FileResponse(
            latest_file,
            filename=f"criteria_analysis_results_{session_id}.csv",
            media_type="text/csv"
        )
    else:
        raise HTTPException(status_code=404, detail="No result files found")

@router.post("/sessions/{session_id}/cancel")
async def cancel_criteria_analysis(session_id: str):
    """Отменить выполнение анализа критериев"""
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
    """Получить список всех файлов критериев"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    
    if not criteria_dir.exists():
        return {"files": []}
    
    files = []
    for file_path in criteria_dir.glob("*.csv"):
        # Исключаем backup файлы из отображения
        if ".backup_" in file_path.name or ".deleted_" in file_path.name:
            continue
        try:
            # Читаем первые несколько строк для получения метаданных
            df = pd.read_csv(file_path, nrows=5)
            
            # Безопасно подсчитываем строки в полном файле
            try:
                full_df = pd.read_csv(file_path)
                total_rows = len(full_df)
            except:
                total_rows = len(df)
            
            files.append({
                "filename": file_path.name,
                "full_path": str(file_path),
                "size": file_path.stat().st_size,
                "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                "rows_preview": len(df),
                "total_rows": total_rows,
                "columns": list(df.columns) if not df.empty else []
            })
        except Exception as e:
            logger.error(f"Error reading criteria file {file_path}: {e}")
            files.append({
                "filename": file_path.name,
                "full_path": str(file_path),
                "size": file_path.stat().st_size,
                "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                "error": str(e)
            })
    
    return {"files": files}

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
        
        # Создаем бэкап если файл существует
        if file_path.exists():
            backup_path = file_path.with_suffix(f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
            shutil.copy2(file_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            
            # Очищаем старые бэкапы - оставляем только последние 5
            cleanup_old_backups(file_path)
        
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

@router.delete("/files/{filename}")
async def delete_criteria_file(filename: str):
    """Удалить файл критериев"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    file_path = criteria_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Criteria file not found")
    
    try:
        # Создаем бэкап перед удалением
        backup_path = file_path.with_suffix(f'.deleted_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        shutil.copy2(file_path, backup_path)
        
        # Удаляем файл
        file_path.unlink()
        
        logger.info(f"Deleted criteria file: {filename} (backup: {backup_path})")
        
        return {
            "message": "File deleted successfully",
            "filename": filename,
            "backup_location": str(backup_path),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error deleting criteria file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")

@router.post("/cleanup-backups")
async def cleanup_all_backups():
    """Очистить все старые бэкап файлы критериев"""
    try:
        criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
        
        if not criteria_dir.exists():
            return {"message": "Criteria directory not found", "cleaned": 0}
        
        cleaned_count = 0
        
        # Находим все основные CSV файлы (исключая бэкапы)
        for file_path in criteria_dir.glob("*.csv"):
            if ".backup_" not in file_path.name and ".deleted_" not in file_path.name:
                old_count = len(list(criteria_dir.glob(f"{file_path.stem}.backup_*.csv")))
                cleanup_old_backups(file_path, max_backups=3)  # Оставляем только 3 последних
                new_count = len(list(criteria_dir.glob(f"{file_path.stem}.backup_*.csv")))
                cleaned_count += (old_count - new_count)
        
        logger.info(f"Cleaned up {cleaned_count} old backup files")
        
        return {
            "message": "Backup cleanup completed",
            "cleaned_files": cleaned_count,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error during backup cleanup: {e}")
        raise HTTPException(status_code=500, detail=f"Error cleaning backups: {str(e)}")

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