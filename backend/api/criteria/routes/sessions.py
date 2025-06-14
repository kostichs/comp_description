"""
Criteria Analysis Routes - Sessions Management

Содержит endpoints для управления сессиями анализа критериев:
- GET /sessions - список всех сессий
- GET /sessions/{id} - информация о сессии
- GET /sessions/{id}/status - статус сессии
- POST /sessions/{id}/cancel - отмена сессии
- GET /sessions/{id}/progress - прогресс выполнения
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

from ..common import (
    logger, criteria_sessions, criteria_tasks,
    CRITERIA_PROCESSOR_PATH
)

router = APIRouter()

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

@router.post("/sessions/{session_id}/cancel")
async def cancel_criteria_analysis(session_id: str):
    """Отменить анализ критериев"""
    if session_id not in criteria_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_data = criteria_sessions[session_id]
    
    if session_data["status"] not in ["created", "processing"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel session with status: {session_data['status']}"
        )
    
    # Отменяем задачу если она активна
    if session_id in criteria_tasks:
        task = criteria_tasks[session_id]
        if not task.done():
            task.cancel()
        del criteria_tasks[session_id]
    
    # Обновляем статус
    criteria_sessions[session_id]["status"] = "cancelled"
    
    logger.info(f"Cancelled criteria analysis session: {session_id}")
    
    return {
        "session_id": session_id,
        "status": "cancelled",
        "message": "Analysis cancelled successfully"
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
                from datetime import datetime
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
                    from datetime import datetime
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