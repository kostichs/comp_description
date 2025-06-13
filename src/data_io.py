import pandas as pd
import os
import csv
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple

# Импортируем функцию нормализации URL
from src.input_validators import normalize_domain

# Setup logging
logger = logging.getLogger(__name__)

# Determine Project Root (assuming this file is in src/)
PROJECT_ROOT = Path(__file__).parent.parent 

def load_and_prepare_company_names(file_path: str | Path, col_index: int = 0) -> Optional[List[Dict[str, Optional[str]]]]:
    """
    Loads company data from Excel/CSV. Requires exactly two columns: Company Name and Website URL.
    Optionally supports 'predator' column for HubSpot integration.
    
    Args:
        file_path: Path to the input file
        col_index: Index of the first column to load (default 0)
    
    Returns:
        List of dictionaries, where each dictionary has 'name', 'url', optionally 'status' and 'predator' keys.
        Returns None if file could not be loaded, is empty, or doesn't have required two columns.
    """
    file_path_str = str(file_path)
    df_loaded = None
    
    try:
        # Определяем формат файла и загружаем его
        reader = pd.read_excel if file_path_str.lower().endswith(('.xlsx', '.xls')) else pd.read_csv
        
        # Сначала попробуем загрузить весь файл, чтобы определить количество столбцов и наличие колонки predator
        df_loaded = reader(file_path_str)
        
        # Проверяем наличие колонки Status (новый формат после normalize_and_remove_duplicates)
        has_status_column = 'Status' in df_loaded.columns
        
        # Ищем колонку с predator (гибкий поиск)
        predator_column_name = None
        has_predator_column = False
        for col in df_loaded.columns:
            if 'predator' in str(col).lower():
                predator_column_name = col
                has_predator_column = True
                break
        
        has_two_or_more_columns = df_loaded.shape[1] >= 2
        
        # Логируем наличие колонки predator
        if has_predator_column:
            logging.info(f"Detected predator column '{predator_column_name}' in {file_path_str}, will include predator data")
        
        if has_status_column:
            # Новый формат с колонкой Status
            logging.info(f"Detected Status column in {file_path_str}, using processed format")
            # Ожидаемые колонки: Company Name, Website, Status, Error_Message
            required_cols = ['Company Name', 'Website', 'Status']
            if not all(col in df_loaded.columns for col in required_cols):
                # Пробуем загрузить по позициям, если названия колонок не соответствуют
                df_loaded = reader(file_path_str, header=0)
                if df_loaded.shape[1] >= 3:
                    df_loaded.columns = list(df_loaded.columns[:2]) + ['Status'] + list(df_loaded.columns[3:])
        elif has_two_or_more_columns:
            # Старый формат с двумя колонками
            logging.info(f"Detected two or more columns in {file_path_str}, using first two columns")
            # Если есть predator колонка, загружаем её тоже
            if has_predator_column:
                # Загружаем первые два столбца плюс predator
                df_loaded = reader(file_path_str, header=0)  # Загружаем весь файл
            else:
                # Используем только первые два столбца
                df_loaded = reader(file_path_str, usecols=[0, 1], header=0)
        else:
            # Отклоняем файлы с одной колонкой
            logging.error(f"File {file_path_str} has only one column. Two columns required: Company Name and Website URL")
            return None
            
    except (ValueError, ImportError, FileNotFoundError) as ve:
        logging.warning(f"Initial read failed for {file_path_str}, trying header=None: {ve}")
        try:
            # Пробуем без заголовка
            df_loaded = reader(file_path_str, header=None)
            
            # Проверяем, есть ли два столбца
            has_two_or_more_columns = df_loaded.shape[1] >= 2
            
            # Если есть два столбца, загружаем оба
            if has_two_or_more_columns:
                logging.info(f"Detected two or more columns in {file_path_str} (without header), using first two columns")
                df_loaded = reader(file_path_str, usecols=[0, 1], header=None)
            else:
                logging.error(f"File {file_path_str} has only one column (without header). Two columns required: Company Name and Website URL")
                return None
                
        except Exception as read_err_no_header:
            logging.error(f"Error reading {file_path_str} even with header=None: {read_err_no_header}")
            return None
    except Exception as read_err:
        logging.error(f"Error reading file {file_path_str}: {read_err}")
        return None

    if df_loaded is not None and not df_loaded.empty:
        # Проверяем наличие колонки Status для определения формата
        has_status_column = 'Status' in df_loaded.columns
        # Переопределяем has_predator_column для текущего df_loaded
        predator_column_name = None
        has_predator_column = False
        for col in df_loaded.columns:
            if 'predator' in str(col).lower():
                predator_column_name = col
                has_predator_column = True
                break
        
        if has_status_column:
            # Новый формат с колонкой Status - обрабатываем все компании включая помеченные
            company_names_series = df_loaded.iloc[:, 0].astype(str).str.strip()
            website_series = df_loaded.iloc[:, 1].astype(str).str.strip()
            status_series = df_loaded['Status'].astype(str).str.strip()
            
            # Получаем данные predator если колонка существует
            predator_series = None
            if has_predator_column and predator_column_name:
                predator_series = df_loaded[predator_column_name].astype(str).str.strip()
            
            result_list_of_dicts = []
            for i, (name, website, status) in enumerate(zip(company_names_series, website_series, status_series)):
                if name and name.lower() not in ['nan', '']:
                    # Нормализуем URL если он есть и статус VALID
                    url_value = None
                    if website and website.lower() not in ['nan', '']:
                        if status == 'VALID':
                            # Для валидных компаний нормализуем URL
                            normalized_url = normalize_domain(website)
                            if normalized_url:
                                url_value = normalized_url
                                # Логируем изменение, если URL был нормализован
                                if normalized_url != website:
                                    logging.info(f"Normalized URL for '{name}': '{website}' -> '{normalized_url}'")
                        else:
                            # Для невалидных компаний сохраняем URL как есть
                            url_value = website
                    
                    # Получаем значение predator для текущей строки
                    predator_value = None
                    if predator_series is not None and i < len(predator_series):
                        predator_val = predator_series.iloc[i]
                        if predator_val is not None and str(predator_val).lower() not in ['nan', '']:
                            predator_value = predator_val
                    
                    # Добавляем в результат
                    company_data = {
                        'name': name, 
                        'url': url_value,
                        'status': status if status.lower() not in ['nan', ''] else 'VALID'
                    }
                    
                    # Добавляем predator если есть (включая "0")
                    if predator_value is not None:
                        company_data['predator'] = predator_value
                    
                    result_list_of_dicts.append(company_data)
            
            if result_list_of_dicts:
                valid_count = len([c for c in result_list_of_dicts if c.get('status') == 'VALID'])
                duplicate_count = len([c for c in result_list_of_dicts if c.get('status') == 'DUPLICATE'])
                dead_url_count = len([c for c in result_list_of_dicts if c.get('status') == 'DEAD_URL'])
                logging.info(f"Loaded {len(result_list_of_dicts)} companies from {file_path_str}: {valid_count} valid, {duplicate_count} duplicates, {dead_url_count} dead URLs")
                return result_list_of_dicts
            else:
                logging.warning(f"No valid company names in {file_path_str} (processed format).")
                return None
                
        elif df_loaded.shape[1] >= 2:
            # Старый формат с двумя или более колонками
            company_names_series = df_loaded.iloc[:, 0].astype(str).str.strip()
            second_column_series = df_loaded.iloc[:, 1].astype(str).str.strip()
            
            # Получаем данные predator если колонка существует
            predator_series = None
            if has_predator_column and predator_column_name:
                predator_series = df_loaded[predator_column_name].astype(str).str.strip()
            
            result_list_of_dicts = []
            for i, (name, second_value) in enumerate(zip(company_names_series, second_column_series)):
                if name and name.lower() not in ['nan', '']:
                    # Если URL во втором столбце есть, нормализуем его
                    url_value = None
                    if second_value and second_value.lower() not in ['nan', '']:
                        # Нормализуем URL, извлекая только домен
                        normalized_url = normalize_domain(second_value)
                        if normalized_url:
                            url_value = normalized_url
                            # Логируем изменение, если URL был нормализован
                            if normalized_url != second_value:
                                logging.info(f"Normalized URL for '{name}': '{second_value}' -> '{normalized_url}'")
                    
                    # Получаем значение predator для текущей строки
                    predator_value = None
                    if predator_series is not None and i < len(predator_series):
                        predator_val = predator_series.iloc[i]
                        if predator_val is not None and str(predator_val).lower() not in ['nan', '']:
                            predator_value = predator_val
                    
                    # Добавляем в результат (старый формат без статуса)
                    company_data = {'name': name, 'url': url_value}
                    
                    # Добавляем predator если есть (включая "0")
                    if predator_value is not None:
                        company_data['predator'] = predator_value
                    
                    result_list_of_dicts.append(company_data)
            
            if result_list_of_dicts:
                logging.info(f"Loaded {len(result_list_of_dicts)} companies with name and URL from {file_path_str}")
                return result_list_of_dicts
            else:
                logging.warning(f"No valid company names in the first column of {file_path_str} (when checking two columns).")
                return None
        else:
            # Файл не содержит достаточно колонок
            logging.error(f"File {file_path_str} does not have the required two columns (Company Name and Website URL)")
            return None
    else:
        logging.warning(f"Could not load data from {file_path_str} or the file is empty.")
        return None

