"""
Модуль для обработки различных кодировок файлов
Поддерживает автоматическое определение кодировки и корректное чтение файлов
"""

import chardet
import pandas as pd
import os
from typing import Optional, Tuple, List
from pathlib import Path
from src.utils.logging import log_info, log_error, log_debug

# Список поддерживаемых кодировок в порядке приоритета
DEFAULT_ENCODINGS = [
    'utf-8',           # UTF-8 (стандарт)
    'utf-8-sig',       # UTF-8 с BOM
    'utf-16',          # UTF-16 с BOM
    'utf-16le',        # UTF-16 Little Endian
    'utf-16be',        # UTF-16 Big Endian
    'windows-1251',    # Кириллица (русский, украинский, болгарский)
    'windows-1250',    # Центральная Европа (польский, чешский, венгерский)
    'windows-1252',    # Западная Европа (английский, французский, немецкий)
    'iso-8859-1',      # Latin-1 (западная Европа)
    'iso-8859-2',      # Latin-2 (центральная Европа)
    'iso-8859-5',      # Latin/Cyrillic
    'cp1251',          # Альтернативное название для windows-1251
    'cp1252',          # Альтернативное название для windows-1252
    'latin1',          # Альтернативное название для iso-8859-1
]

def detect_file_encoding(file_path: str, sample_size: int = 100000) -> str:
    """
    Определяет кодировку файла
    
    Args:
        file_path: Путь к файлу
        sample_size: Размер выборки для анализа (по умолчанию 100KB)
        
    Returns:
        Определенная кодировка
    """
    try:
        # Читаем образец файла
        with open(file_path, 'rb') as file:
            raw_data = file.read(sample_size)
        
        if not raw_data:
            log_info(f"File {file_path} is empty, defaulting to utf-8")
            return 'utf-8'
        
        # Используем chardet для определения кодировки
        result = chardet.detect(raw_data)
        detected_encoding = result.get('encoding', '').lower()
        confidence = result.get('confidence', 0)
        
        log_debug(f"Chardet result for {file_path}: {detected_encoding} (confidence: {confidence:.2f})")
        
        # Если уверенность высокая и кодировка известна
        if confidence > 0.7 and detected_encoding in [enc.lower() for enc in DEFAULT_ENCODINGS]:
            return detected_encoding
        
        # Если chardet не уверен, пробуем стандартные кодировки
        for encoding in DEFAULT_ENCODINGS:
            try:
                with open(file_path, 'r', encoding=encoding, errors='strict') as file:
                    file.read(1024)  # Пробуем прочитать небольшой фрагмент
                log_info(f"Successfully decoded {file_path} with encoding: {encoding}")
                return encoding
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        # Если ничего не подошло, возвращаем UTF-8 как fallback
        log_info(f"Could not determine encoding for {file_path}, defaulting to utf-8")
        return 'utf-8'
        
    except Exception as e:
        log_error(f"Error detecting encoding for {file_path}: {e}")
        return 'utf-8'

def read_text_file_with_encoding(file_path: str, encodings: List[str] = None) -> Tuple[str, str]:
    """
    Читает текстовый файл, пытаясь разные кодировки
    
    Args:
        file_path: Путь к файлу
        encodings: Список кодировок для попытки (по умолчанию DEFAULT_ENCODINGS)
        
    Returns:
        Кортеж (содержимое файла, использованная кодировка)
    """
    if encodings is None:
        encodings = DEFAULT_ENCODINGS
    
    # Сначала пробуем автоопределение
    detected_encoding = detect_file_encoding(file_path)
    if detected_encoding not in encodings:
        encodings = [detected_encoding] + encodings
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding, errors='strict') as file:
                content = file.read()
            
            # Нормализуем содержимое
            content = normalize_text_encoding(content)
            
            log_info(f"Successfully read {file_path} with encoding: {encoding}")
            return content, encoding
            
        except (UnicodeDecodeError, UnicodeError) as e:
            log_debug(f"Failed to read {file_path} with encoding {encoding}: {e}")
            continue
        except Exception as e:
            log_error(f"Unexpected error reading {file_path} with encoding {encoding}: {e}")
            continue
    
    raise UnicodeDecodeError(f"Unable to decode file {file_path} with any of the attempted encodings: {encodings}")

