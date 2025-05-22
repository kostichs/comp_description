"""
Скрипт для нормализации URL во входных данных.

Этот скрипт читает файл CSV/Excel, нормализует URL во второй колонке
и сохраняет файл с нормализованными URL обратно.
"""

import pandas as pd
import os
import logging
import argparse
from pathlib import Path
from src.input_validators import normalize_domain

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def normalize_urls_in_file(input_file: str, output_file: str = None) -> str:
    """
    Нормализует URL во второй колонке файла и сохраняет результат.
    
    Args:
        input_file: Путь к входному файлу (CSV или Excel)
        output_file: Путь для сохранения результата (если не указан, перезаписывает входной файл)
        
    Returns:
        str: Путь к файлу с нормализованными URL
    """
    # Если output_file не указан, используем input_file
    if not output_file:
        output_file = input_file
    
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Файл не найден: {input_file}")
    
    # Определяем формат файла
    is_excel = input_path.suffix.lower() in ['.xlsx', '.xls']
    
    try:
        # Загружаем файл
        df = pd.read_excel(input_file) if is_excel else pd.read_csv(input_file)
        
        # Проверяем, есть ли хотя бы две колонки
        if df.shape[1] < 2:
            logger.error(f"В файле {input_file} меньше двух колонок")
            return None
        
        # Получаем имена колонок
        column_names = df.columns.tolist()
        first_column = column_names[0]
        second_column = column_names[1]
        
        # Нормализуем URL во второй колонке
        logger.info(f"Нормализация URL в колонке '{second_column}'")
        normalized_urls = []
        changes_count = 0
        
        for url in df[second_column]:
            if pd.isna(url) or not url:
                normalized_urls.append(url)
            else:
                url_str = str(url).strip()
                normalized_url = normalize_domain(url_str)
                normalized_urls.append(normalized_url)
                if normalized_url != url_str:
                    changes_count += 1
                    logger.info(f"Нормализовано: '{url_str}' -> '{normalized_url}'")
        
        # Заменяем значения во второй колонке
        df[second_column] = normalized_urls
        
        # Сохраняем файл
        if is_excel:
            df.to_excel(output_file, index=False)
        else:
            df.to_csv(output_file, index=False)
        
        logger.info(f"Нормализовано {changes_count} URL")
        logger.info(f"Файл сохранен: {output_file}")
        
        return output_file
    
    except Exception as e:
        logger.error(f"Ошибка при нормализации URL: {e}")
        return None

def remove_duplicates_by_domain(input_file: str, output_file: str = None) -> tuple[str, dict]:
    """
    Удаляет дубликаты компаний по нормализованным доменам.
    
    Args:
        input_file: Путь к входному файлу с нормализованными URL (CSV или Excel)
        output_file: Путь для сохранения результата (если не указан, перезаписывает входной файл)
        
    Returns:
        tuple: (путь к файлу без дубликатов, словарь с информацией о дедупликации)
    """
    # Если output_file не указан, используем input_file
    if not output_file:
        output_file = input_file
    
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Файл не найден: {input_file}")
    
    # Определяем формат файла
    is_excel = input_path.suffix.lower() in ['.xlsx', '.xls']
    
    try:
        # Загружаем файл
        if is_excel:
            df = pd.read_excel(input_file, engine='openpyxl')
        else:
            df = pd.read_csv(input_file)
        
        # Определяем колонку с URL
        url_column = None
        
        # Проверяем первые две колонки
        for i in range(min(2, len(df.columns))):
            col = df.columns[i]
            if df[col].dtype == 'object' and df[col].str.contains('http|www', case=False, na=False).any():
                url_column = col
                break
        
        # Если колонка с URL не найдена, ищем по индексу 1 (вторая колонка)
        if url_column is None and len(df.columns) > 1:
            url_column = df.columns[1]
        
        # Если колонка все равно не найдена, используем первую колонку
        if url_column is None:
            url_column = df.columns[0]
        
        original_row_count = len(df)
        logger.info(f"Поиск дубликатов по доменам в колонке '{url_column}'")
        logger.info(f"Всего строк в файле до удаления дубликатов: {original_row_count}")
        
        # Словарь для отслеживания уникальных доменов
        unique_domains = {}
        # Список для хранения дубликатов
        duplicate_rows = []
        
        # Проходим по всем строкам датафрейма
        for index, row in df.iterrows():
            # Получаем URL или домен и название компании
            url = str(row[url_column]) if pd.notna(row[url_column]) else ""
            company_name = str(row[df.columns[0]]) if pd.notna(row[df.columns[0]]) else "Unknown"
            
            # Нормализуем домен
            domain = normalize_domain(url)
            
            logger.info(f"Проверка компании: '{company_name}' с доменом '{domain}'")
            
            # Если домен уже был встречен, это дубликат
            if domain in unique_domains and domain:  # Проверяем, что домен не пустой
                logger.info(f"Найден дубликат домена '{domain}' для компании '{company_name}'")
                duplicate_rows.append(index)
            else:
                # Запоминаем домен и индекс строки
                unique_domains[domain] = index
        
        # Если есть дубликаты, удаляем их и сохраняем датафрейм
        duplicate_count = len(duplicate_rows)
        
        if duplicate_count > 0:
            duplicate_domains = []
            for index in duplicate_rows:
                url = str(df.loc[index, url_column]) if pd.notna(df.loc[index, url_column]) else ""
                domain = normalize_domain(url)
                if domain and domain not in duplicate_domains:
                    duplicate_domains.append(domain)
            
            logger.info(f"Удаление {duplicate_count} дубликатов по следующим доменам: {', '.join(duplicate_domains)}")
            
            # Сохраняем дубликаты в отдельный файл
            duplicates_df = df.loc[duplicate_rows]
            duplicates_output_file = f"{os.path.splitext(output_file)[0]}_duplicates{os.path.splitext(output_file)[1]}"
            
            # Удаляем дубликаты
            df = df.drop(duplicate_rows)
            logger.info(f"Осталось {len(df)} компаний с уникальными доменами")
            
            # Сохраняем датафрейм без дубликатов
            if is_excel:
                df.to_excel(output_file, index=False, engine='openpyxl')
            else:
                df.to_csv(output_file, index=False)
            
            # Сохраняем дубликаты
            if is_excel:
                duplicates_df.to_excel(duplicates_output_file, index=False, engine='openpyxl')
            else:
                duplicates_df.to_csv(duplicates_output_file, index=False)
            
            logger.info(f"Удалено {duplicate_count} дубликатов")
            logger.info(f"Файл без дубликатов сохранен: {output_file}")
            logger.info(f"Дубликаты сохранены в файл: {duplicates_output_file}")
        else:
            logger.info("Дубликаты по доменам не найдены")
            
        # Собираем информацию о дедупликации
        deduplication_info = {
            "original_count": original_row_count,
            "duplicates_removed": duplicate_count,
            "final_count": len(df)
        }
        
        return output_file, deduplication_info
        
    except Exception as e:
        logger.error(f"Ошибка при удалении дубликатов: {e}")
        raise

