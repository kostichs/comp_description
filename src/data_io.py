import pandas as pd
import os
import csv
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple

# Setup logging
logger = logging.getLogger(__name__)

# Determine Project Root (assuming this file is in src/)
PROJECT_ROOT = Path(__file__).parent.parent 

def load_and_prepare_company_names(file_path: str | Path, col_index: int = 0) -> Union[List[str], List[Tuple[str, str]]] | None:
    """
    Loads company data from Excel/CSV.
    
    Args:
        file_path: Path to the input file
        col_index: Index of the first column to load (default 0)
    
    Returns:
        If file has only one column: List of company names
        If file has two columns: List of tuples (company_name, second_column_value)
        None if file could not be loaded
    """
    file_path_str = str(file_path)
    df_loaded = None
    
    try:
        # Определяем формат файла и загружаем его
        reader = pd.read_excel if file_path_str.lower().endswith(('.xlsx', '.xls')) else pd.read_csv
        
        # Сначала попробуем загрузить весь файл, чтобы определить количество столбцов
        df_loaded = reader(file_path_str)
        
        # Проверяем, есть ли два столбца
        has_two_columns = df_loaded.shape[1] >= 2
        
        # Если есть два столбца, загружаем оба
        if has_two_columns:
            logging.info(f"Detected two or more columns in {file_path_str}, using first two columns")
            # Используем первые два столбца
            df_loaded = reader(file_path_str, usecols=[0, 1], header=0)
        else:
            # Если только один столбец, используем только первый
            logging.info(f"Detected only one column in {file_path_str}")
            df_loaded = reader(file_path_str, usecols=[col_index], header=0)
            
    except (ValueError, ImportError, FileNotFoundError) as ve:
        logging.warning(f"Initial read failed for {file_path_str}, trying header=None: {ve}")
        try:
            # Пробуем без заголовка
            df_loaded = reader(file_path_str, header=None)
            
            # Проверяем, есть ли два столбца
            has_two_columns = df_loaded.shape[1] >= 2
            
            # Если есть два столбца, загружаем оба
            if has_two_columns:
                logging.info(f"Detected two or more columns in {file_path_str} (without header), using first two columns")
                df_loaded = reader(file_path_str, usecols=[0, 1], header=None)
            else:
                logging.info(f"Detected only one column in {file_path_str} (without header)")
                df_loaded = reader(file_path_str, usecols=[col_index], header=None)
                
        except Exception as read_err_no_header:
            logging.error(f"Error reading {file_path_str} even with header=None: {read_err_no_header}")
            return None
    except Exception as read_err:
        logging.error(f"Error reading file {file_path_str}: {read_err}")
        return None

    if df_loaded is not None and not df_loaded.empty:
        # Проверяем, сколько столбцов в датафрейме
        if df_loaded.shape[1] >= 2:
            # Если есть два или больше столбцов, возвращаем кортежи (company_name, second_column_value)
            company_names = df_loaded.iloc[:, 0].astype(str).str.strip()
            second_column = df_loaded.iloc[:, 1].astype(str).str.strip()
            
            # Создаем список кортежей, исключая строки с пустыми значениями в первом столбце
            result = []
            for name, second_value in zip(company_names, second_column):
                if name and name.lower() not in ['nan', '']:
                    result.append((name, second_value))
            
            if result:
                logging.info(f"Loaded {len(result)} companies with second column data from {file_path_str}")
                return result
            else:
                logging.warning(f"No valid names in first column of {file_path_str}.")
                return None
        else:
            # Если только один столбец, возвращаем список строк
            company_names = df_loaded.iloc[:, 0].astype(str).str.strip().tolist()
            valid_names = [name for name in company_names if name and name.lower() not in ['nan', '']]
            if valid_names:
                logging.info(f"Loaded {len(valid_names)} companies from {file_path_str}")
                return valid_names
            else:
                logging.warning(f"No valid names in first column of {file_path_str}.")
                return None
    else:
        logging.warning(f"Could not load data from {file_path_str}.")
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
        logging.warning(f"'{SESSIONS_METADATA_FILE}' not found. Initializing with empty list.")
        return []
    try:
        with open(SESSIONS_METADATA_FILE, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
            if not isinstance(metadata, list):
                 logging.error(f"Invalid format in '{SESSIONS_METADATA_FILE}'. Expected a list. Returning empty list.")
                 return []
            return metadata
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from '{SESSIONS_METADATA_FILE}'. Returning empty list.")
        return []
    except Exception as e:
        logging.error(f"Error loading session metadata: {e}")
        return []

def save_session_metadata(metadata: list[dict]):
    """Saves session metadata list to the JSON file."""
    ensure_sessions_dir_exists()
    try:
        with open(SESSIONS_METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        logging.debug(f"Saved session metadata to {SESSIONS_METADATA_FILE}")
    except Exception as e:
        logging.error(f"Error saving session metadata: {e}")

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
        fieldnames = ["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp"]
    
    # Determine mode based on append_mode and file existence
    mode = 'a' if append_mode and os.path.exists(output_path) else 'w'
    
    # Write to CSV
    with open(output_path, mode, newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        # Write header only if writing a new file
        if mode == 'w':
            writer.writeheader()
        
        for result in results:
            # Ensure all expected fields are present
            row = {field: result.get(field, '') for field in fieldnames}
            writer.writerow(row)
    
    logging.info(f"Saved {len(results)} result(s) to {output_path}")

def save_results_json(results: List[Dict[str, Any]], output_path: str, append_mode: bool = False):
    """
    Сохраняет структурированные данные о компаниях в JSON файл.
    
    Args:
        results: Список результатов с данными компаний
        output_path: Путь для сохранения JSON файла
        append_mode: Режим добавления в существующий файл вместо перезаписи
    """
    # Создаем директорию, если она не существует
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Подготавливаем структурированные данные
    structured_data = []
    
    for result in results:
        # Если в результате есть structured_data, используем их
        if result.get("structured_data") and isinstance(result.get("structured_data"), dict):
            structured_result = result["structured_data"]
        else:
            # Иначе создаем структуру из доступных полей
            structured_result = {
                "company_name": result.get("name", ""),
                "founding_year": result.get("founding_year", None),
                "headquarters_location": result.get("headquarters_location", None),
                "industry": result.get("industry", None),
                "main_products_services": result.get("main_products_services", None),
                "employees_count": result.get("employees_count", None),
                "description": result.get("description", ""),
                "homepage": result.get("homepage", None),
                "linkedin": result.get("linkedin", None),
                "timestamp": result.get("timestamp", None)
            }
        
        structured_data.append(structured_result)
    
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
    final_data = existing_data + structured_data
    
    # Сохраняем в JSON
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved {len(structured_data)} structured result(s) to {output_path}")
        return True
    except Exception as e:
        logging.error(f"Error saving structured data to {output_path}: {e}")
        return False

def save_structured_data_incrementally(result: Dict[str, Any], output_path: str):
    """
    Сохраняет структурированные данные об одной компании в JSON файл инкрементально.
    
    Args:
        result: Результат с данными одной компании
        output_path: Путь для сохранения JSON файла
    """
    # Создаем директорию, если она не существует
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Подготавливаем структурированные данные
    if result.get("structured_data") and isinstance(result.get("structured_data"), dict):
        structured_result = result["structured_data"]
    else:
        # Иначе создаем структуру из доступных полей
        structured_result = {
            "company_name": result.get("name", ""),
            "founding_year": result.get("founding_year", None),
            "headquarters_location": result.get("headquarters_location", None),
            "industry": result.get("industry", None),
            "main_products_services": result.get("main_products_services", None),
            "employees_count": result.get("employees_count", None),
            "description": result.get("description", ""),
            "homepage": result.get("homepage", None),
            "linkedin": result.get("linkedin", None),
            "timestamp": result.get("timestamp", None)
        }
    
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
    existing_data.append(structured_result)
    
    # Сохраняем в JSON
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
        logging.info(f"Added 1 structured result to {output_path}")
        return True
    except Exception as e:
        logging.error(f"Error saving structured data to {output_path}: {e}")
        return False 