def load_context_file(context_file_path: str) -> str | None:
    """Loads the content of a context text file."""
    if os.path.exists(context_file_path):
        try:
            with open(context_file_path, 'r', encoding='utf-8') as f:
                context_text = f.read().strip()
            if context_text: 
                print(f"Successfully loaded context from: {context_file_path}")
                return context_text
            else:
                print(f"Context file found but empty: {context_file_path}")
                return None
        except Exception as e:
            print(f"Error reading context file {context_file_path}: {e}")
            return None
    else:
        return None

def save_context_file(context_file_path: str, context_text: str) -> bool:
    """Saves the provided context text to a file."""
    try:
        # Ensure the directory exists before saving
        context_dir = os.path.dirname(context_file_path)
        if context_dir and not os.path.exists(context_dir):
             os.makedirs(context_dir)
             print(f"Created context directory: {context_dir}")
             
        with open(context_file_path, 'w', encoding='utf-8') as f:
            f.write(context_text)
        print(f"Context saved to: {context_file_path}")
        return True
    except Exception as e:
        print(f"Error saving context file {context_file_path}: {e}")
        return False

# === Session Metadata Handling (Using Project Root Paths) ===
SESSIONS_METADATA_FILE = PROJECT_ROOT / "sessions_metadata.json" # Use Path object
SESSIONS_DIR = PROJECT_ROOT / "output" / "sessions" # Use Path object

