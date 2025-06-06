"""
Центральные настройки системы анализа критериев
"""

import os

# Версия системы
VERSION = "2.0.0"

# Базовые настройки
DEFAULT_COMPANIES_LIMIT = 0
DEFAULT_TIMEOUT = 30
DEFAULT_RETRY_COUNT = 3

# Настройки API
API_TIMEOUTS = {
    'openai': 30,
    'serper': 15,
    'default': 20
}

# Настройки обработки
PROCESSING_DEFAULTS = {
    'batch_size': 5,
    'max_concurrent_requests': 3,
    'delay_between_requests': 1.0
}

# Настройки логирования
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s | %(levelname)s | %(message)s',
    'file_encoding': 'utf-8'
}

# Поддерживаемые кодировки файлов
SUPPORTED_ENCODINGS = [
    'utf-8-sig',
    'utf-8', 
    'windows-1251',
    'cp1252',
    'iso-8859-1',
    'latin1'
]

# Типы критериев
CRITERIA_TYPES = {
    'GENERAL': 'General',
    'QUALIFICATION': 'Qualification', 
    'MANDATORY': 'Mandatory',
    'NTH': 'NTH'
}

# Статусы обработки
PROCESSING_STATUSES = {
    'PASSED': 'Passed',
    'NOT_PASSED': 'Not Passed',
    'ND': 'ND',
    'ERROR': 'Error',
    'SKIPPED': 'Skipped'
} 