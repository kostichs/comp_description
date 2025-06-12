"""
Recovery модуль для возобновления прерванных сессий анализа критериев
"""

import json
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from src.utils.logging import log_info, log_error, log_debug
from src.utils.state_manager import ProcessingStateManager
from src.core.parallel_processor import run_parallel_analysis
from src.data.search_data_saver import initialize_search_data_saver, finalize_search_data_saving


def resume_processing(session_id: str, 
                     companies_file: str = None,
                     load_all_companies: bool = False,
                     use_deep_analysis: bool = False,
                     max_concurrent_companies: int = 12) -> Tuple[bool, str, Optional[List[Dict[str, Any]]]]:
    """
    Возобновить прерванную сессию анализа критериев
    
    Args:
        session_id: ID сессии для возобновления
        companies_file: Файл компаний (если нужен для новой обработки)
        load_all_companies: Загружать все файлы
        use_deep_analysis: Использовать глубокий анализ
        max_concurrent_companies: Количество параллельных компаний
        
    Returns:
        (success, message, results) - результат возобновления
    """
    try:
        log_info(f"🔄 Попытка возобновления сессии: {session_id}")
        
        # Initialize state manager for the session
        state_manager = ProcessingStateManager(session_id)
        
        # Check if session can be resumed
        can_resume, reason = state_manager.can_resume()
        if not can_resume:
            return False, f"Cannot resume session: {reason}", None
        
        # Load saved progress
        progress = state_manager.load_progress()
        if not progress:
            return False, "No progress data found", None
        
        # Load existing results
        existing_results = state_manager.load_partial_results()
        log_info(f"📂 Найдено {len(existing_results)} существующих результатов")
        
        # Get session state summary
        state_summary = state_manager.get_state_summary()
        log_info(f"📊 Состояние сессии:")
        log_info(f"   Статус: {state_summary.get('status', 'unknown')}")
        log_info(f"   Прогресс: {state_summary.get('progress', {})}")
        log_info(f"   Текущий: {state_summary.get('current', {})}")
        
        # Validate partial results
        valid_results, validation_report = validate_partial_results(existing_results)
        if validation_report['errors']:
            log_error(f"⚠️ Проблемы в существующих результатах:")
            for error in validation_report['errors']:
                log_error(f"   - {error}")
        
        log_info(f"✅ Валидация результатов: {validation_report['valid_count']}/{validation_report['total_count']} валидных")
        
        # Mark session as resuming
        state_manager.save_progress(
            progress.get('current_product_index', 0),
            progress.get('current_company_index', 0),
            progress.get('current_product'),
            progress.get('current_company'),
            progress.get('current_audience'),
            "resuming"
        )
        
        # Record resume event
        state_manager.record_circuit_breaker_event("session_resumed", {
            "previous_status": progress.get('status'),
            "existing_results_count": len(valid_results),
            "resume_reason": reason
        })
        
        log_info(f"🚀 Возобновляем обработку с сохраненного места...")
        
        # Initialize search data saver for resumed session
        initialize_search_data_saver(session_id)
        log_info(f"🔧 Initialized search data saver for resumed session: {session_id}")
        
        # Resume actual processing
        # Note: The run_parallel_analysis function will automatically load 
        # existing results through state_manager.load_partial_results()
        new_results = run_parallel_analysis(
            companies_file=companies_file,
            load_all_companies=load_all_companies,
            session_id=session_id,
            use_deep_analysis=use_deep_analysis,
            max_concurrent_companies=max_concurrent_companies
        )
        
        log_info(f"🎉 Возобновление завершено!")
        log_info(f"📊 Итого результатов: {len(new_results)} (включая ранее обработанные)")
        
        return True, "Session resumed successfully", new_results
        
    except Exception as e:
        log_error(f"❌ Ошибка возобновления сессии {session_id}: {e}")
        return False, f"Resume failed: {str(e)}", None


