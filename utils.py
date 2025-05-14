import pandas as pd
from pathlib import Path
from typing import List, Optional

def load_company_names(file_path: str | Path, col_index: int = 0) -> Optional[List[str]]:
    """
    Загружает список названий компаний из Excel/CSV файла.
    
    Args:
        file_path: Путь к файлу
        col_index: Индекс столбца с названиями компаний (по умолчанию 0)
        
    Returns:
        Optional[List[str]]: Список названий компаний или None в случае ошибки
    """
    file_path_str = str(file_path)
    df_loaded = None
    read_params = {"usecols": [col_index], "header": 0}
    
    try:
        # Определяем функцию для чтения в зависимости от типа файла
        reader = pd.read_excel if file_path_str.lower().endswith(('.xlsx', '.xls')) else pd.read_csv
        df_loaded = reader(file_path_str, **read_params)
    except (ValueError, ImportError, FileNotFoundError) as ve:
        print(f"Ошибка при чтении {file_path_str} с header=0: {ve}")
        # Пробуем без заголовка
        read_params["header"] = None
        try: 
            df_loaded = reader(file_path_str, **read_params)
        except Exception as read_err_no_header: 
            print(f"Ошибка при чтении {file_path_str} даже без заголовка: {read_err_no_header}")
            return None
    except Exception as read_err: 
        print(f"Ошибка при чтении файла {file_path_str}: {read_err}")
        return None

    # Проверяем, успешно ли загружен DataFrame
    if df_loaded is not None and not df_loaded.empty:
        # Извлекаем названия компаний, приводим к строкам и удаляем пробелы
        company_names = df_loaded.iloc[:, 0].astype(str).str.strip().tolist()
        # Фильтруем невалидные значения
        valid_names = [name for name in company_names if name and name.lower() not in ['nan', '']]
        
        if valid_names: 
            return valid_names
        else: 
            print(f"Нет валидных названий в первом столбце {file_path_str}.")
            return None
    else: 
        print(f"Не удалось загрузить данные из первого столбца {file_path_str}.")
        return None

def create_output_dirs() -> None:
    """
    Создает необходимые директории для выходных файлов.
    """
    Path("output").mkdir(exist_ok=True)
    Path("input").mkdir(exist_ok=True) 