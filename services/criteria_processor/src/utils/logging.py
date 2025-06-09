"""
Конфигурация логирования для системы верификации
"""

import logging
import os
from datetime import datetime

def setup_logging():
    """Настраивает логирование в файл с временной меткой"""
    
    # Создаем папку для логов
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    # Временная метка для имени файла
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(logs_dir, f"analysis_{timestamp}.log")
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()  # Дублируем в консоль основные сообщения
        ]
    )
    
    # Создаем отдельный логгер только для файла (без консоли)
    file_logger = logging.getLogger('file_only')
    file_logger.setLevel(logging.INFO)
    
    # Убираем наследование от root logger
    file_logger.propagate = False
    
    # Добавляем только файловый handler
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
    file_logger.addHandler(file_handler)
    
    logging.info(f"📝 Логирование настроено: {log_filename}")
    return log_filename, file_logger

def log_info(message, console=True):
    """Логирует сообщение с возможностью отключения консольного вывода"""
    if console:
        logging.info(message)
    else:
        file_logger = logging.getLogger('file_only')
        file_logger.info(message)

def log_error(message):
    """Логирует ошибки"""
    logging.error(message)

def log_debug(message):
    """Логирует debug информацию (только в файл)"""
    file_logger = logging.getLogger('file_only')
    file_logger.info(f"DEBUG: {message}") 