"""
Модуль для загрузки данных из файлов
"""

import os
import glob
import pandas as pd
from src.utils.config import DATA_DIR, COMPANIES_LIMIT, CRITERIA_DIR, CRITERIA_TYPE, INDUSTRY_MAPPING
from src.utils.logging import log_info, log_error, log_debug
from src.data.encodings import load_csv_with_encoding

def load_file_smart(file_path):
    """Загружает файл автоматически определяя тип (CSV или Excel) с правильным парсингом"""
    file_ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if file_ext in ['.csv']:
            log_debug(f"📋 Загружаем CSV файл: {os.path.basename(file_path)}")
            # Используем правильные параметры для CSV с многострочными полями
            df = pd.read_csv(file_path, quoting=1, encoding='utf-8', on_bad_lines='skip')
            
            # УДАЛЕНИЕ НЕЖЕЛАТЕЛЬНЫХ КОЛОНОК: убираем validation колонки
            columns_to_remove = ['validation_status', 'validation_warning']
            columns_removed = []
            for col in columns_to_remove:
                if col in df.columns:
                    df = df.drop(columns=[col])
                    columns_removed.append(col)
            
            if columns_removed:
                log_info(f"🗑️  Удалены колонки: {', '.join(columns_removed)}")
            
            # ФИЛЬТРАЦИЯ ПУСТЫХ СТРОК: удаляем строки где все основные колонки пустые
            main_columns = ['Company_Name', 'Description']  # Основные колонки для проверки
            existing_columns = [col for col in main_columns if col in df.columns]
            
            if existing_columns:
                # Удаляем строки где ВСЕ основные колонки пустые (NaN, None, пустая строка)
                df_before = len(df)
                df = df.dropna(subset=existing_columns, how='all')  # Удаляем строки где ВСЕ колонки NaN
                df = df[df[existing_columns].ne('').any(axis=1)]   # Удаляем строки где ВСЕ колонки пустые строки
                df_after = len(df)
                
                filtered_count = df_before - df_after
                if filtered_count > 0:
                    log_info(f"🧹 Отфильтровано пустых строк: {filtered_count} из {df_before}")
                
            return df
        elif file_ext in ['.xlsx', '.xls']:
            log_debug(f"📊 Загружаем Excel файл: {os.path.basename(file_path)}")
            df = pd.read_excel(file_path)
            
            # УДАЛЕНИЕ НЕЖЕЛАТЕЛЬНЫХ КОЛОНОК: убираем validation колонки
            columns_to_remove = ['validation_status', 'validation_warning']
            columns_removed = []
            for col in columns_to_remove:
                if col in df.columns:
                    df = df.drop(columns=[col])
                    columns_removed.append(col)
            
            if columns_removed:
                log_info(f"🗑️  Удалены колонки: {', '.join(columns_removed)}")
            
            # Аналогичная фильтрация для Excel
            main_columns = ['Company_Name', 'Description']
            existing_columns = [col for col in main_columns if col in df.columns]
            
            if existing_columns:
                df_before = len(df)
                df = df.dropna(subset=existing_columns, how='all')
                df = df[df[existing_columns].ne('').any(axis=1)]
                df_after = len(df)
                
                filtered_count = df_before - df_after
                if filtered_count > 0:
                    log_info(f"🧹 Отфильтровано пустых строк: {filtered_count} из {df_before}")
            
            return df
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {file_ext}")
    except Exception as e:
        log_error(f"❌ Ошибка загрузки файла {file_path}: {e}")
        raise

def load_companies_data(file_path=None):
    """Load companies data - either from specific file or automatically find first CSV"""
    if file_path:
        log_info(f"📊 Загружаем данные компаний из указанного файла: {file_path}")
        companies_df = load_file_smart(file_path)
    else:
        # Автоматически находим первый CSV файл в папке data
        csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
        if not csv_files:
            raise FileNotFoundError(f"❌ CSV файлы не найдены в папке: {DATA_DIR}")
        
        first_csv = os.path.join(DATA_DIR, csv_files[0])
        log_info(f"📊 Автоматически выбран файл: {first_csv}")
        companies_df = load_file_smart(first_csv)
    
    if COMPANIES_LIMIT > 0:
        log_info(f"⚠️  ТЕСТОВЫЙ РЕЖИМ: Ограничиваем до {COMPANIES_LIMIT} компаний")
        companies_df = companies_df.head(COMPANIES_LIMIT)
    
    log_info(f"✅ Загружено компаний: {len(companies_df)}")
    return companies_df