def validate_partial_results(results: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Валидация частичных результатов
    
    Args:
        results: Список результатов для валидации
        
    Returns:
        (valid_results, validation_report) - валидные результаты и отчет
    """
    valid_results = []
    errors = []
    warnings = []
    
    required_fields = ['Company_Name', 'Product']
    
    for i, result in enumerate(results):
        try:
            # Check required fields
            missing_fields = [field for field in required_fields if field not in result or not result[field]]
            if missing_fields:
                errors.append(f"Result {i}: Missing required fields: {missing_fields}")
                continue
            
            # Check if All_Results is valid JSON structure
            if 'All_Results' in result:
                all_results = result['All_Results']
                if isinstance(all_results, str):
                    try:
                        json.loads(all_results)
                    except json.JSONDecodeError:
                        warnings.append(f"Result {i}: Invalid JSON in All_Results for {result.get('Company_Name', 'Unknown')}")
                elif not isinstance(all_results, dict):
                    warnings.append(f"Result {i}: All_Results is not dict or JSON string for {result.get('Company_Name', 'Unknown')}")
            
            # Check qualification status
            qualified_products = result.get('Qualified_Products', '')
            if not qualified_products:
                warnings.append(f"Result {i}: Empty Qualified_Products for {result.get('Company_Name', 'Unknown')}")
            
            valid_results.append(result)
            
        except Exception as e:
            errors.append(f"Result {i}: Validation error: {str(e)}")
    
    validation_report = {
        'total_count': len(results),
        'valid_count': len(valid_results),
        'error_count': len(errors),
        'warning_count': len(warnings),
        'errors': errors,
        'warnings': warnings,
        'success_rate': len(valid_results) / len(results) if results else 0
    }
    
    return valid_results, validation_report


def get_resumable_sessions(base_output_dir: str = None) -> List[Dict[str, Any]]:
    """
    Получить список сессий которые можно возобновить
    
    Args:
        base_output_dir: Базовая папка output
        
    Returns:
        Список информации о возобновляемых сессиях
    """
    resumable_sessions = []
    
    try:
        if base_output_dir is None:
            from src.utils.config import OUTPUT_DIR
            base_output_dir = OUTPUT_DIR
        
        output_path = Path(base_output_dir)
        
        if not output_path.exists():
            return resumable_sessions
        
        # Ищем папки сессий
        for session_dir in output_path.iterdir():
            if not session_dir.is_dir():
                continue
                
            session_id = session_dir.name
            
            try:
                # Проверяем есть ли файлы состояния
                progress_file = session_dir / f"{session_id}_progress.json"
                
                if progress_file.exists():
                    state_manager = ProcessingStateManager(session_id, base_output_dir)
                    can_resume, reason = state_manager.can_resume()
                    
                    if can_resume:
                        state_summary = state_manager.get_state_summary()
                        resumable_sessions.append({
                            'session_id': session_id,
                            'status': state_summary.get('status', 'unknown'),
                            'progress': state_summary.get('progress', {}),
                            'current': state_summary.get('current', {}),
                            'results_count': state_summary.get('results_count', 0),
                            'last_updated': state_summary.get('last_updated'),
                            'can_resume': True,
                            'resume_reason': reason
                        })
                    else:
                        # Add info about non-resumable sessions too
                        resumable_sessions.append({
                            'session_id': session_id,
                            'can_resume': False,
                            'resume_reason': reason
                        })
                        
            except Exception as e:
                log_debug(f"Ошибка проверки сессии {session_id}: {e}")
                continue
    
    except Exception as e:
        log_error(f"Ошибка поиска возобновляемых сессий: {e}")
    
    return resumable_sessions


def cleanup_failed_sessions(base_output_dir: str = None, days_old: int = 7) -> Dict[str, Any]:
    """
    Очистка старых неуспешных сессий
    
    Args:
        base_output_dir: Базовая папка output
        days_old: Удалять сессии старше N дней
        
    Returns:
        Отчет об очистке
    """
    import time
    from datetime import datetime, timedelta
    
    cleanup_report = {
        'sessions_checked': 0,
        'sessions_deleted': 0,
        'freed_space': 0,
        'errors': []
    }
    
    try:
        if base_output_dir is None:
            from src.utils.config import OUTPUT_DIR
            base_output_dir = OUTPUT_DIR
        
        output_path = Path(base_output_dir)
        cutoff_time = datetime.now() - timedelta(days=days_old)
        
        for session_dir in output_path.iterdir():
            if not session_dir.is_dir():
                continue
                
            cleanup_report['sessions_checked'] += 1
            
            try:
                # Check session age
                modified_time = datetime.fromtimestamp(session_dir.stat().st_mtime)
                
                if modified_time < cutoff_time:
                    # Check if session is failed/cancelled
                    session_id = session_dir.name
                    state_manager = ProcessingStateManager(session_id, base_output_dir)
                    progress = state_manager.load_progress()
                    
                    if progress and progress.get('status') in ['failed', 'cancelled']:
                        # Calculate size before deletion
                        size_before = sum(f.stat().st_size for f in session_dir.rglob('*') if f.is_file())
                        
                        # Delete session directory
                        import shutil
                        shutil.rmtree(session_dir)
                        
                        cleanup_report['sessions_deleted'] += 1
                        cleanup_report['freed_space'] += size_before
                        
                        log_info(f"🗑️ Удалена старая сессия: {session_id}")
                        
            except Exception as e:
                cleanup_report['errors'].append(f"Error cleaning session {session_dir.name}: {str(e)}")
    
    except Exception as e:
        cleanup_report['errors'].append(f"Error during cleanup: {str(e)}")
    
    return cleanup_report 