def read_csv_with_encoding(file_path: str, **kwargs) -> Tuple[pd.DataFrame, str]:
    """
    Читает CSV файл, автоматически определяя кодировку
    
    Args:
        file_path: Путь к CSV файлу
        **kwargs: Дополнительные параметры для pandas.read_csv
        
    Returns:
        Кортеж (DataFrame, использованная кодировка)
    """
    detected_encoding = detect_file_encoding(file_path)
    
    encodings_to_try = [detected_encoding] + [enc for enc in DEFAULT_ENCODINGS if enc != detected_encoding]
    
    for encoding in encodings_to_try:
        try:
            # Читаем CSV с текущей кодировкой
            df = pd.read_csv(file_path, encoding=encoding, **kwargs)
            
            # Нормализуем текстовые колонки
            for col in df.columns:
                if df[col].dtype == 'object':  # Текстовые колонки
                    df[col] = df[col].apply(lambda x: normalize_text_encoding(str(x)) if pd.notna(x) else x)
            
            log_info(f"Successfully read CSV {file_path} with encoding: {encoding}")
            return df, encoding
            
        except (UnicodeDecodeError, UnicodeError) as e:
            log_debug(f"Failed to read CSV {file_path} with encoding {encoding}: {e}")
            continue
        except Exception as e:
            log_error(f"Error reading CSV {file_path} with encoding {encoding}: {e}")
            continue
    
    raise UnicodeDecodeError(f"Unable to read CSV {file_path} with any supported encoding")

def read_excel_with_encoding(file_path: str, **kwargs) -> Tuple[pd.DataFrame, str]:
    """
    Читает Excel файл с обработкой кодировки текстовых полей
    
    Args:
        file_path: Путь к Excel файлу
        **kwargs: Дополнительные параметры для pandas.read_excel
        
    Returns:
        Кортеж (DataFrame, 'excel' как индикатор формата)
    """
    try:
        df = pd.read_excel(file_path, **kwargs)
        
        # Нормализуем текстовые колонки
        for col in df.columns:
            if df[col].dtype == 'object':  # Текстовые колонки
                df[col] = df[col].apply(lambda x: normalize_text_encoding(str(x)) if pd.notna(x) else x)
        
        log_info(f"Successfully read Excel {file_path}")
        return df, 'excel'
        
    except Exception as e:
        log_error(f"Error reading Excel {file_path}: {e}")
        raise

def save_text_with_encoding(content: str, file_path: str, encoding: str = 'utf-8-sig') -> None:
    """
    Сохраняет текст в файл с указанной кодировкой
    
    Args:
        content: Содержимое для сохранения
        file_path: Путь к файлу
        encoding: Кодировка (по умолчанию UTF-8 с BOM для лучшей совместимости)
    """
    try:
        # Создаем директорию если её нет
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding=encoding, errors='strict') as file:
            file.write(content)
            
        log_info(f"Successfully saved text to {file_path} with encoding: {encoding}")
        
    except Exception as e:
        log_error(f"Error saving text to {file_path}: {e}")
        raise

def save_csv_with_encoding(df: pd.DataFrame, file_path: str, encoding: str = 'utf-8-sig', **kwargs) -> None:
    """
    Сохраняет DataFrame в CSV с указанной кодировкой
    
    Args:
        df: DataFrame для сохранения
        file_path: Путь к файлу
        encoding: Кодировка (по умолчанию UTF-8 с BOM)
        **kwargs: Дополнительные параметры для pandas.to_csv
    """
    try:
        # Создаем директорию если её нет
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Устанавливаем параметры по умолчанию
        default_kwargs = {'index': False, 'encoding': encoding}
        default_kwargs.update(kwargs)
        
        df.to_csv(file_path, **default_kwargs)
        
        log_info(f"Successfully saved CSV to {file_path} with encoding: {encoding}")
        
    except Exception as e:
        log_error(f"Error saving CSV to {file_path}: {e}")
        raise