def load_all_companies_from_data_folder():
    """Load and combine all CSV and Excel company files from data/ directory"""
    data_dir = DATA_DIR  # Используем папку data из конфигурации
    
    if not os.path.exists(data_dir):
        raise FileNotFoundError(f"❌ Папка data не найдена: {data_dir}")
    
    # Find all CSV and Excel files in data directory
    company_files = []
    company_files.extend(glob.glob(os.path.join(data_dir, "*.csv")))
    company_files.extend(glob.glob(os.path.join(data_dir, "*.xlsx")))
    company_files.extend(glob.glob(os.path.join(data_dir, "*.xls")))
    
    if not company_files:
        raise FileNotFoundError(f"❌ Не найдено CSV/Excel файлов в папке: {data_dir}")
    
    log_info(f"📁 Найдено файлов компаний: {len(company_files)}")
    for file_path in company_files:
        file_ext = os.path.splitext(file_path)[1].lower()
        log_info(f"   - {os.path.basename(file_path)} ({file_ext.upper()})")
    
    all_companies = []
    
    for file_path in company_files:
        filename = os.path.basename(file_path)
        file_ext = os.path.splitext(file_path)[1].lower()
        log_info(f"📋 Загружаем компании из: {filename} ({file_ext.upper()})")
        
        try:
            df = load_file_smart(file_path)
            log_info(f"✅ Загружено из {filename}: {len(df)} компаний")
            all_companies.append(df)
            
        except Exception as e:
            log_error(f"❌ Ошибка загрузки {filename}: {e}")
            continue
    
    if not all_companies:
        raise ValueError("❌ Не удалось загрузить ни одного файла компаний")
    
    # Combine all companies into single DataFrame
    combined_companies = pd.concat(all_companies, ignore_index=True)
    
    if COMPANIES_LIMIT > 0:
        log_info(f"⚠️  ТЕСТОВЫЙ РЕЖИМ: Ограничиваем до {COMPANIES_LIMIT} компаний")
        combined_companies = combined_companies.head(COMPANIES_LIMIT)
    
    log_info(f"🎯 Объединено компаний: {len(combined_companies)}")
    return combined_companies

def load_all_criteria_files():
    """Load and combine all criteria files from criteria/ directory"""
    criteria_dir = CRITERIA_DIR
    
    if not os.path.exists(criteria_dir):
        raise FileNotFoundError(f"❌ Папка criteria не найдена: {criteria_dir}")
    
    # Find all CSV files in criteria directory
    criteria_files = glob.glob(os.path.join(criteria_dir, "*.csv"))
    
    if not criteria_files:
        raise FileNotFoundError(f"❌ Не найдено файлов критериев в папке: {criteria_dir}")
    
    log_info(f"📁 Найдено файлов критериев: {len(criteria_files)}")
    
    all_criteria = []
    
    for file_path in criteria_files:
        filename = os.path.basename(file_path)
        log_info(f"📋 Загружаем критерии из: {filename}")
        
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            
            # Validate required columns
            required_columns = ['Product', 'Target Audience', 'Criteria Type', 'Criteria']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                log_error(f"❌ В файле {filename} отсутствуют колонки: {missing_columns}")
                continue
            
            log_info(f"✅ Загружено из {filename}: {len(df)} критериев")
            all_criteria.append(df)
            
        except Exception as e:
            log_error(f"❌ Ошибка загрузки {filename}: {e}")
            continue
    
    if not all_criteria:
        raise ValueError("❌ Не удалось загрузить ни одного файла критериев")
    
    # Combine all criteria into single DataFrame
    combined_criteria = pd.concat(all_criteria, ignore_index=True)
    
    log_info(f"🎯 Объединено критериев: {len(combined_criteria)}")
    
    # Show products and types summary
    products = combined_criteria['Product'].unique()
    criteria_types = combined_criteria['Criteria Type'].unique()
    
    log_info(f"📊 Найдены продукты: {', '.join(products)}")
    log_info(f"📊 Типы критериев: {', '.join(criteria_types)}")
    
    return combined_criteria

