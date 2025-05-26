"""
Утилиты для работы с CSV файлами с поддержкой нормализации кодировки.
"""

import csv
import chardet
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from src.input_validators import normalize_company_name, detect_encoding_issues

logger = logging.getLogger(__name__)

def detect_file_encoding(file_path: str) -> str:
    """
    Определяет кодировку файла.
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        str: Определенная кодировка
    """
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)  # Читаем первые 10KB для определения кодировки
            result = chardet.detect(raw_data)
            encoding = result['encoding']
            confidence = result['confidence']
            
            logger.info(f"Detected encoding for {file_path}: {encoding} (confidence: {confidence:.2f})")
            
            # Если уверенность низкая, используем UTF-8 по умолчанию
            if confidence < 0.7:
                logger.warning(f"Low confidence in encoding detection, using UTF-8 as fallback")
                return 'utf-8'
                
            return encoding or 'utf-8'
    except Exception as e:
        logger.error(f"Error detecting encoding for {file_path}: {e}")
        return 'utf-8'

def read_csv_with_normalization(
    file_path: str, 
    normalize_names: bool = True,
    encoding: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Читает CSV файл с автоматической нормализацией названий компаний.
    
    Args:
        file_path: Путь к CSV файлу
        normalize_names: Применять ли нормализацию названий компаний
        encoding: Принудительная кодировка (если None, определяется автоматически)
        
    Returns:
        List[Dict[str, Any]]: Список строк с нормализованными данными
    """
    if not encoding:
        encoding = detect_file_encoding(file_path)
    
    results = []
    encoding_issues_count = 0
    normalized_count = 0
    
    try:
        # Пробуем несколько кодировок в порядке приоритета
        encodings_to_try = [encoding, 'utf-8', 'cp1252', 'latin-1', 'utf-8-sig']
        
        for enc in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=enc, newline='') as f:
                    reader = csv.DictReader(f)
                    
                    for row_num, row in enumerate(reader, 1):
                        processed_row = {}
                        
                        for key, value in row.items():
                            if value is None:
                                processed_row[key] = ""
                                continue
                                
                            # Нормализуем ключи (названия колонок)
                            normalized_key = key.strip() if key else ""
                            
                            # Нормализуем значения
                            normalized_value = str(value).strip()
                            
                            # Специальная обработка для колонок с названиями компаний
                            if normalize_names and any(keyword in normalized_key.lower() for keyword in 
                                                     ['company', 'name', 'organization', 'business', 'firm']):
                                
                                # Проверяем на проблемы с кодировкой
                                issues = detect_encoding_issues(normalized_value)
                                if issues:
                                    encoding_issues_count += 1
                                    logger.debug(f"Row {row_num}: Encoding issues in '{normalized_value}': {', '.join(issues)}")
                                
                                # Нормализуем название компании
                                original_value = normalized_value
                                normalized_value = normalize_company_name(normalized_value, for_search=True)
                                
                                if normalized_value != original_value:
                                    normalized_count += 1
                                    logger.debug(f"Row {row_num}: Normalized '{original_value}' -> '{normalized_value}'")
                            
                            processed_row[normalized_key] = normalized_value
                        
                        results.append(processed_row)
                
                # Если дошли до сюда, значит чтение прошло успешно
                logger.info(f"Successfully read {len(results)} rows from {file_path} using encoding {enc}")
                if encoding_issues_count > 0:
                    logger.warning(f"Found encoding issues in {encoding_issues_count} rows")
                if normalized_count > 0:
                    logger.info(f"Normalized {normalized_count} company names")
                
                return results
                
            except UnicodeDecodeError as e:
                logger.debug(f"Failed to read {file_path} with encoding {enc}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error reading {file_path} with encoding {enc}: {e}")
                continue
        
        # Если все кодировки не сработали
        raise Exception(f"Could not read {file_path} with any of the attempted encodings: {encodings_to_try}")
        
    except Exception as e:
        logger.error(f"Error reading CSV file {file_path}: {e}")
        raise

def write_csv_with_proper_encoding(
    data: List[Dict[str, Any]], 
    file_path: str, 
    encoding: str = 'utf-8-sig'
) -> None:
    """
    Записывает данные в CSV файл с правильной кодировкой.
    
    Args:
        data: Данные для записи
        file_path: Путь к выходному файлу
        encoding: Кодировка для записи (по умолчанию utf-8-sig для совместимости с Excel)
    """
    if not data:
        logger.warning(f"No data to write to {file_path}")
        return
    
    try:
        # Создаем директорию, если её нет
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Получаем все возможные ключи из всех строк
        all_keys = set()
        for row in data:
            all_keys.update(row.keys())
        
        fieldnames = sorted(list(all_keys))
        
        with open(file_path, 'w', encoding=encoding, newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        logger.info(f"Successfully wrote {len(data)} rows to {file_path} using encoding {encoding}")
        
    except Exception as e:
        logger.error(f"Error writing CSV file {file_path}: {e}")
        raise

def analyze_csv_encoding_issues(file_path: str) -> Dict[str, Any]:
    """
    Анализирует CSV файл на предмет проблем с кодировкой.
    
    Args:
        file_path: Путь к CSV файлу
        
    Returns:
        Dict[str, Any]: Отчет об анализе
    """
    report = {
        'file_path': file_path,
        'detected_encoding': None,
        'total_rows': 0,
        'rows_with_issues': 0,
        'common_issues': {},
        'problematic_rows': [],
        'suggested_fixes': []
    }
    
    try:
        # Определяем кодировку
        report['detected_encoding'] = detect_file_encoding(file_path)
        
        # Читаем файл без нормализации для анализа
        data = read_csv_with_normalization(file_path, normalize_names=False)
        report['total_rows'] = len(data)
        
        for row_num, row in enumerate(data, 1):
            row_issues = []
            
            for key, value in row.items():
                if not value:
                    continue
                    
                issues = detect_encoding_issues(str(value))
                if issues:
                    row_issues.extend(issues)
                    
                    # Подсчитываем частоту проблем
                    for issue in issues:
                        report['common_issues'][issue] = report['common_issues'].get(issue, 0) + 1
            
            if row_issues:
                report['rows_with_issues'] += 1
                if len(report['problematic_rows']) < 10:  # Сохраняем только первые 10 проблемных строк
                    report['problematic_rows'].append({
                        'row_number': row_num,
                        'issues': row_issues,
                        'data': {k: v for k, v in row.items() if v}  # Только непустые значения
                    })
        
        # Генерируем рекомендации
        if report['rows_with_issues'] > 0:
            report['suggested_fixes'].append("Use normalize_company_name() function to fix encoding issues")
            
            if 'Possible corrupted Ü/ü characters' in report['common_issues']:
                report['suggested_fixes'].append("File likely has Estonian company names with corrupted encoding")
                
            if 'Possible corrupted Ö/ö characters' in report['common_issues']:
                report['suggested_fixes'].append("File likely has German company names with corrupted encoding")
                
            if 'Possible corrupted Cyrillic characters' in report['common_issues']:
                report['suggested_fixes'].append("File likely has Cyrillic text with corrupted encoding")
        
        logger.info(f"Encoding analysis complete for {file_path}: {report['rows_with_issues']}/{report['total_rows']} rows have issues")
        
    except Exception as e:
        logger.error(f"Error analyzing {file_path}: {e}")
        report['error'] = str(e)
    
    return report 