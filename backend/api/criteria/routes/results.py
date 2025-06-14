"""
Criteria Analysis Routes - Results Management

Содержит endpoints для получения результатов анализа критериев:
- GET /sessions/{id}/results - получение результатов анализа
- GET /sessions/{id}/download - скачивание CSV файла с результатами
- GET /sessions/{id}/scrapingbee_logs - скачивание логов ScrapingBee
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..common import (
    logger, criteria_sessions,
    CRITERIA_PROCESSOR_PATH
)

router = APIRouter()

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
                df = df.replace([float('inf'), float('-inf'), np.inf, -np.inf], None)
                df = df.where(pd.notnull(df), None)
                
                # Парсим JSON в колонке All_Results
                if 'All_Results' in df.columns:
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