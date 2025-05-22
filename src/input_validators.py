"""
Валидаторы входных данных для проекта генерации описаний компаний.

Этот модуль содержит функции для нормализации URL.
"""

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def normalize_domain(url: str) -> str:
    """
    Нормализует URL, извлекая только домен без протокола, www и пути.
    
    Args:
        url: Исходный URL, который может содержать протокол, www, путь и т.д.
        
    Returns:
        str: Нормализованный домен (например, 'example.com')
    """
    if not url or not isinstance(url, str):
        return ""
    
    # Очищаем URL от пробелов
    url = url.strip()
    
    # Если URL не содержит протокол, добавляем временно для корректного парсинга
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        # Используем urlparse для извлечения домена
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Удаляем www. из начала домена, если присутствует
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Удаляем порт, если он есть
        domain = domain.split(':')[0]
        
        return domain.lower()  # Приводим к нижнему регистру для единообразия
    except Exception as e:
        logger.warning(f"Error normalizing domain from URL '{url}': {e}")
        # Если парсинг не удался, возвращаем исходный URL без протоколов и www
        url = url.replace('http://', '').replace('https://', '')
        if url.startswith('www.'):
            url = url[4:]
        return url.split('/')[0].lower()  # Берем только домен, удаляя все пути 