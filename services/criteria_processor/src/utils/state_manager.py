"""
State Manager для сохранения прогресса обработки критериев
Позволяет восстанавливать работу после сбоев или пауз
"""

import json
import os
import time
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from src.utils.logging import log_info, log_error, log_debug


class ProcessingStateManager:
    """
    Менеджер состояния обработки критериев
    
    Сохраняет:
    - Текущий прогресс (продукт, компания, аудитория)
    - Промежуточные результаты
    - Метаданные сессии
    - Статистику ошибок
    """
    
    def __init__(self, session_id: str, base_output_dir: str = None):
        """
        Args:
            session_id: Уникальный ID сессии
            base_output_dir: Базовая папка для output (по умолчанию из config)
        """
        self.session_id = session_id
        self._lock = threading.RLock()
        
        # Определяем папки
        if base_output_dir is None:
            from src.utils.config import OUTPUT_DIR
            base_output_dir = OUTPUT_DIR
            
        self.session_dir = Path(base_output_dir) / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # Файлы состояния
        self.progress_file = self.session_dir / f"{session_id}_progress.json"
        self.results_file = self.session_dir / f"{session_id}_partial_results.json"
        self.metadata_file = self.session_dir / f"{session_id}_metadata.json"
        
        # Состояние
        self._current_state = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "status": "created",
            "current_product_index": 0,
            "current_company_index": 0,
            "current_product": None,
            "current_company": None,
            "current_audience": None,
            "current_stage": "initialization",
            "total_products": 0,
            "total_companies": 0,
            "processed_companies": 0,
            "failed_companies": 0,
            "circuit_breaker_events": [],
            "last_circuit_breaker_event": None
        }
        
        self._partial_results = []
        
        # Загружаем существующее состояние если есть
        self._load_existing_state()
        
        log_info(f"💾 State Manager инициализирован для сессии: {session_id}")
        log_info(f"📁 Папка состояния: {self.session_dir}")
    
    def save_progress(self, 
                     product_index: int, 
                     company_index: int, 
                     product_name: str = None,
                     company_name: str = None,
                     audience: str = None, 
                     stage: str = "processing") -> bool:
        """
        Сохранить текущий прогресс
        
        Args:
            product_index: Индекс текущего продукта
            company_index: Индекс текущей компании  
            product_name: Название продукта
            company_name: Название компании
            audience: Текущая аудитория
            stage: Стадия обработки
            
        Returns:
            True если сохранение успешно
        """
        try:
            with self._lock:
                self._current_state.update({
                    "updated_at": datetime.now().isoformat(),
                    "current_product_index": product_index,
                    "current_company_index": company_index,
                    "current_product": product_name,
                    "current_company": company_name,
                    "current_audience": audience,
                    "current_stage": stage,
                    "status": "processing"
                })
                
                # Сохраняем в файл
                with open(self.progress_file, 'w', encoding='utf-8') as f:
                    json.dump(self._current_state, f, ensure_ascii=False, indent=2)
                
                log_debug(f"💾 Progress saved: P{product_index} C{company_index} {stage}")
                return True
                
        except Exception as e:
            log_error(f"❌ Ошибка сохранения прогресса: {e}")
            return False
    
    def load_progress(self) -> Optional[Dict[str, Any]]:
        """
        Загрузить сохраненный прогресс
        
        Returns:
            Словарь с состоянием или None если нет сохраненного состояния
        """
        try:
            if self.progress_file.exists():
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    progress = json.load(f)
                
                log_info(f"📂 Загружен прогресс: {progress.get('current_stage', 'unknown')}")
                log_info(f"   Продукт: {progress.get('current_product_index', 0)}/{progress.get('total_products', 0)}")
                log_info(f"   Компания: {progress.get('current_company_index', 0)}/{progress.get('total_companies', 0)}")
                
                return progress
            
            return None
            
        except Exception as e:
            log_error(f"❌ Ошибка загрузки прогресса: {e}")
            return None
    
    def save_partial_results(self, results: List[Dict[str, Any]]) -> bool:
        """
        Сохранить промежуточные результаты
        
        Args:
            results: Список результатов для сохранения
            
        Returns:
            True если сохранение успешно
        """
        try:
            with self._lock:
                # Добавляем новые результаты к существующим
                self._partial_results.extend(results)
                
                # Создаем метаданные
                metadata = {
                    "session_id": self.session_id,
                    "saved_at": datetime.now().isoformat(),
                    "total_results": len(self._partial_results),
                    "batch_size": len(results),
                    "progress": self._current_state.copy()
                }
                
                # Сохраняем результаты
                with open(self.results_file, 'w', encoding='utf-8') as f:
                    json.dump(self._partial_results, f, ensure_ascii=False, indent=2)
                
                # Сохраняем метаданные
                with open(self.metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                
                log_info(f"💾 Сохранено {len(results)} новых результатов (всего: {len(self._partial_results)})")
                return True
                
        except Exception as e:
            log_error(f"❌ Ошибка сохранения результатов: {e}")
            return False
    
    def load_partial_results(self) -> List[Dict[str, Any]]:
        """
        Загрузить промежуточные результаты
        
        Returns:
            Список результатов или пустой список
        """
        try:
            if self.results_file.exists():
                with open(self.results_file, 'r', encoding='utf-8') as f:
                    results = json.load(f)
                
                log_info(f"📂 Загружено {len(results)} промежуточных результатов")
                return results
            
            return []
            
        except Exception as e:
            log_error(f"❌ Ошибка загрузки результатов: {e}")
            return []
    
    def record_circuit_breaker_event(self, event_type: str, details: Dict[str, Any] = None):
        """
        Записать событие circuit breaker
        
        Args:
            event_type: Тип события (opened, closed, half_open)
            details: Дополнительные детали
        """
        try:
            with self._lock:
                event = {
                    "timestamp": datetime.now().isoformat(),
                    "type": event_type,
                    "details": details or {}
                }
                
                self._current_state["circuit_breaker_events"].append(event)
                self._current_state["last_circuit_breaker_event"] = event
                
                # Ограничиваем историю событий
                if len(self._current_state["circuit_breaker_events"]) > 50:
                    self._current_state["circuit_breaker_events"] = \
                        self._current_state["circuit_breaker_events"][-50:]
                
                log_debug(f"🛡️ Circuit breaker event recorded: {event_type}")
                
        except Exception as e:
            log_error(f"❌ Ошибка записи события circuit breaker: {e}")
    
    def mark_company_completed(self, company_name: str, product: str, success: bool = True):
        """
        Отметить компанию как обработанную
        
        Args:
            company_name: Название компании
            product: Название продукта  
            success: Успешно ли обработана
        """
        try:
            with self._lock:
                if success:
                    self._current_state["processed_companies"] += 1
                else:
                    self._current_state["failed_companies"] += 1
                
                log_debug(f"✅ Company marked completed: {company_name} ({product})")
                
        except Exception as e:
            log_error(f"❌ Ошибка отметки компании: {e}")
    
    def update_totals(self, total_products: int, total_companies: int):
        """
        Обновить общие счетчики
        
        Args:
            total_products: Общее количество продуктов
            total_companies: Общее количество компаний
        """
        try:
            with self._lock:
                self._current_state.update({
                    "total_products": total_products,
                    "total_companies": total_companies
                })
                
                log_debug(f"📊 Totals updated: {total_products} products, {total_companies} companies")
                
        except Exception as e:
            log_error(f"❌ Ошибка обновления счетчиков: {e}")
    
    def mark_completed(self, status: str = "completed"):
        """
        Отметить сессию как завершенную
        
        Args:
            status: Финальный статус (completed, failed, cancelled)
        """
        try:
            with self._lock:
                self._current_state.update({
                    "status": status,
                    "completed_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                })
                
                # Сохраняем финальное состояние
                with open(self.progress_file, 'w', encoding='utf-8') as f:
                    json.dump(self._current_state, f, ensure_ascii=False, indent=2)
                
                log_info(f"🏁 Сессия отмечена как завершенная: {status}")
                
        except Exception as e:
            log_error(f"❌ Ошибка завершения сессии: {e}")
    
    def clear_progress(self):
        """Очистить сохраненный прогресс"""
        try:
            files_to_remove = [self.progress_file, self.results_file, self.metadata_file]
            
            for file_path in files_to_remove:
                if file_path.exists():
                    file_path.unlink()
                    log_debug(f"🗑️ Removed: {file_path.name}")
            
            log_info("🧹 Progress cleared")
            
        except Exception as e:
            log_error(f"❌ Ошибка очистки прогресса: {e}")
    
    def get_state_summary(self) -> Dict[str, Any]:
        """
        Получить сводку о состоянии
        
        Returns:
            Словарь с информацией о состоянии
        """
        try:
            with self._lock:
                return {
                    "session_id": self.session_id,
                    "status": self._current_state.get("status", "unknown"),
                    "progress": {
                        "products": f"{self._current_state.get('current_product_index', 0)}/{self._current_state.get('total_products', 0)}",
                        "companies": f"{self._current_state.get('current_company_index', 0)}/{self._current_state.get('total_companies', 0)}",
                        "processed": self._current_state.get("processed_companies", 0),
                        "failed": self._current_state.get("failed_companies", 0)
                    },
                    "current": {
                        "product": self._current_state.get("current_product"),
                        "company": self._current_state.get("current_company"),
                        "audience": self._current_state.get("current_audience"),
                        "stage": self._current_state.get("current_stage")
                    },
                    "results_count": len(self._partial_results),
                    "circuit_breaker_events": len(self._current_state.get("circuit_breaker_events", [])),
                    "last_updated": self._current_state.get("updated_at")
                }
                
        except Exception as e:
            log_error(f"❌ Ошибка получения сводки: {e}")
            return {"error": str(e)}
    
    def can_resume(self) -> Tuple[bool, str]:
        """
        Проверить можно ли возобновить сессию
        
        Returns:
            (True/False, причина)
        """
        try:
            progress = self.load_progress()
            if not progress:
                return False, "No saved progress found"
            
            status = progress.get("status", "unknown")
            if status in ["completed", "cancelled"]:
                return False, f"Session already {status}"
            
            # Проверяем корректность данных
            if progress.get("total_products", 0) == 0:
                return False, "Invalid progress data (no products)"
            
            current_product_index = progress.get("current_product_index", 0)
            total_products = progress.get("total_products", 0)
            
            if current_product_index >= total_products:
                return False, "All products already processed"
            
            return True, "Can resume from saved progress"
            
        except Exception as e:
            return False, f"Error checking resume capability: {e}"
    
    def _load_existing_state(self):
        """Загрузить существующее состояние при инициализации"""
        try:
            # Загружаем прогресс
            if self.progress_file.exists():
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    saved_state = json.load(f)
                    self._current_state.update(saved_state)
            
            # Загружаем результаты
            if self.results_file.exists():
                self._partial_results = self.load_partial_results()
            
            log_debug(f"💾 Existing state loaded: {self._current_state.get('status', 'new')}")
            
        except Exception as e:
            log_error(f"❌ Ошибка загрузки существующего состояния: {e}") 