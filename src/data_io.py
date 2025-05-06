import pandas as pd
import os

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

def save_results_csv(data: list[dict], output_file_path: str) -> None:
    """Saves the processed data to a CSV file."""
    if not data: print(f"No data to save for {output_file_path}."); return
    # Determine columns dynamically to handle variable JSON output
    all_keys = set()
    for row in data:
        all_keys.update(row.keys())
    # Optional: Define a preferred column order if needed
    # preferred_order = ['name', 'homepage', 'linkedin', ...] 
    # columns = [col for col in preferred_order if col in all_keys] + sorted([col for col in all_keys if col not in preferred_order])
    columns = sorted(list(all_keys)) # Simple sorted list for now
    
    df = pd.DataFrame(data, columns=columns)
    try:
        output_dir = os.path.dirname(output_file_path)
        if output_dir and not os.path.exists(output_dir): os.makedirs(output_dir); print(f"Created output dir: {output_dir}")
        df.to_csv(output_file_path, index=False, encoding='utf-8')
        print(f"Results saved to {output_file_path}")
    except Exception as e: print(f"Error saving CSV to {output_file_path}: {e}") 