def ensure_sessions_dir_exists():
    """Ensures the sessions directory exists."""
    if not SESSIONS_DIR.exists(): # Use Path.exists()
        try:
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True) # Use Path.mkdir()
            logging.info(f"Created sessions directory: {SESSIONS_DIR}")
        except OSError as e:
            logging.error(f"Could not create sessions directory {SESSIONS_DIR}. Error: {e}")

def load_session_metadata() -> list[dict]:
    """Loads session metadata from the JSON file."""
    ensure_sessions_dir_exists()
    if not SESSIONS_METADATA_FILE.exists(): # Use Path.exists()
        logging.warning(f"\'{SESSIONS_METADATA_FILE}\' not found. Initializing with empty list.")
        return []
    try:
        # Log file modification time before reading
        try:
            mod_time = os.path.getmtime(SESSIONS_METADATA_FILE)
            logging.info(f"Attempting to load session metadata. File '{SESSIONS_METADATA_FILE}' last modified at: {mod_time}")
        except OSError:
            logging.warning(f"Could not get modification time for '{SESSIONS_METADATA_FILE}'.")

        with open(SESSIONS_METADATA_FILE, 'r', encoding='utf-8') as f:
            content_before_load = f.read() # Read content first for logging
            f.seek(0) # Reset file pointer to the beginning before json.load
            metadata = json.loads(content_before_load) # Use json.loads with string content
            
            # Log the actual content being loaded for the specific session if possible
            # This requires knowing the session_id, which this generic function doesn't.
            # So, we log a snippet or hash if it's too large.
            # content_snippet = content_before_load[:500] + "..." if len(content_before_load) > 500 else content_before_load
            # logging.info(f"Successfully loaded session metadata from '{SESSIONS_METADATA_FILE}'. Content snippet: {content_snippet}")
            
            if not isinstance(metadata, list):
                 logging.error(f"Invalid format in \'{SESSIONS_METADATA_FILE}\'. Expected a list. Returning empty list.")
                 return []
            return metadata
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from \'{SESSIONS_METADATA_FILE}\'. Returning empty list.")
        return []
    except Exception as e:
        logging.error(f"Error loading session metadata: {e}", exc_info=True)
        return []

