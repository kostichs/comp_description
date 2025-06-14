"""
Criteria Analysis API Module

Модульная архитектура для анализа критериев:
- analysis: запуск анализа
- sessions: управление сессиями  
- results: получение результатов
- files: управление файлами критериев
- management: утилиты и мониторинг
"""

from .routes import router

__all__ = ["router"] 