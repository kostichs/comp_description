import os
import json
import pandas as pd
import csv
import chardet
import glob
from config import INPUT_PATH, COMPANIES_LIMIT, CSV_OUTPUT_PATH, OUTPUT_DIR
from logger_config import log_info, log_error, log_debug

def detect_encoding(file_path):
    """Автоматически определяет кодировку файла"""
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)  # Читаем первые 10KB для определения
            result = chardet.detect(raw_data)
            encoding = result['encoding']
            confidence = result['confidence']
            log_debug(f"📝 Определена кодировка {file_path}: {encoding} (уверенность: {confidence:.2f})")
            return encoding
    except Exception as e:
        log_error(f"❌ Ошибка определения кодировки для {file_path}: {e}")
        return 'utf-8'

def load_csv_with_encoding(file_path):
    """Загружает CSV с автоматическим определением кодировки"""
    # Список кодировок для попыток
    encodings_to_try = [
        detect_encoding(file_path),  # Автоопределение
        'utf-8-sig',                 # UTF-8 с BOM
        'utf-8',                     # Обычный UTF-8
        'windows-1251',              # Кириллица Windows
        'cp1252',                    # Windows Western
        'iso-8859-1',                # Latin-1
        'latin1'                     # Fallback
    ]
    
    # Убираем дубликаты
    encodings_to_try = list(dict.fromkeys(encodings_to_try))
    
    for encoding in encodings_to_try:
        if not encoding:
            continue
            
        try:
            log_debug(f"🔄 Пробуем загрузить {file_path} с кодировкой: {encoding}")
            df = pd.read_csv(file_path, encoding=encoding)
            log_info(f"✅ Файл загружен с кодировкой: {encoding}")
            return df
        except (UnicodeDecodeError, UnicodeError) as e:
            log_debug(f"⚠️  Не удалось с кодировкой {encoding}: {e}")
            continue
        except Exception as e:
            log_error(f"❌ Ошибка загрузки файла {file_path}: {e}")
            raise
    
    # Если ничего не помогло
    raise UnicodeError(f"Не удалось определить кодировку для файла: {file_path}")

def load_companies_data():
    """Load only companies data for processing"""
    from config import INPUT_PATH, COMPANIES_LIMIT
    
    log_info(f"📊 Загружаем данные компаний: {INPUT_PATH}")
    
    companies_df = load_csv_with_encoding(INPUT_PATH)
    
    if COMPANIES_LIMIT > 0:
        log_info(f"⚠️  ТЕСТОВЫЙ РЕЖИМ: Ограничиваем до {COMPANIES_LIMIT} компаний")
        companies_df = companies_df.head(COMPANIES_LIMIT)
    
    log_info(f"✅ Загружено компаний: {len(companies_df)}")
    return companies_df

def load_all_criteria_files():
    """Load and combine all criteria files from criteria/ directory"""
    criteria_dir = os.path.join(os.path.dirname(__file__), "criteria")
    
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
            df = load_csv_with_encoding(file_path)
            
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

