import time
import logging
from fastapi import HTTPException
from fastapi import APIRouter
from src.data_io import load_session_metadata, save_session_metadata

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/sessions")
async def get_sessions():
    """Получение списка всех сессий"""
    try:
        logger.info("GET /api/sessions - Вызов функции get_sessions из роутера sessions.py")
        metadata = load_session_metadata()
        
        # Фильтруем только те сессии, папки которых существуют и имеют статус completed
        import os
        filtered_sessions = []
        for session in metadata:
            session_id = session.get("session_id")
            session_dir = f"output/sessions/{session_id}"
            
            # Проверяем существование папки сессии и статус completed
            if os.path.exists(session_dir) and session.get("status") == "completed":
                # Исправляем поле created_time если используется старое поле timestamp_created
                if "created_time" not in session and "timestamp_created" in session:
                    session["created_time"] = session["timestamp_created"]
                
                # Убеждаемся что есть поле total_companies
                if "total_companies" not in session:
                    session["total_companies"] = session.get("companies_count", 0)
                
                filtered_sessions.append(session)
        
        # Сортируем по времени создания, новые сверху
        filtered_sessions.sort(key=lambda x: x.get("created_time", ""), reverse=True)
        
        logger.info(f"Filtered {len(filtered_sessions)} valid sessions out of {len(metadata)} total")
        return filtered_sessions
    except Exception as e:
        logger.error(f"Error getting sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Получение информации о сессии по ID"""
    try:
        logger.info(f"GET /api/sessions/{session_id} - Вызов функции get_session из роутера sessions.py")
        metadata = load_session_metadata()
        session_data = next((m for m in metadata if m.get("session_id") == session_id), None)
        
        if not session_data:
            logger.error(f"Session {session_id} not found")
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        # Формирование и добавление сообщения о дедупликации (если нужно и его еще нет)
        dedup_info = session_data.get("deduplication_info")
        if dedup_info and isinstance(dedup_info.get("final_count"), int) and dedup_info.get("duplicates_removed", 0) > 0:
            original = dedup_info.get("original_count", 0)
            removed = dedup_info.get("duplicates_removed", 0)
            final = dedup_info.get("final_count", 0)
            
            dedup_message_text = f"Removed {removed} duplicates"
            
            processing_messages = session_data.get("processing_messages", [])
            has_dedup_message = any(msg.get("type") == "deduplication" and msg.get("message") == dedup_message_text for msg in processing_messages)
            
            if not has_dedup_message:
                new_message = {
                    "type": "deduplication",
                    "message": dedup_message_text,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                session_data["processing_messages"] = processing_messages + [new_message]
                
                # Сохраняем метаданные, так как добавили новое сообщение
                current_all_metadata = load_session_metadata() 
                updated_all_metadata = []
                for meta_item in current_all_metadata:
                    if meta_item.get("session_id") == session_id:
                        updated_all_metadata.append(session_data) 
                    else:
                        updated_all_metadata.append(meta_item)
                save_session_metadata(updated_all_metadata)
                logger.info(f"Session {session_id}: Сохранены метаданные с новым сообщением о дедупликации.")
        
        return session_data
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions/{session_id}/results_file")
async def get_session_results_file(session_id: str):
    """Получение пути к результирующему файлу сессии для использования в criteria analysis"""
    try:
        logger.info(f"GET /api/sessions/{session_id}/results_file - Получение пути к результирующему файлу")
        metadata = load_session_metadata()
        session_data = next((m for m in metadata if m.get("session_id") == session_id), None)
        
        if not session_data:
            logger.error(f"Session {session_id} not found")
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        if session_data.get("status") != "completed":
            raise HTTPException(status_code=400, detail=f"Session {session_id} is not completed yet")
        
        # Путь к результирующему файлу
        results_file_path = f"output/sessions/{session_id}/final_results.csv"
        
        return {
            "session_id": session_id,
            "file_path": results_file_path,
            "status": session_data.get("status"),
            "total_companies": session_data.get("total_companies", 0),
            "created_time": session_data.get("created_time", "")
        }
    except Exception as e:
        logger.error(f"Error getting results file for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) 