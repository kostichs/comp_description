"""
Валидаторы входных данных для проекта генерации описаний компаний.

Этот модуль содержит функции для нормализации URL.
"""

import logging
from urllib.parse import urlparse
import re
import unicodedata

logger = logging.getLogger(__name__)

# Черный список общих терминов на разных языках, которые НЕ являются компаниями
GENERIC_TERMS_BLACKLIST = {
    # Английский
    "remote work", "remote job", "job opportunities", "work from home", 
    "employment", "career", "hiring", "recruitment", "staffing",
    "freelance", "contractor", "consultant", "temp work", "part time",
    "full time", "job search", "career opportunities", "business opportunity",
    "work opportunity", "employment opportunity", "job opening",
    
    # Русский
    "удаленная работа", "работа на дому", "вакансии", "карьера", 
    "трудоустройство", "рекрутинг", "кадры", "фриланс", "подработка",
    
    # Арабский
    "فرص عمل", "عمل عن بعد", "وظائف", "توظيف", "عمل من المنزل",
    "فرص وظيفية", "عمل حر", "مهن", "كاريير", "وظيفة",
    
    # Испанский
    "trabajo remoto", "oportunidades de trabajo", "empleo", "carrera",
    "trabajo desde casa", "freelance", "contratista",
    
    # Французский
    "travail à distance", "opportunités d'emploi", "emploi", "carrière",
    "travail à domicile", "freelance",
    
    # Немецкий
    "fernarbeit", "homeoffice", "stellenangebote", "karriere", "beschäftigung",
    
    # Китайский
    "远程工作", "工作机会", "就业", "职业", "招聘", "兼职", "全职"
}

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

def is_generic_term(text: str) -> bool:
    """
    Проверяет, является ли текст общим термином, а не названием реальной компании.
    
    Args:
        text: Текст для проверки
        
    Returns:
        bool: True если это общий термин, False если может быть названием компании
    """
    if not text or not isinstance(text, str):
        return True
    
    # Нормализуем текст: убираем лишние пробелы, приводим к нижнему регистру
    normalized_text = ' '.join(text.strip().lower().split())
    
    # Удаляем знаки препинания для более точного сравнения
    cleaned_text = re.sub(r'[^\w\s]', ' ', normalized_text)
    cleaned_text = ' '.join(cleaned_text.split())
    
    # Проверяем точное совпадение
    if cleaned_text in GENERIC_TERMS_BLACKLIST:
        return True
    
    # Проверяем частичные совпадения для многословных терминов
    for term in GENERIC_TERMS_BLACKLIST:
        if len(term.split()) > 1:  # Многословные термины
            if term in cleaned_text or cleaned_text in term:
                return True
    
    # Проверяем на очень короткие тексты (менее 2 символов)
    if len(cleaned_text) < 2:
        return True
    
    # Проверяем на подозрительные паттерны
    suspicious_patterns = [
        r'^job\s',
        r'^work\s',
        r'^career\s',
        r'^employment\s',
        r'^hiring\s',
        r'^recruitment\s',
        r'opportunities?$',
        r'jobs?$',
        r'^وظائف',
        r'^عمل',
        r'^فرص',
        r'^trabajo\s',
        r'^emploi\s',
        r'^работа\s'
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, cleaned_text, re.IGNORECASE):
            return True
    
    return False

def validate_company_name(company_name: str) -> tuple[bool, str]:
    """
    Валидирует название компании, проверяя что это не общий термин.
    
    Args:
        company_name: Название компании для проверки
        
    Returns:
        tuple[bool, str]: (is_valid, error_message)
    """
    if not company_name or not isinstance(company_name, str):
        return False, "Company name cannot be empty"
    
    # Проверяем на общие термины
    if is_generic_term(company_name):
        return False, f"'{company_name}' appears to be a generic term rather than a specific company name"
    
    # Проверяем минимальную длину
    if len(company_name.strip()) < 2:
        return False, "Company name is too short"
    
    # Проверяем на только цифры
    if company_name.strip().isdigit():
        return False, "Company name cannot consist only of digits"
    
    return True, "" 