def load_data(companies_file=None, load_all_companies=False):
    """Load all data files - updated for ALL PRODUCTS processing
    
    Args:
        companies_file: путь к конкретному файлу компаний (опционально)
        load_all_companies: если True, загружает все CSV файлы из папки data/
    """
    log_info(f"📋 Загружаем данные для ВСЕХ продуктов")
    
    try:
        # Load companies data based on parameters
        if load_all_companies:
            log_info("📊 Загружаем ВСЕ файлы компаний из папки data/")
            companies_df = load_all_companies_from_data_folder()
        elif companies_file:
            log_info(f"📊 Загружаем компании из указанного файла: {companies_file}")
            companies_df = load_companies_data(companies_file)
        else:
            log_info(f"📊 Автоматически находим CSV файл в папке: {DATA_DIR}")
            companies_df = load_companies_data()
        
        log_info(f"✅ Итого загружено компаний: {len(companies_df)}")
        
        # Load all criteria files automatically
        df_criteria = load_all_criteria_files()
        
        # НОВАЯ ЛОГИКА: Собираем все General критерии из всех файлов
        log_info("🌐 Собираем все General критерии из всех файлов критериев...")
        all_general_criteria = df_criteria[df_criteria["Criteria Type"] == "General"]["Criteria"].dropna().unique().tolist()
        log_info(f"✅ Найдено уникальных General критериев: {len(all_general_criteria)}")
        for i, criteria in enumerate(all_general_criteria, 1):
            log_info(f"   {i}. {criteria}")
        
        # ИСПРАВЛЕНО: Используем ВСЕ критерии для ВСЕХ продуктов
        products = df_criteria['Product'].unique()
        log_info(f"🏭 Будем обрабатывать компании для ВСЕХ продуктов: {', '.join(products)}")
        
        # Создаем структуру данных для всех продуктов
        all_products_data = {}
        
        for product in products:
            product_criteria = df_criteria[df_criteria["Product"] == product]
            log_info(f"📋 Найдено критериев для продукта {product}: {len(product_criteria)}")
            
            # Extract qualification questions FOR THIS PRODUCT
            qualification_df = product_criteria[product_criteria["Criteria Type"] == "Qualification"].dropna(subset=["Criteria", "Target Audience"])
            qualification_questions = {
                row["Target Audience"]: row["Criteria"]
                for _, row in qualification_df.iterrows()
            }
            log_info(f"✅ Загружено квалификационных вопросов для {product}: {len(qualification_questions)}")
            
            # Load mandatory criteria FOR THIS PRODUCT
            mandatory_df = product_criteria[product_criteria["Criteria Type"] == "Mandatory"].dropna(subset=["Criteria", "Target Audience"])
            log_info(f"✅ Загружено обязательных критериев для {product}: {len(mandatory_df)}")
            
            # Load NTH criteria FOR THIS PRODUCT
            nth_df = product_criteria[product_criteria["Criteria Type"] == "NTH"].dropna(subset=["Criteria", "Target Audience"])
            log_info(f"✅ Загружено NTH критериев для {product}: {len(nth_df)}")
            
            all_products_data[product] = {
                "qualification_questions": qualification_questions,
                "mandatory_df": mandatory_df,
                "nth_df": nth_df
            }
        
        log_info("🚀 Все данные успешно загружены")
        log_info(f"General критерии будут применяться ко всем компаниям")
        log_info(f"🎯 Критерии для продуктов: {', '.join(products)}")
        
        return {
            "companies": companies_df,
            "general_criteria": all_general_criteria,  # ВСЕ General из всех файлов
            "products_data": all_products_data,  # Данные для ВСЕХ продуктов
            "products": list(products)  # Список всех продуктов
        }
        
    except FileNotFoundError as e:
        log_error(f"❌ Файл не найден: {e}")
        raise
    except Exception as e:
        log_error(f"❌ Ошибка загрузки данных: {e}")
        raise 