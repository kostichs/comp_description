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

def remove_duplicates_by_domain(input_file: str, output_file: str = None) -> str:
    """
    Удаляет дубликаты компаний по нормализованным доменам.
    
    Args:
        input_file: Путь к входному файлу с нормализованными URL (CSV или Excel)
        output_file: Путь для сохранения результата (если не указан, перезаписывает входной файл)
        
    Returns:
        str: Путь к файлу без дубликатов
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
        
        logger.info(f"Поиск дубликатов по доменам в колонке '{second_column}'")
        
        # Создаем словарь {домен: первый индекс}
        domains_index = {}
        duplicate_indices = []
        
        # Создаем копию DataFrame для хранения оригинальных данных
        df_original = df.copy()
        
        # Добавляем отладочную информацию
        logger.info(f"Всего строк в файле до удаления дубликатов: {len(df)}")
        
        # Преобразуем все URL в нижний регистр для сравнения
        # и создаем временный столбец с нормализованными доменами
        df['_normalized_domain'] = df[second_column].apply(
            lambda x: normalize_domain(x) if pd.notna(x) and x else ''
        )
        
        # Находим все дубликаты
        unique_domains = set()
        duplicated_domains = set()
        
        for idx, row in df.iterrows():
            domain = row['_normalized_domain']
            company_name = row[first_column]
            
            # Пропускаем пустые значения
            if pd.isna(domain) or not domain or domain == '':
                continue
                
            # Выводим более подробную информацию
            logger.info(f"Проверка компании: '{company_name}' с доменом '{domain}'")
            
            # Проверяем, есть ли уже такой домен
            if domain in unique_domains:
                # Это дубликат
                logger.info(f"Найден дубликат домена '{domain}' для компании '{company_name}'")
                duplicate_indices.append(idx)
                duplicated_domains.add(domain)
            else:
                # Это первое вхождение домена
                unique_domains.add(domain)
        
        # Удаляем временный столбец
        df.drop('_normalized_domain', axis=1, inplace=True)
        
        # Если есть дубликаты, удаляем их
        if duplicate_indices:
            logger.info(f"Удаление {len(duplicate_indices)} дубликатов по следующим доменам: {', '.join(duplicated_domains)}")
            df_no_duplicates = df.drop(duplicate_indices)
            
            # Выводим список оставшихся доменов
            remaining_domains = df_no_duplicates[second_column].apply(
                lambda x: normalize_domain(x) if pd.notna(x) and x else ''
            ).tolist()
            
            logger.info(f"Осталось {len(df_no_duplicates)} компаний с уникальными доменами")
            
            # Сохраняем файл без дубликатов
            if is_excel:
                df_no_duplicates.to_excel(output_file, index=False)
            else:
                df_no_duplicates.to_csv(output_file, index=False)
            
            logger.info(f"Удалено {len(duplicate_indices)} дубликатов")
            logger.info(f"Файл без дубликатов сохранен: {output_file}")
            
            # Сохраняем дубликаты в отдельный файл для анализа
            duplicates_file = str(input_path.with_stem(f"{input_path.stem}_duplicates"))
            df_duplicates = df_original.iloc[duplicate_indices]
            
            if is_excel:
                df_duplicates.to_excel(duplicates_file, index=False)
            else:
                df_duplicates.to_csv(duplicates_file, index=False)
                
            logger.info(f"Дубликаты сохранены в файл: {duplicates_file}")
        else:
            logger.info("Дубликатов не найдено")
            
            # Если дубликатов нет, просто возвращаем исходный файл
            return input_file
        
        return output_file
    
    except Exception as e:
        logger.error(f"Ошибка при удалении дубликатов: {e}")
        return None

def normalize_and_remove_duplicates(input_file: str, output_file: str = None) -> str:
    """
    Нормализует URL и удаляет дубликаты в одной операции.
    
    Args:
        input_file: Путь к входному файлу (CSV или Excel)
        output_file: Путь для сохранения результата (если не указан, перезаписывает входной файл)
        
    Returns:
        str: Путь к файлу с нормализованными URL без дубликатов
    """
    # Если output_file не указан, генерируем временный файл
    if not output_file:
        input_path = Path(input_file)
        output_file = str(input_path.with_stem(f"{input_path.stem}_normalized_no_duplicates"))
    
    # Сначала нормализуем URL
    normalized_file = normalize_urls_in_file(input_file, output_file)
    if not normalized_file:
        logger.error("Не удалось нормализовать URL")
        return None
    
    # Затем удаляем дубликаты
    no_duplicates_file = remove_duplicates_by_domain(normalized_file, output_file)
    if not no_duplicates_file:
        logger.error("Не удалось удалить дубликаты")
        return normalized_file  # Возвращаем хотя бы нормализованный файл
    
    return no_duplicates_file

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