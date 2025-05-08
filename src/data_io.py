import pandas as pd
import os
import csv
import json
import logging
from pathlib import Path

# Determine Project Root (assuming this file is in src/)
PROJECT_ROOT = Path(__file__).parent.parent 

def load_and_prepare_company_names(file_path: str | Path, col_index: int = 0) -> list[str] | None:
    """Loads the first column from Excel/CSV, handles headers, returns list of names."""
    file_path_str = str(file_path)
    df_loaded = None
    read_params = {"usecols": [col_index], "header": 0}
    try:
        reader = pd.read_excel if file_path_str.lower().endswith(('.xlsx', '.xls')) else pd.read_csv
        df_loaded = reader(file_path_str, **read_params)
    except (ValueError, ImportError, FileNotFoundError) as ve:
        logging.warning(f" Initial read failed for {file_path_str}, trying header=None: {ve}")
        read_params["header"] = None
        try: df_loaded = reader(file_path_str, **read_params)
        except Exception as read_err_no_header: logging.error(f" Error reading {file_path_str} even with header=None: {read_err_no_header}"); return None
    except Exception as read_err: logging.error(f" Error reading file {file_path_str}: {read_err}"); return None

    if df_loaded is not None and not df_loaded.empty:
        company_names = df_loaded.iloc[:, 0].astype(str).str.strip().tolist()
        valid_names = [name for name in company_names if name and name.lower() not in ['nan', '']]
        if valid_names: return valid_names
        else: logging.warning(f" No valid names in first column of {file_path_str}."); return None
    else: logging.warning(f" Could not load data from first column of {file_path_str}."); return None

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
def save_results_csv(results: list[dict], output_file_path: str | Path, append_mode: bool = False, fieldnames: list[str] | None = None):
    # Convert Path object to string if necessary for csv writer compatibility or os.path
    output_file_path_str = str(output_file_path)
    
    if not results and not append_mode: # Handle case where we just want to write header
        # Ensure directory exists even if results are empty
        output_dir = os.path.dirname(output_file_path_str)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                logging.info(f"Created directory for CSV output: {output_dir}")
            except OSError as e:
                 logging.error(f"Could not create directory {output_dir} for CSV. Error: {e}")
                 return # Cannot proceed if directory creation fails
        # If results list is empty but we need header
        if not fieldnames:
            logging.warning(f"Cannot write header for {output_file_path_str}: fieldnames not provided and results are empty.")
            return
        try:
            with open(output_file_path_str, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
            logging.info(f"Created empty CSV with header at {output_file_path_str}")
        except IOError as e:
             logging.error(f"Error writing header to CSV file {output_file_path_str}: {e}")
        return # Exit after writing header

    if not results:
        # If appending and results is empty, do nothing
        # If writing (not appending) and results is empty, handled above.
        logging.debug(f"No results to save/append to {output_file_path_str}")
        return
        
    # Determine fieldnames if not provided
    if not fieldnames:
        fieldnames = list(results[0].keys()) 

    file_exists = os.path.isfile(output_file_path_str)
    write_header = not file_exists or not append_mode
    mode = 'a' if append_mode and file_exists else 'w'

    try:
        output_dir = os.path.dirname(output_file_path_str)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logging.info(f"Created directory for CSV output: {output_dir}")
            
        with open(output_file_path_str, mode, newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
            if write_header:
                writer.writeheader()
            writer.writerows(results) # Use writerows for efficiency
        
        action = "Appended" if mode == 'a' else "Saved"
        logging.info(f"{action} {len(results)} result(s) to {output_file_path_str}") # Changed print to logging.info

    except IOError as e:
        logging.error(f"Error writing to CSV file {output_file_path_str}: {e}") # Changed print to logging.error
    except Exception as e:
        logging.error(f"An unexpected error occurred during CSV writing to {output_file_path_str}: {e}") # Changed print to logging.error
 