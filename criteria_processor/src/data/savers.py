"""
Модуль для сохранения результатов в файлы
"""

import os
import json
import pandas as pd
from datetime import datetime
from src.utils.config import OUTPUT_DIR
from src.utils.logging import log_info

def save_results(results, product, timestamp=None):
    """Save results to both JSON and CSV files"""
    if not timestamp:
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
    
    # Save to CSV with proper line break handling - CUSTOM APPROACH
    if csv_data:
        import csv
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            if csv_data:
                fieldnames = csv_data[0].keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
                writer.writeheader()
                for row in csv_data:
                    writer.writerow(row)
        
        log_info(f"💾 CSV результаты сохранены: {csv_path}")
        log_info(f"📊 Обработано записей: {len(results)}")
        log_info(f"📋 Колонок в CSV: {len(fieldnames) if csv_data else 0}")
    
    return json_path, csv_path

def flatten_result_for_csv(result):
    """Converts result to flat dictionary for CSV - CLEAN VERSION"""
    flat = {}
    
    # Копируем ТОЛЬКО исходные данные компании + JSON результаты
    for key, value in result.items():
        if key == "Qualified_Products":
            # НЕ используем json.dumps для этой колонки! Оставляем переносы строк как есть
            flat[key] = value if value else ""
        elif not key.startswith(("Qualification_", "General_", "Mandatory_", "NTH_", "Status_", "Final_Status", "Global_Criteria_Status", "Qualified_Audiences_")):
            # Исходные данные компании
            if isinstance(value, (dict, list)):
                # Форматируем JSON с переносами строк для читаемости в CSV
                flat[key] = json.dumps(value, ensure_ascii=False, indent=2) if value else ""
            else:
                flat[key] = value
    
    return flat 