def normalize_and_remove_duplicates(input_file: str, output_file: str = None) -> tuple[str, dict]:
    """
    Нормализует URL и удаляет дубликаты по доменам в одной операции.
    
    Args:
        input_file: Путь к входному файлу (CSV или Excel)
        output_file: Путь для сохранения результата (если не указан, перезаписывает входной файл)
        
    Returns:
        tuple: (путь к файлу без дубликатов, словарь с информацией о дедупликации)
    """
    try:
        # Шаг 1: Нормализация URL
        normalized_file = normalize_urls_in_file(input_file, output_file)
        
        # Шаг 2: Удаление дубликатов
        result_file, deduplication_info = remove_duplicates_by_domain(normalized_file)
        
        # Логируем детальную информацию о дедупликации
        logger.info(f"normalize_and_remove_duplicates результат: файл={result_file}, удалено дубликатов={deduplication_info['duplicates_removed']}")
        
        # Обновляем метаданные сессии, если файл находится в каталоге сессии
        try:
            from src.data_io import load_session_metadata, save_session_metadata
            
            # Проверяем, содержит ли путь к файлу слово 'sessions'
            file_path = Path(result_file)
            if 'sessions' in str(file_path):
                # Предполагаем, что ID сессии - это имя родительской директории
                session_id = file_path.parent.name
                
                # Загружаем метаданные
                all_metadata = load_session_metadata()
                session_found_and_updated = False # Флаг для проверки
                for meta_idx, meta in enumerate(all_metadata):
                    if meta.get("session_id") == session_id:
                        logger.info(f"Found session {session_id} in metadata. Updating...")
                        # Обновляем количество компаний в метаданных
                        meta["original_companies_count"] = deduplication_info["original_count"]
                        meta["companies_count"] = deduplication_info["final_count"]
                        meta["total_companies"] = deduplication_info["final_count"]
                        
                        # Добавляем информацию о дедупликации
                        meta["deduplication_info"] = deduplication_info
                        
                        # Добавляем сообщение о дедупликации
                        if "processing_messages" not in meta:
                            meta["processing_messages"] = []
                        
                        import time
                        dedup_message_text = f"Обнаружено и удалено {deduplication_info['duplicates_removed']} дубликатов. Обрабатывается {deduplication_info['final_count']} уникальных компаний вместо {deduplication_info['original_count']}."
                        
                        # Проверяем, есть ли уже такое сообщение
                        message_exists = any(
                            msg.get("type") == "deduplication" and msg.get("message") == dedup_message_text 
                            for msg in meta["processing_messages"]
                        )
                        
                        if not message_exists:
                            meta["processing_messages"].append({
                                "type": "deduplication",
                                "message": dedup_message_text,
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                            })
                        
                        logger.info(f"Values for session {session_id} before save: total_companies={meta.get('total_companies')}, deduplication_info={meta.get('deduplication_info')}")
                        # Обновляем элемент в списке all_metadata напрямую по индексу, чтобы быть уверенным
                        all_metadata[meta_idx] = meta 
                        save_session_metadata(all_metadata)
                        logger.info(f"Обновлены метаданные сессии {session_id} с информацией о дедупликации")
                        session_found_and_updated = True
                        break
                if not session_found_and_updated:
                    logger.warning(f"Session {session_id} not found in metadata during deduplication update step. Metadata not updated with dedup info.")
        except Exception as e:
            logger.error(f"Ошибка при обновлении метаданных сессии: {e}")
        
        return result_file, deduplication_info
    
    except Exception as e:
        logger.error(f"Ошибка в процессе нормализации и удаления дубликатов: {e}")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Нормализация URL и удаление дубликатов во входных данных")
    parser.add_argument("input_file", help="Путь к входному файлу (CSV или Excel)")
    parser.add_argument("--output", "-o", help="Путь для сохранения результата (если не указан, перезаписывает входной файл)")
    parser.add_argument("--normalize-only", action="store_true", help="Только нормализовать URL без удаления дубликатов")
    parser.add_argument("--remove-duplicates-only", action="store_true", help="Только удалить дубликаты без нормализации URL")
    
    args = parser.parse_args()
    
    if args.normalize_only:
        normalize_urls_in_file(args.input_file, args.output)
    elif args.remove_duplicates_only:
        remove_duplicates_by_domain(args.input_file, args.output)
    else:
        normalize_and_remove_duplicates(args.input_file, args.output) 