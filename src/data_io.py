import pandas as pd
import os
import csv
import json
import logging

def load_and_prepare_company_names(file_path: str, col_index: int = 0) -> list[str] | None:
    """Loads the first column from Excel/CSV, handles headers, returns list of names."""
    df_loaded = None
    read_params = {"usecols": [col_index], "header": 0}
    try:
        reader = pd.read_excel if file_path.lower().endswith(('.xlsx', '.xls')) else pd.read_csv
        df_loaded = reader(file_path, **read_params)
    except (ValueError, ImportError, FileNotFoundError) as ve:
        print(f" Initial read failed for {file_path}, trying header=None: {ve}")
        read_params["header"] = None
        try: df_loaded = reader(file_path, **read_params)
        except Exception as read_err_no_header: print(f" Error reading {file_path} even with header=None: {read_err_no_header}"); return None
    except Exception as read_err: print(f" Error reading file {file_path}: {read_err}"); return None

    if df_loaded is not None and not df_loaded.empty:
        company_names = df_loaded.iloc[:, 0].astype(str).str.strip().tolist()
        valid_names = [name for name in company_names if name and name.lower() not in ['nan', '']]
        if valid_names: return valid_names
        else: print(f" No valid names in first column of {file_path}."); return None
    else: print(f" Could not load data from first column of {file_path}."); return None

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

# === Session Metadata Handling (NEW) ===
SESSIONS_METADATA_FILE = "sessions_metadata.json"
SESSIONS_DIR = os.path.join("output", "sessions")

def ensure_sessions_dir_exists():
    """Ensures the sessions directory exists."""
    if not os.path.exists(SESSIONS_DIR):
        try:
            os.makedirs(SESSIONS_DIR)
            logging.info(f"Created sessions directory: {SESSIONS_DIR}")
        except OSError as e:
            logging.error(f"Could not create sessions directory {SESSIONS_DIR}. Error: {e}")
            # Depending on how critical this is, you might raise the exception
            # raise

def load_session_metadata() -> list[dict]:
    """Loads session metadata from the JSON file."""
    ensure_sessions_dir_exists() # Ensure parent dir exists first
    if not os.path.exists(SESSIONS_METADATA_FILE):
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
def save_results_csv(results: list[dict], output_file_path: str, append_mode: bool = False, fieldnames: list[str] | None = None):
    """
    Saves a list of dictionaries to a CSV file.
    Can append to an existing file or create a new one.
    """
    if not results:
        print(f"No results to save to {output_file_path}")
        return

    # Определяем заголовки (поля)
    # Если fieldnames не предоставлены, берем ключи из первой записи
    # Важно: при дозаписи все словари должны иметь одинаковый набор ключей, соответствующий исходным заголовкам
    if not fieldnames:
        fieldnames = list(results[0].keys()) # ['name', 'homepage', 'linkedin', 'description', 'llm_summary', ...]

    file_exists = os.path.isfile(output_file_path)
    
    # Определяем, нужно ли писать заголовки
    # Заголовки пишутся, если файл не существует ИЛИ если это не режим дозаписи (т.е. перезапись)
    write_header = not file_exists or not append_mode

    try:
        # Используем 'a' (append) если append_mode и файл существует, иначе 'w' (write)
        mode = 'a' if append_mode and file_exists else 'w'
        
        with open(output_file_path, mode, newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore') # ignore extra fields in dict
            
            if write_header:
                writer.writeheader()
            
            for row_data in results:
                writer.writerow(row_data)
        
        action = "Appended" if mode == 'a' else "Saved"
        print(f"{action} {len(results)} result(s) to {output_file_path}")

    except IOError as e:
        print(f"Error writing to CSV file {output_file_path}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during CSV writing to {output_file_path}: {e}")
 