def load_data():
    """Load all data files - updated for automatic criteria loading with global general criteria"""
    from config import CRITERIA_TYPE, INPUT_PATH, COMPANIES_LIMIT, INDUSTRY_MAPPING
    
    log_info(f"📋 Загружаем данные для: {CRITERIA_TYPE}")
    
    # Get product name for filtering
    product_name = INDUSTRY_MAPPING.get(CRITERIA_TYPE, CRITERIA_TYPE)
    log_info(f"🏭 Фильтруем критерии по продукту: {product_name}")
    
    try:
        # Load companies data
        log_info(f"📊 Загружаем компании: {INPUT_PATH}")
        companies_df = load_csv_with_encoding(INPUT_PATH)
        
        if COMPANIES_LIMIT > 0:
            log_info(f"⚠️  ТЕСТОВЫЙ РЕЖИМ: Ограничиваем до {COMPANIES_LIMIT} компаний")
            companies_df = companies_df.head(COMPANIES_LIMIT)
        
        log_info(f"✅ Загружено компаний: {len(companies_df)}")
        
        # Load all criteria files automatically
        df_criteria = load_all_criteria_files()
        
        # НОВАЯ ЛОГИКА: Собираем все General критерии из всех файлов
        log_info("🌐 Собираем все General критерии из всех файлов критериев...")
        all_general_criteria = df_criteria[df_criteria["Criteria Type"] == "General"]["Criteria"].dropna().unique().tolist()
        log_info(f"✅ Найдено уникальных General критериев: {len(all_general_criteria)}")
        for i, criteria in enumerate(all_general_criteria, 1):
            log_info(f"   {i}. {criteria}")
        
        # Filter by product for other criteria types (NOT for General!)
        product_criteria = df_criteria[df_criteria["Product"] == product_name]
        log_info(f"📋 Найдено критериев для продукта {product_name}: {len(product_criteria)}")
        
        if len(product_criteria) == 0:
            log_error(f"❌ Не найдено критериев для продукта: {product_name}")
            log_info(f"💡 Доступные продукты: {', '.join(df_criteria['Product'].unique())}")
            raise ValueError(f"Нет критериев для продукта: {product_name}")
        
        # Extract qualification questions FOR THIS PRODUCT
        qualification_df = product_criteria[product_criteria["Criteria Type"] == "Qualification"].dropna(subset=["Criteria", "Target Audience"])
        qualification_questions = {
            row["Target Audience"]: row["Criteria"]
            for _, row in qualification_df.iterrows()
        }
        log_info(f"✅ Загружено квалификационных вопросов для {product_name}: {len(qualification_questions)}")
        for audience in qualification_questions:
            log_info(f"   - {audience}")
        
        # Load mandatory criteria FOR THIS PRODUCT
        mandatory_df = product_criteria[product_criteria["Criteria Type"] == "Mandatory"].dropna(subset=["Criteria", "Target Audience"])
        log_info(f"✅ Загружено обязательных критериев для {product_name}: {len(mandatory_df)}")
        
        # Load NTH criteria FOR THIS PRODUCT
        nth_df = product_criteria[product_criteria["Criteria Type"] == "NTH"].dropna(subset=["Criteria", "Target Audience"])
        log_info(f"✅ Загружено NTH критериев для {product_name}: {len(nth_df)}")
        
        log_info("🚀 Все данные успешно загружены")
        log_info(f"🌐 General критерии будут применяться ко всем компаниям")
        log_info(f"🎯 Остальные критерии только для продукта: {product_name}")
        
        return {
            "companies": companies_df,
            "general_criteria": all_general_criteria,  # ВСЕ General из всех файлов
            "qualification_questions": qualification_questions,
            "mandatory_df": mandatory_df,
            "nth_df": nth_df,
            "product": CRITERIA_TYPE
        }
        
    except FileNotFoundError as e:
        log_error(f"❌ Файл не найден: {e}")
        raise
    except Exception as e:
        log_error(f"❌ Ошибка загрузки данных: {e}")
        raise

def save_results(results, product, timestamp=None):
    """Save results to both JSON and CSV files"""
    if not timestamp:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create output filenames
    json_filename = f"analysis_results_{product}_{timestamp}.json"
    csv_filename = f"analysis_results_{product}_{timestamp}.csv"
    
    json_path = os.path.join(OUTPUT_DIR, json_filename)
    csv_path = os.path.join(OUTPUT_DIR, csv_filename)
    
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Save to JSON with pretty formatting
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    log_info(f"💾 JSON результаты сохранены: {json_path}")
    
    # Convert to CSV format
    csv_data = []
    for result in results:
        # Flatten nested structures for CSV
        flat_result = flatten_result_for_csv(result)
        csv_data.append(flat_result)
    
    # Save to CSV
    if csv_data:
        df_csv = pd.DataFrame(csv_data)
        df_csv.to_csv(csv_path, index=False, encoding='utf-8-sig')
        log_info(f"💾 CSV результаты сохранены: {csv_path}")
        log_info(f"📊 Обработано записей: {len(results)}")
        log_info(f"📋 Колонок в CSV: {len(df_csv.columns)}")
    
    return json_path, csv_path

def flatten_result_for_csv(result):
    """Converts nested JSON result to flat dictionary for CSV"""
    flat = {}
    
    # Basic company info
    flat["Company_Name"] = result.get("Company_Name", "")
    flat["Official_Website"] = result.get("Official_Website", "")
    flat["Description"] = result.get("Description", "")
    
    # Status fields
    flat["Global_Criteria_Status"] = result.get("Global_Criteria_Status", "")
    flat["Final_Status"] = result.get("Final_Status", "")
    flat["Qualified_Audiences"] = ", ".join(result.get("Qualified_Audiences", []))
    
    # Qualification results
    for key, value in result.items():
        if key.startswith("Qualification_"):
            flat[key] = value
    
    # Status for each audience
    for key, value in result.items():
        if key.startswith("Status_"):
            flat[key] = value
    
    # Mandatory results
    for key, value in result.items():
        if key.startswith("Mandatory_"):
            flat[key] = value
    
    # NTH results and scores
    for key, value in result.items():
        if key.startswith("NTH_"):
            flat[key] = value
    
    # General criteria results
    for key, value in result.items():
        if key.startswith("General_"):
            flat[key] = value
    
    # Any other fields
    for key, value in result.items():
        if key not in flat and not isinstance(value, (dict, list)):
            flat[key] = value
        elif isinstance(value, list):
            flat[key] = ", ".join(str(v) for v in value)
    
    return flat 