def normalize_text_encoding(text: str) -> str:
    """
    Нормализует текст, исправляя проблемы с кодировкой кавычек, апострофов и спецсимволов
    
    Args:
        text: Исходный текст
        
    Returns:
        Нормализованный текст
    """
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    
    try:
        # Убираем BOM если есть
        if text.startswith('\ufeff'):
            text = text[1:]
        
        # Исправляем распространенные артефакты неправильной кодировки
        # Используем Unicode escape sequences для безопасности
        
        # Кавычки и апострофы
        text = text.replace('\u2019', "'")     # Right single quotation mark
        text = text.replace('\u2018', "'")     # Left single quotation mark  
        text = text.replace('\u201C', '"')     # Left double quotation mark
        text = text.replace('\u201D', '"')     # Right double quotation mark
        
        # Тире
        text = text.replace('\u2013', '-')     # En dash
        text = text.replace('\u2014', '-')     # Em dash
        
        # Многоточие
        text = text.replace('\u2026', '...')   # Horizontal ellipsis
        
        # Неразрывные пробелы
        text = text.replace('\u00A0', ' ')     # Non-breaking space
        text = text.replace('\u2002', ' ')     # En space
        text = text.replace('\u2003', ' ')     # Em space
        text = text.replace('\u2009', ' ')     # Thin space
        text = text.replace('\u200A', ' ')     # Hair space
        
        # Исправляем артефакты кодировки UTF-8 -> Windows-1252 -> UTF-8
        encoding_artifacts = {
            'â€™': "'",      # Right single quotation mark artifact
            'â€œ': '"',      # Left double quotation mark artifact
            'â€': '"',       # Right double quotation mark artifact
            'â€˜': "'",      # Left single quotation mark artifact
            'â€"': '–',      # En dash artifact  
            'â€"': '—',      # Em dash artifact
            'â€¦': '...',    # Ellipsis artifact
            'â€¢': '•',      # Bullet artifact
            'â‚¬': '€',      # Euro artifact
            'Â£': '£',       # Pound artifact
            'Â©': '©',       # Copyright artifact
            'Â®': '®',       # Registered artifact
            'Â ': ' ',       # Non-breaking space artifact
            'Â': '',         # Standalone non-breaking space artifact
        }
        
        for artifact, replacement in encoding_artifacts.items():
            text = text.replace(artifact, replacement)
        
        # Нормализуем Unicode
        import unicodedata
        text = unicodedata.normalize('NFKC', text)
        
        # Убираем невидимые символы управления, кроме разрешенных
        text = ''.join(char for char in text if unicodedata.category(char) != 'Cc' or char in '\n\r\t')
        
        # Убираем лишние пробелы, но сохраняем переносы строк
        import re
        # Убираем множественные пробелы/табы, но оставляем переносы строк  
        text = re.sub(r'[ \t]+', ' ', text)  # Только пробелы и табы в один пробел
        # Убираем лишние переносы строк (больше 2 подряд)
        text = re.sub(r'\n{3,}', '\n\n', text)  # Максимум 2 переноса подряд
        text = text.strip()  # Убираем пробелы в начале и конце
        
        return text
        
    except Exception as e:
        log_error(f"Error normalizing text: {e}")
        return text

def get_file_info(file_path: str) -> dict:
    """
    Получает информацию о файле, включая предполагаемую кодировку
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        Словарь с информацией о файле
    """
    try:
        file_stat = os.stat(file_path)
        detected_encoding = detect_file_encoding(file_path)
        
        return {
            'path': file_path,
            'size': file_stat.st_size,
            'size_mb': round(file_stat.st_size / (1024 * 1024), 2),
            'detected_encoding': detected_encoding,
            'extension': Path(file_path).suffix.lower(),
            'exists': True
        }
        
    except Exception as e:
        log_error(f"Error getting file info for {file_path}: {e}")
        return {
            'path': file_path,
            'error': str(e),
            'exists': False
        } 