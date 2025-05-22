import time
import logging
from fastapi import HTTPException
from fastapi import APIRouter
from src.data_io import load_session_metadata, save_session_metadata

logger = logging.getLogger(__name__)

router = APIRouter()

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
        
        # Просто логируем загруженные значения (они должны быть обновлены normalize_urls.py)
        logger.info(f"Session {session_id}: Загруженные данные - total_companies: {session_data.get('total_companies')}, companies_count: {session_data.get('companies_count')}, dedup_info: {session_data.get('deduplication_info')}")

        # Формирование и добавление сообщения о дедупликации (если нужно и его еще нет)
        dedup_info = session_data.get("deduplication_info")
        if dedup_info and isinstance(dedup_info.get("final_count"), int) and dedup_info.get("duplicates_removed", 0) > 0:
            original = dedup_info.get("original_count", 0)
            removed = dedup_info.get("duplicates_removed", 0)
            final = dedup_info.get("final_count", 0)
            
            dedup_message_text = f"Обнаружено и удалено {removed} дубликатов. Обрабатывается {final} уникальных компаний вместо {original}."
            
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