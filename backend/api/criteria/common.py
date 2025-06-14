"""
Общие компоненты для Criteria Analysis

Содержит импорты, утилиты и глобальные переменные, используемые во всех модулях
"""

import os
import sys
import json
import shutil
import logging
import asyncio
import aiofiles
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from starlette.background import BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR, SESSIONS_METADATA_FILE

# Настройка путей к criteria_processor
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CRITERIA_PROCESSOR_PATH = PROJECT_ROOT / "services" / "criteria_processor"
CRITERIA_SRC_PATH = CRITERIA_PROCESSOR_PATH / "src"

# Добавляем пути в sys.path если их нет
for path in [str(CRITERIA_PROCESSOR_PATH), str(CRITERIA_SRC_PATH)]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Логгер
logger = logging.getLogger(__name__)

# Хранилище активных сессий анализа критериев
# Формат: {"session_id": {"status": "processing|completed|failed", "result_path": "...", ...}}
criteria_sessions: Dict[str, Dict[str, Any]] = {}

# Хранилище активных задач
criteria_tasks: Dict[str, asyncio.Task] = {}

def load_existing_criteria_sessions():
    """Загружает существующие сессии из файловой системы"""
    global criteria_sessions
    
    output_dir = CRITERIA_PROCESSOR_PATH / "output"
    if not output_dir.exists():
        return
    
    for session_dir in output_dir.iterdir():
        if session_dir.is_dir() and session_dir.name.startswith("crit_"):
            session_id = session_dir.name
            
            # Пропускаем если сессия уже загружена
            if session_id in criteria_sessions:
                continue
                
            # Определяем статус сессии по наличию файлов
            metadata_file = session_dir / f"{session_id}_metadata.json"
            progress_file = session_dir / f"{session_id}_progress.json"
            result_files = list(session_dir.glob("*.csv"))
            
            status = "unknown"
            if result_files:
                status = "completed"
            elif progress_file.exists():
                try:
                    with open(progress_file, 'r', encoding='utf-8') as f:
                        progress_data = json.load(f)
                        status = progress_data.get("status", "processing")
                except:
                    status = "processing"
            
            # Создаем запись сессии
            criteria_sessions[session_id] = {
                "session_id": session_id,
                "status": status,
                "created_time": session_dir.stat().st_ctime,
                "result_path": str(session_dir) if result_files else None
            }
            
            logger.info(f"Loaded existing session: {session_id} (status: {status})")

# Загружаем существующие сессии при импорте модуля
load_existing_criteria_sessions()

def generate_criteria_session_id() -> str:
    """Генерирует уникальный ID сессии с префиксом crit_"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"crit_{timestamp}"

def run_criteria_processor(
    input_file_path: str, 
    load_all_companies: bool = False, 
    session_id: str = None, 
    use_deep_analysis: bool = False, 
    use_parallel: bool = True, 
    max_concurrent: int = 12, 
    selected_products: List[str] = None, 
    selected_criteria_files: List[str] = None, 
    write_to_hubspot_criteria: bool = False
):
    """Запускаем criteria_processor как отдельный процесс"""
    import subprocess
    
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
                            df = pd.read_csv(file_path)
                            if 'Product' in df.columns:
                                file_products = df['Product'].unique().tolist()
                                file_products = [str(p).strip() for p in file_products if pd.notna(p) and str(p).strip()]
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

def cleanup_old_sessions(max_sessions: int = 10) -> None:
    """Очистка старых сессий анализа критериев"""
    try:
        # Получаем все папки сессий критериев
        output_dir = CRITERIA_PROCESSOR_PATH / "output"
        if not output_dir.exists():
            return
        
        # Получаем все папки с префиксом crit_
        session_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("crit_")]
        
        # Сортируем по времени создания (новые первыми)
        session_dirs.sort(key=lambda x: x.stat().st_ctime, reverse=True)
        
        # Удаляем старые сессии
        for old_dir in session_dirs[max_sessions:]:
            try:
                shutil.rmtree(old_dir)
                logger.info(f"Removed old criteria session: {old_dir.name}")
            except Exception as e:
                logger.error(f"Error removing old criteria session {old_dir.name}: {e}")
                
    except Exception as e:
        logger.error(f"Error in cleanup_old_sessions: {e}")

def cleanup_temp_sessions(max_sessions: int = 10) -> None:
    """Очистка временных сессий из temp/criteria_analysis"""
    try:
        temp_dir = PROJECT_ROOT / "temp" / "criteria_analysis"
        if not temp_dir.exists():
            return
        
        # Получаем все папки с префиксом crit_
        session_dirs = [d for d in temp_dir.iterdir() if d.is_dir() and d.name.startswith("crit_")]
        
        # Сортируем по времени создания (новые первыми)
        session_dirs.sort(key=lambda x: x.stat().st_ctime, reverse=True)
        
        # Удаляем старые сессии
        for old_dir in session_dirs[max_sessions:]:
            try:
                shutil.rmtree(old_dir)
                logger.info(f"Removed old temp criteria session: {old_dir.name}")
            except Exception as e:
                logger.error(f"Error removing old temp criteria session {old_dir.name}: {e}")
                
    except Exception as e:
        logger.error(f"Error in cleanup_temp_sessions: {e}") 