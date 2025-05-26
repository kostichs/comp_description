"""
Валидаторы входных данных для проекта генерации описаний компаний.

Этот модуль содержит функции для нормализации URL и названий компаний.
"""

import logging
from urllib.parse import urlparse
import re
import unicodedata
import html
from typing import Tuple

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

def validate_company_name(company_name: str) -> Tuple[bool, str]:
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

def normalize_company_name(company_name: str, for_search: bool = False) -> str:
    """
    Нормализует название компании, исправляя проблемы с кодировкой и Unicode.
    
    Args:
        company_name: Исходное название компании
        for_search: Если True, применяет дополнительную нормализацию для поиска
        
    Returns:
        str: Нормализованное название компании
    """
    if not company_name or not isinstance(company_name, str):
        return ""
    
    # Шаг 1: Исправление проблем с кодировкой
    normalized = company_name
    
    # Исправляем распространенные проблемы с кодировкой UTF-8
    encoding_fixes = {
        # Эстонские символы
        'OÃœ': 'OÜ',
        'oÃœ': 'oü',
        
        # Немецкие символы
        'VÃ–LGY': 'VÖLGY',
        'vÃ¶lgy': 'völgy',
        'Ã¤': 'ä',
        'Ã¶': 'ö',
        'Ã¼': 'ü',
        'ÃŸ': 'ß',
        
        # Французские символы
        'Ã ': 'à',
        'Ã¡': 'á',
        'Ã¢': 'â',
        'Ã£': 'ã',
        'Ã¨': 'è',
        'Ã©': 'é',
        'Ãª': 'ê',
        'Ã«': 'ë',
        'Ã¬': 'ì',
        'Ã­': 'í',
        'Ã®': 'î',
        'Ã¯': 'ï',
        'Ã²': 'ò',
        'Ã³': 'ó',
        'Ã´': 'ô',
        'Ãµ': 'õ',
        'Ã¹': 'ù',
        'Ãº': 'ú',
        'Ã»': 'û',
        'Ã§': 'ç',
        
        # Испанские символы
        'Ã±': 'ñ',
        
        # Скандинавские символы
        'Ã¥': 'å',
        'Ã†': 'Æ',
        'Ã¸': 'ø',
        'Ã…': 'Å',
    }
    
    # Применяем исправления кодировки
    for broken, correct in encoding_fixes.items():
        normalized = normalized.replace(broken, correct)
    
    # Шаг 2: Декодирование HTML entities
    try:
        normalized = html.unescape(normalized)
    except Exception as e:
        logger.debug(f"HTML unescape failed for '{company_name}': {e}")
    
    # Шаг 3: Нормализация Unicode
    try:
        # Нормализуем Unicode в форму NFC (Canonical Decomposition, followed by Canonical Composition)
        normalized = unicodedata.normalize('NFC', normalized)
    except Exception as e:
        logger.debug(f"Unicode normalization failed for '{company_name}': {e}")
    
    # Шаг 4: Попытка исправить поврежденную кодировку через re-encoding
    try:
        # Попробуем различные методы исправления кодировки
        if any(ord(char) > 127 for char in normalized):
            # Метод 1: latin-1 -> utf-8
            try:
                fixed = normalized.encode('latin-1').decode('utf-8')
                if fixed != normalized and len(fixed) > 0:
                    logger.info(f"Fixed encoding (latin-1->utf-8): '{normalized}' -> '{fixed}'")
                    normalized = fixed
            except (UnicodeEncodeError, UnicodeDecodeError):
                # Метод 2: cp1252 -> utf-8 (Windows кодировка)
                try:
                    fixed = normalized.encode('cp1252').decode('utf-8')
                    if fixed != normalized and len(fixed) > 0:
                        logger.info(f"Fixed encoding (cp1252->utf-8): '{normalized}' -> '{fixed}'")
                        normalized = fixed
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
    except Exception as e:
        logger.debug(f"Encoding fix failed for '{company_name}': {e}")
    
    # Шаг 5: Очистка и нормализация для поиска (если требуется)
    if for_search:
        # Удаляем лишние пробелы
        normalized = ' '.join(normalized.split())
        
        # Удаляем кавычки в начале и конце
        normalized = normalized.strip('"\'""''')
        
        # Нормализуем регистр для некоторых общих сокращений
        normalized = re.sub(r'\b(inc|llc|ltd|corp|gmbh|co|kg|oo|ooo)\b\.?', 
                           lambda m: m.group(0).upper(), normalized, flags=re.IGNORECASE)
    
    # Шаг 6: Финальная очистка
    normalized = normalized.strip()
    
    # Логируем изменения, если они были
    if normalized != company_name:
        logger.info(f"Normalized company name: '{company_name}' -> '{normalized}'")
    
    return normalized

def detect_encoding_issues(text: str) -> list:
    """
    Обнаруживает потенциальные проблемы с кодировкой в тексте.
    
    Args:
        text: Текст для анализа
        
    Returns:
        list: Список обнаруженных проблем
    """
    issues = []
    
    if not text:
        return issues
    
    # Проверяем на распространенные паттерны поврежденной кодировки
    encoding_patterns = [
        (r'Ã[œŒ]', 'Possible corrupted Ü/ü characters'),
        (r'Ã[–—]', 'Possible corrupted Ö/ö characters'),
        (r'Ã[¤¥]', 'Possible corrupted ä characters'),
        (r'Ã[±]', 'Possible corrupted ñ character'),
        (r'Ã[§]', 'Possible corrupted ç character'),
        (r'Ã[¡-¿]', 'Possible corrupted accented characters'),
        (r'Ð[Ñ-ï]', 'Possible corrupted Cyrillic characters'),
        (r'â€[™œž]', 'Possible corrupted quotation marks'),
        (r'â€["]', 'Possible corrupted dash characters'),
    ]
    
    for pattern, description in encoding_patterns:
        if re.search(pattern, text):
            issues.append(description)
    
    # Проверяем на смешанные кодировки
    has_latin = bool(re.search(r'[a-zA-Z]', text))
    has_cyrillic = bool(re.search(r'[а-яё]', text, re.IGNORECASE))
    has_special_chars = bool(re.search(r'[À-ÿ]', text))
    
    if has_latin and has_cyrillic and has_special_chars:
        issues.append('Mixed character sets detected (Latin + Cyrillic + Special)')
    
    # Проверяем на подозрительные последовательности
    if re.search(r'[Ã][^a-zA-Z0-9\s]', text):
        issues.append('Suspicious Ã character sequences')
    
    return issues 