def save_session_metadata(metadata: list[dict]):
    """Saves session metadata list to the JSON file."""
    ensure_sessions_dir_exists()
    
    # Log the metadata that is about to be saved, especially for the relevant session
    # This requires knowing session_id, so we might log a relevant part or full if small
    try:
        metadata_str_for_log = json.dumps(metadata, indent=2, ensure_ascii=False)
        # snippet_to_log = metadata_str_for_log[:500] + "..." if len(metadata_str_for_log) > 500 else metadata_str_for_log
        # logging.info(f"Attempting to save session metadata. Data snippet: {snippet_to_log}")
    except Exception as log_e:
        logging.warning(f"Could not serialize metadata for logging before save: {log_e}")

    try:
        with open(SESSIONS_METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            f.flush()  # Ensure all internal buffers are written to the OS
            os.fsync(f.fileno())  # Ensure OS writes to disk
        logging.info(f"Successfully saved session metadata to {SESSIONS_METADATA_FILE} with fsync.")
        # Log file modification time after writing
        try:
            mod_time = os.path.getmtime(SESSIONS_METADATA_FILE)
            logging.info(f"File '{SESSIONS_METADATA_FILE}' last modified at: {mod_time} (after save)")
        except OSError:
            logging.warning(f"Could not get modification time for '{SESSIONS_METADATA_FILE}' after save.")
            
    except Exception as e:
        logging.error(f"Error saving session metadata: {e}", exc_info=True)

# === Results CSV Handling ===
def save_results_csv(results: list[dict], output_path: str, expected_fields: list[str] = None, append_mode: bool = False):
    """
    Save results to CSV file.
    
    Args:
        results: List of result dictionaries
        output_path: Path to save CSV file
        expected_fields: List of expected field names (optional)
        append_mode: Whether to append to existing file rather than overwrite
    """
    import csv
    import os
    from pathlib import Path
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Determine field names
    if expected_fields:
        fieldnames = expected_fields
    elif results and len(results) > 0:
        fieldnames = list(results[0].keys())
    else:
        fieldnames = ["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp", "HubSpot_Company_ID", "Predator_ID"]
    
    # Determine mode based on append_mode and file existence
    file_exists = os.path.exists(output_path)
    mode = 'a' if append_mode else 'w'
    
    # Write to CSV
    with open(output_path, mode, newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        # Write header only if writing a new file or appending to empty file
        if mode == 'w' or (mode == 'a' and not file_exists):
            writer.writeheader()
        
        for result in results:
            # Ensure all expected fields are present
            row = {field: result.get(field, '') for field in fieldnames}
            writer.writerow(row)
    
    logging.info(f"Saved {len(results)} result(s) to {output_path}")

def save_results_json(results: List[Dict[str, Any]], output_path: str, append_mode: bool = False):
    """
    Сохраняет полные результаты обработки компаний в JSON файл.
    Включает все данные из CSV плюс структурированные данные.
    
    Args:
        results: Список результатов с данными компаний
        output_path: Путь для сохранения JSON файла
        append_mode: Режим добавления в существующий файл вместо перезаписи
    """
    # Создаем директорию, если она не существует
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Подготавливаем полные данные результатов
    json_data = []
    
    for result in results:
        # Создаем полную структуру данных, включающую все поля
        json_result = {
            # Основные поля из CSV
            "Company_Name": result.get("Company_Name", ""),
            "Official_Website": result.get("Official_Website", ""),
            "LinkedIn_URL": result.get("LinkedIn_URL", ""),
            "Description": result.get("Description", ""),
            "Timestamp": result.get("Timestamp", ""),
            "HubSpot_Company_ID": result.get("HubSpot_Company_ID", ""),
            "Predator_ID": result.get("Predator_ID", ""),
            "Quality_Status": result.get("Quality_Status", ""),
            
            # Структурированные данные (если есть)
            "structured_data": result.get("structured_data", {}),
            
            # Дополнительные поля (валидация, интеграции и т.д.)
            "validation": result.get("validation", {}),
            "integrations": result.get("integrations", {}),
            
            # Любые другие поля, которые могут быть в результате
        }
        
        # Добавляем все остальные поля, которые не были явно указаны выше
        for key, value in result.items():
            if key not in json_result:
                json_result[key] = value
        
        json_data.append(json_result)
    
    # Если в режиме добавления и файл существует, загружаем существующие данные
    existing_data = []
    if append_mode and os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                if not isinstance(existing_data, list):
                    existing_data = []
        except Exception as e:
            logging.error(f"Error loading existing JSON data from {output_path}: {e}")
            existing_data = []
    
    # Объединяем существующие и новые данные
    final_data = existing_data + json_data
    
    # Сохраняем в JSON
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved {len(json_data)} complete result(s) to {output_path}")
        return True
    except Exception as e:
        logging.error(f"Error saving complete results to {output_path}: {e}")
        return False

def save_structured_data_incrementally(result: Dict[str, Any], output_path: str):
    """
    Сохраняет полные данные об одной компании в JSON файл инкрементально.
    Включает все данные из CSV плюс структурированные данные.
    
    Args:
        result: Результат с данными одной компании
        output_path: Путь для сохранения JSON файла
    """
    # Создаем директорию, если она не существует
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Подготавливаем полные данные результата
    json_result = {
        # Основные поля из CSV
        "Company_Name": result.get("Company_Name", ""),
        "Official_Website": result.get("Official_Website", ""),
        "LinkedIn_URL": result.get("LinkedIn_URL", ""),
        "Description": result.get("Description", ""),
        "Timestamp": result.get("Timestamp", ""),
        "HubSpot_Company_ID": result.get("HubSpot_Company_ID", ""),
        "Predator_ID": result.get("Predator_ID", ""),
        "Quality_Status": result.get("Quality_Status", ""),
        
        # Структурированные данные (если есть)
        "structured_data": result.get("structured_data", {}),
        
        # Дополнительные поля (валидация, интеграции и т.д.)
        "validation": result.get("validation", {}),
        "integrations": result.get("integrations", {}),
    }
    
    # Добавляем все остальные поля, которые не были явно указаны выше
    for key, value in result.items():
        if key not in json_result:
            json_result[key] = value
    
    # Загружаем существующие данные, если файл существует
    existing_data = []
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                if not isinstance(existing_data, list):
                    existing_data = []
        except Exception as e:
            logging.error(f"Error loading existing JSON data from {output_path}: {e}")
            existing_data = []
    
    # Добавляем новые данные
    existing_data.append(json_result)
    
    # Сохраняем в JSON
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
        logging.info(f"Added 1 complete result to {output_path}")
        return True
    except Exception as e:
        logging.error(f"Error saving complete result to {output_path}: {e}")
        return False

def merge_original_with_results(original_file_path: str, results_file_path: str, output_file_path: str) -> bool:
    """
    Объединяет исходный файл с результатами обработки.
    Исходные колонки остаются на своих местах, результаты добавляются в новые колонки.
    
    Args:
        original_file_path: Путь к исходному файлу
        results_file_path: Путь к файлу с результатами
        output_file_path: Путь для сохранения объединенного файла
        
    Returns:
        bool: True если объединение прошло успешно
    """
    try:
        # Загружаем исходный файл
        if original_file_path.lower().endswith(('.xlsx', '.xls')):
            original_df = pd.read_excel(original_file_path)
        else:
            original_df = pd.read_csv(original_file_path, encoding='utf-8-sig')
        
        # Загружаем файл с результатами
        if results_file_path.lower().endswith(('.xlsx', '.xls')):
            results_df = pd.read_excel(results_file_path)
        else:
            results_df = pd.read_csv(results_file_path, encoding='utf-8-sig')
        
        logging.info(f"Исходный файл: {original_df.shape[0]} строк, {original_df.shape[1]} колонок")
        logging.info(f"Файл результатов: {results_df.shape[0]} строк, {results_df.shape[1]} колонок")
        
        # Удаляем пустые столбцы из исходного файла
        original_df = original_df.loc[:, ~original_df.columns.str.contains('^Unnamed')]
        original_df = original_df.dropna(axis=1, how='all')  # Удаляем полностью пустые столбцы
        
        # Удаляем пустые столбцы из файла результатов
        results_df = results_df.loc[:, ~results_df.columns.str.contains('^Unnamed')]
        results_df = results_df.dropna(axis=1, how='all')  # Удаляем полностью пустые столбцы
        
        logging.info(f"После очистки пустых столбцов - Исходный файл: {original_df.shape[1]} колонок, Файл результатов: {results_df.shape[1]} колонок")
        
        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: ВСЕГДА объединяем по именам компаний, а не по индексам
        # Это исправляет проблему смещения данных при дубликатах и мертвых ссылках
        
        if original_df.shape[0] != results_df.shape[0]:
            logging.warning(f"Количество строк не совпадает: исходный {original_df.shape[0]}, результаты {results_df.shape[0]}")
        
        # Пытаемся объединить по имени компании (ВСЕГДА, не только при несовпадении строк)
        company_col_original = None
        company_col_results = None
        
        # Ищем колонку с именем компании в исходном файле
        for col in original_df.columns:
            if 'company' in col.lower() or 'name' in col.lower():
                company_col_original = col
                break
        if not company_col_original and len(original_df.columns) > 0:
            company_col_original = original_df.columns[0]  # Первая колонка по умолчанию
            
        # Ищем колонку с именем компании в файле результатов
        for col in results_df.columns:
            if 'company' in col.lower() or 'name' in col.lower():
                company_col_results = col
                break
        if not company_col_results and len(results_df.columns) > 0:
            company_col_results = results_df.columns[0]  # Первая колонка по умолчанию
        
        # Ищем колонку с URL в исходном файле
        url_col_original = None
        for col in original_df.columns:
            if 'url' in col.lower() or 'website' in col.lower() or 'site' in col.lower():
                url_col_original = col
                break
        
        # Ищем колонку с URL в файле результатов  
        url_col_results = None
        for col in results_df.columns:
            if 'url' in col.lower() or 'website' in col.lower() or 'site' in col.lower():
                url_col_results = col
                break
        
        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Объединяем по URL (основной ключ), а не по именам компаний
        if url_col_original and url_col_results:
            logging.info(f"Объединяем по URL: '{url_col_original}' <-> '{url_col_results}'")
            
            # Объединяем по URL - это правильный уникальный ключ
            merged_df = original_df.merge(
                results_df, 
                left_on=url_col_original, 
                right_on=url_col_results, 
                how='left',  # Сохраняем все исходные записи
                suffixes=('', '_result')
            )
            
            # Удаляем дублированную колонку URL из результатов
            if f"{url_col_results}_result" in merged_df.columns:
                merged_df = merged_df.drop(columns=[f"{url_col_results}_result"])
                
        elif company_col_original and company_col_results:
            logging.warning("URL колонки не найдены, используем fallback объединение по именам компаний")
            logging.info(f"Объединяем по именам компаний: '{company_col_original}' <-> '{company_col_results}'")
            
            # Fallback: объединяем по именам компаний
            merged_df = original_df.merge(
                results_df, 
                left_on=company_col_original, 
                right_on=company_col_results, 
                how='left',  # Сохраняем все исходные записи
                suffixes=('', '_result')
            )
            
            # Удаляем дублированную колонку имени компании из результатов
            if f"{company_col_results}_result" in merged_df.columns:
                merged_df = merged_df.drop(columns=[f"{company_col_results}_result"])
            
            logging.info(f"Объединение по именам завершено: {merged_df.shape[0]} строк, {merged_df.shape[1]} колонок")
            
            # Сохраняем объединенный файл
            os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
            if output_file_path.lower().endswith(('.xlsx', '.xls')):
                merged_df.to_excel(output_file_path, index=False)
            else:
                merged_df.to_csv(output_file_path, index=False, encoding='utf-8-sig')
            
            logging.info(f"Объединенный файл сохранен: {output_file_path}")
            return True
        else:
            logging.error("Не удалось найти колонки с именами компаний для объединения")
            # В крайнем случае используем объединение по индексам
            min_rows = min(original_df.shape[0], results_df.shape[0])
            original_df = original_df.iloc[:min_rows]
            results_df = results_df.iloc[:min_rows]
        
        # Создаем объединенный DataFrame
        # Начинаем с исходных данных
        merged_df = original_df.copy()
        
        # Добавляем колонки из результатов, избегая дублирования
        for col in results_df.columns:
            if col not in merged_df.columns:
                merged_df[col] = results_df[col]
            else:
                # Специальная обработка для predator данных
                if col == "Predator_ID" and "predator" in merged_df.columns:
                    # Если в результатах есть Predator_ID, а в исходном файле predator,
                    # то обновляем исходную колонку predator значениями из Predator_ID
                    for idx in merged_df.index:
                        if pd.isna(merged_df.loc[idx, "predator"]) or merged_df.loc[idx, "predator"] == "":
                            # Если в исходном файле predator пустой, заполняем из результатов
                            if idx < len(results_df) and not pd.isna(results_df.loc[idx, col]):
                                merged_df.loc[idx, "predator"] = results_df.loc[idx, col]
                    # Также добавляем колонку Predator_ID для полноты
                    merged_df[col] = results_df[col]
                    logging.info(f"Обновлена колонка 'predator' значениями из '{col}' и добавлена колонка '{col}'")
                else:
                    # Если колонка уже существует, добавляем с суффиксом
                    new_col_name = f"{col}_result"
                    counter = 1
                    while new_col_name in merged_df.columns:
                        new_col_name = f"{col}_result_{counter}"
                        counter += 1
                    merged_df[new_col_name] = results_df[col]
                    logging.info(f"Колонка '{col}' переименована в '{new_col_name}' для избежания дублирования")
        
        # Создаем директорию если её нет
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        
        # Сохраняем объединенный файл
        if output_file_path.lower().endswith(('.xlsx', '.xls')):
            merged_df.to_excel(output_file_path, index=False)
        else:
            merged_df.to_csv(output_file_path, index=False, encoding='utf-8-sig')
        
        logging.info(f"Объединенный файл сохранен: {output_file_path}")
        logging.info(f"Итоговый размер: {merged_df.shape[0]} строк, {merged_df.shape[1]} колонок")
        
        return True
        
    except Exception as e:
        logging.error(f"Ошибка при объединении файлов: {e}")
        return False 