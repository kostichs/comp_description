"""
Модуль для работы с кодировками файлов
"""

import chardet
import pandas as pd
from src.utils.logging import log_info, log_error, log_debug

def detect_encoding(file_path):
    """Автоматически определяет кодировку файла"""
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)  # Читаем первые 10KB для определения
            result = chardet.detect(raw_data)
            encoding = result['encoding']
            confidence = result['confidence']
            log_debug(f"📝 Определена кодировка {file_path}: {encoding} (уверенность: {confidence:.2f})")
            return encoding
    except Exception as e:
        log_error(f"❌ Ошибка определения кодировки для {file_path}: {e}")
        return 'utf-8'

def load_csv_with_encoding(file_path):
    """Загружает CSV с автоматическим определением кодировки"""
    # Список кодировок для попыток
    encodings_to_try = [
        detect_encoding(file_path),  # Автоопределение
        'utf-8-sig',                 # UTF-8 с BOM
        'utf-8',                     # Обычный UTF-8
        'windows-1251',              # Кириллица Windows
        'cp1252',                    # Windows Western
        'iso-8859-1',                # Latin-1
        'latin1'                     # Fallback
    ]
    
    # Убираем дубликаты
    encodings_to_try = list(dict.fromkeys(encodings_to_try))
    
    for encoding in encodings_to_try:
        if not encoding:
            continue
            
        try:
            log_debug(f"🔄 Пробуем загрузить {file_path} с кодировкой: {encoding}")
            df = pd.read_csv(file_path, encoding=encoding)
            log_info(f"✅ Файл загружен с кодировкой: {encoding}")
            return df
        except (UnicodeDecodeError, UnicodeError) as e:
            log_debug(f"⚠️  Не удалось с кодировкой {encoding}: {e}")
            continue
        except Exception as e:
            log_error(f"❌ Ошибка загрузки файла {file_path}: {e}")
            raise
    
    # Если ничего не помогло
    raise UnicodeError(f"Не удалось определить кодировку для файла: {file_path}") 