"""
Global Circuit Breaker для координированного управления OpenAI API запросами
Предотвращает cascade failures при rate limiting
"""

import time
import threading
from enum import Enum
from typing import Optional, List
from src.utils.logging import log_info, log_error, log_debug


class CircuitState(Enum):
    """Состояния Circuit Breaker"""
    CLOSED = "CLOSED"       # Нормальная работа
    OPEN = "OPEN"          # Блокировка всех запросов
    HALF_OPEN = "HALF_OPEN" # Тестовый режим восстановления


class CircuitOpenException(Exception):
    """Исключение когда Circuit Breaker заблокирован"""
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class OpenAICircuitBreaker:
    """
    Thread-safe Circuit Breaker для OpenAI API
    
    Логика работы:
    - CLOSED: пропускает все запросы, считает ошибки
    - OPEN: блокирует все запросы на timeout период  
    - HALF_OPEN: пропускает ограниченное количество тестовых запросов
    """
    
    def __init__(self, 
                 failure_threshold: int = 5,
                 recovery_timeout: int = 120,
                 success_threshold: int = 3,
                 rate_limit_keywords: List[str] = None):
        """
        Args:
            failure_threshold: Количество ошибок для перехода в OPEN
            recovery_timeout: Секунд ожидания в OPEN состоянии
            success_threshold: Успешных запросов для закрытия из HALF_OPEN
            rate_limit_keywords: Ключевые слова rate limit ошибок
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.rate_limit_keywords = rate_limit_keywords or [
            'rate_limit', 'quota_exceeded', 'too_many_requests', 
            'rate limit', 'limit exceeded', 'throttled'
        ]
        
        # Thread-safe состояние
        self._lock = threading.RLock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._half_open_requests = 0
        self._max_half_open_requests = 3
        
        log_info(f"🛡️ Circuit Breaker инициализирован: threshold={failure_threshold}, timeout={recovery_timeout}s")
    
    def can_execute(self) -> bool:
        """
        Проверяет можно ли выполнить запрос
        
        Returns:
            True если запрос разрешен, False если заблокирован
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
                
            elif self._state == CircuitState.OPEN:
                # Проверяем не пора ли попробовать восстановление
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                    return True
                return False
                
            elif self._state == CircuitState.HALF_OPEN:
                # В режиме тестирования разрешаем ограниченное количество запросов
                if self._half_open_requests < self._max_half_open_requests:
                    self._half_open_requests += 1
                    return True
                return False
                
        return False
    
    def record_success(self):
        """Записывает успешный запрос"""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                # В нормальном режиме сбрасываем счетчик ошибок
                if self._failure_count > 0:
                    self._failure_count = 0
                    log_debug("🛡️ Failure count reset after success")
                    
            elif self._state == CircuitState.HALF_OPEN:
                # В тестовом режиме считаем успехи
                self._success_count += 1
                log_debug(f"🛡️ Half-open success: {self._success_count}/{self.success_threshold}")
                
                if self._success_count >= self.success_threshold:
                    self._transition_to_closed()
    
    def record_failure(self, error: Exception) -> bool:
        """
        Записывает ошибку запроса
        
        Args:
            error: Исключение которое произошло
            
        Returns:
            True если это rate limit ошибка, False иначе
        """
        error_str = str(error).lower()
        is_rate_limit = any(keyword in error_str for keyword in self.rate_limit_keywords)
        
        if not is_rate_limit:
            # Не rate limit ошибка - не влияет на circuit breaker
            return False
            
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            log_debug(f"🛡️ Rate limit failure recorded: {self._failure_count}/{self.failure_threshold}")
            
            if self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition_to_open()
                    
            elif self._state == CircuitState.HALF_OPEN:
                # В тестовом режиме любая ошибка возвращает в OPEN
                self._transition_to_open()
                
        return True
    
    def get_state_info(self) -> dict:
        """Возвращает текущее состояние circuit breaker"""
        with self._lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure_time": self._last_failure_time,
                "time_until_retry": self._get_time_until_retry(),
                "half_open_requests": self._half_open_requests if self._state == CircuitState.HALF_OPEN else 0
            }
    
    def force_open(self, reason: str = "Manual"):
        """Принудительно открыть circuit breaker"""
        with self._lock:
            log_info(f"🛡️ Circuit Breaker принудительно открыт: {reason}")
            self._transition_to_open()
    
    def force_close(self, reason: str = "Manual"):
        """Принудительно закрыть circuit breaker"""
        with self._lock:
            log_info(f"🛡️ Circuit Breaker принудительно закрыт: {reason}")
            self._transition_to_closed()
    
    def _should_attempt_reset(self) -> bool:
        """Проверяет пора ли попробовать восстановление"""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.recovery_timeout
    
    def _get_time_until_retry(self) -> Optional[float]:
        """Возвращает секунд до следующей попытки"""
        if self._state != CircuitState.OPEN or self._last_failure_time is None:
            return None
        elapsed = time.time() - self._last_failure_time
        remaining = self.recovery_timeout - elapsed
        return max(0, remaining)
    
    def _transition_to_open(self):
        """Переход в состояние OPEN"""
        if self._state != CircuitState.OPEN:
            self._state = CircuitState.OPEN
            self._success_count = 0
            self._half_open_requests = 0
            retry_time = self._get_time_until_retry()
            log_error(f"🔴 Circuit Breaker ОТКРЫТ - блокировка OpenAI запросов на {self.recovery_timeout}s")
            log_info(f"⏰ Следующая попытка через {retry_time:.1f} секунд")
    
    def _transition_to_half_open(self):
        """Переход в состояние HALF_OPEN"""
        if self._state != CircuitState.HALF_OPEN:
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0
            self._half_open_requests = 0
            log_info(f"🟡 Circuit Breaker ПОЛУОТКРЫТ - тестируем {self._max_half_open_requests} запросов")
    
    def _transition_to_closed(self):
        """Переход в состояние CLOSED"""
        if self._state != CircuitState.CLOSED:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_requests = 0
            self._last_failure_time = None
            log_info(f"🟢 Circuit Breaker ЗАКРЫТ - нормальная работа восстановлена")


# Глобальный инстанс circuit breaker
_global_circuit_breaker: Optional[OpenAICircuitBreaker] = None
_breaker_lock = threading.Lock()


def get_circuit_breaker() -> OpenAICircuitBreaker:
    """Получить глобальный инстанс circuit breaker (thread-safe singleton)"""
    global _global_circuit_breaker
    
    if _global_circuit_breaker is None:
        with _breaker_lock:
            if _global_circuit_breaker is None:
                from src.utils.config import CIRCUIT_BREAKER_CONFIG
                _global_circuit_breaker = OpenAICircuitBreaker(
                    failure_threshold=CIRCUIT_BREAKER_CONFIG['failure_threshold'],
                    recovery_timeout=CIRCUIT_BREAKER_CONFIG['recovery_timeout'],
                    success_threshold=CIRCUIT_BREAKER_CONFIG['success_threshold'],
                    rate_limit_keywords=CIRCUIT_BREAKER_CONFIG['rate_limit_keywords']
                )
    
    return _global_circuit_breaker


def reset_circuit_breaker():
    """Сброс глобального circuit breaker (для тестов)"""
    global _global_circuit_breaker
    with _breaker_lock:
        _global_circuit_breaker = None 