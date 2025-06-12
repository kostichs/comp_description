"""
Модуль для сохранения результатов в файлы
"""

import os
import sys
import json
import pandas as pd
from datetime import datetime

# Добавляем корень проекта в sys.path для импорта HubSpot интеграции
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file)))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.config import OUTPUT_DIR
from src.utils.logging import log_info
from src.utils.encoding_handler import save_csv_with_encoding, save_text_with_encoding

def save_results(results, product, timestamp=None, session_id=None, write_to_hubspot_criteria=False, original_file_path=None):
    """Save results to both JSON and CSV files in session-specific directory"""
    if not timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create session-specific output directory
    if session_id:
        session_output_dir = os.path.join(OUTPUT_DIR, session_id)
        log_info(f"📁 Создаем папку сессии: {session_output_dir}")
    else:
        session_output_dir = OUTPUT_DIR
        log_info(f"📁 Используем общую папку: {session_output_dir}")
    
    # Ensure session output directory exists
    os.makedirs(session_output_dir, exist_ok=True)
    
    # Create output filenames
    json_filename = f"analysis_results_{product}_{timestamp}.json"
    csv_filename = f"analysis_results_{product}_{timestamp}.csv"
    
    json_path = os.path.join(session_output_dir, json_filename)
    csv_path = os.path.join(session_output_dir, csv_filename)
    
    # Save to JSON with pretty formatting using UTF-8
    json_content = json.dumps(results, ensure_ascii=False, indent=2)
    save_text_with_encoding(json_content, json_path, encoding='utf-8')
    log_info(f"💾 JSON результаты сохранены: {json_path}")
    
    # Convert to CSV format
    csv_data = []
    for result in results:
        # Flatten nested structures for CSV
        flat_result = flatten_result_for_csv(result)
        csv_data.append(flat_result)
    
    # Save to CSV with proper encoding handling
    if csv_data:
        df = pd.DataFrame(csv_data)
        save_csv_with_encoding(df, csv_path, encoding='utf-8-sig')
        
        log_info(f"💾 CSV результаты сохранены: {csv_path}")
        log_info(f"📊 Обработано записей: {len(results)}")
        log_info(f"📋 Колонок в CSV: {len(df.columns) if not df.empty else 0}")
    
    # HubSpot Integration for Criteria
    if write_to_hubspot_criteria:
        try:
            log_info("🔗 Начинаем интеграцию с HubSpot для критериев...")
            
            # Используем существующую HubSpot инфраструктуру
            hubspot_api_key = os.getenv("HUBSPOT_API_KEY")
            if not hubspot_api_key:
                log_info("⚠️ HUBSPOT_API_KEY не найден - пропускаем интеграцию")
                return json_path, csv_path
            
            # Прямой импорт HubSpot клиента через spec
            import importlib.util
            client_path = os.path.join(project_root, "src", "integrations", "hubspot", "client.py")
            spec = importlib.util.spec_from_file_location("hubspot_client", client_path)
            client_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(client_module)
            
            # Создаем клиент и обрабатываем результаты
            hubspot_client = client_module.HubSpotClient()
            
            stats = {"processed": 0, "updated": 0, "errors": 0, "skipped": 0}
            
            for result in results:
                try:
                    company_name = result.get("Company_Name", "")
                    hubspot_company_id = result.get("HubSpot_Company_ID")
                    
                    if not company_name or not hubspot_company_id:
                        stats["skipped"] += 1
                        continue
                    
                    # Извлекаем ID из URL если нужно
                    if isinstance(hubspot_company_id, str) and "hubspot.com" in hubspot_company_id:
                        # Извлекаем ID из URL типа https://app.hubspot.com/contacts/4202168/record/0-2/4833748489
                        hubspot_company_id = hubspot_company_id.split("/")[-1]
                        log_info(f"🔗 {company_name}: извлечен ID {hubspot_company_id} из URL")
                    
                    # Подготавливаем данные для записи
                    criteria_data = result.get("All_Results", {})
                    description = result.get("Description", "")
                    
                    # Формируем данные для обновления
                    update_data = {
                        "ai_criteria": json.dumps(criteria_data, ensure_ascii=False, separators=(',', ':')),
                        "ai_description": description,
                        "ai_description_updated": datetime.now().isoformat()
                    }
                    
                    # Обновляем компанию в HubSpot синхронно
                    import asyncio
                    import concurrent.futures
                    
                    # Используем ThreadPoolExecutor для выполнения async функции в отдельном потоке
                    def run_async_in_thread():
                        return asyncio.run(hubspot_client.update_company_properties(hubspot_company_id, update_data))
                    
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_async_in_thread)
                        success = future.result()
                    
                    if success:
                        log_info(f"✅ {company_name}: критерии записаны в HubSpot")
                        stats["updated"] += 1
                    else:
                        log_info(f"❌ {company_name}: ошибка записи в HubSpot")
                        stats["errors"] += 1
                    
                    stats["processed"] += 1
                    
                except Exception as e:
                    log_info(f"❌ Ошибка обработки {company_name}: {e}")
                    stats["errors"] += 1
            
            log_info(f"✅ HubSpot интеграция завершена: {stats}")
            
        except ImportError as e:
            log_info(f"⚠️ HubSpot интеграция недоступна - модуль не найден: {e}")
        except Exception as e:
            log_info(f"❌ Ошибка HubSpot интеграции: {e}")
    else:
        log_info("📝 HubSpot интеграция отключена")
    
    # Объединение исходного файла с результатами
    if original_file_path and os.path.exists(original_file_path):
        try:
            # Импортируем функцию объединения из основного проекта
            sys.path.insert(0, project_root)
            from src.data_io import merge_original_with_results
            
            # Создаем путь для объединенного файла
            merged_file_path = csv_path.replace('.csv', '_merged.csv')
            
            # Объединяем исходный файл с результатами
            merge_success = merge_original_with_results(
                original_file_path=original_file_path,
                results_file_path=csv_path,
                output_file_path=merged_file_path
            )
            
            if merge_success:
                log_info(f"📋 Создан объединенный файл: {merged_file_path}")
                # Заменяем основной файл результатов объединенным
                import shutil
                shutil.move(merged_file_path, csv_path)
                log_info(f"📋 Основной файл результатов заменен объединенным: {csv_path}")
            else:
                log_info("⚠️ Не удалось создать объединенный файл, оставляем исходный файл результатов")
                
        except Exception as e:
            log_info(f"❌ Ошибка при объединении файлов: {e}")
            log_info("⚠️ Оставляем исходный файл результатов без объединения")
    else:
        if original_file_path:
            log_info(f"⚠️ Исходный файл не найден: {original_file_path}")
        else:
            log_info("📝 Путь к исходному файлу не указан - пропускаем объединение")
    
    return json_path, csv_path

def flatten_result_for_csv(result):
    """Converts result to flat dictionary for CSV - CLEAN VERSION"""
    flat = {}
    
    # Копируем ВСЕ данные, включая исходные колонки компании
    for key, value in result.items():
        if key == "Qualified_Products":
            # НЕ используем json.dumps для этой колонки! Оставляем переносы строк как есть
            flat[key] = value if value else ""
        elif key == "All_Results":
            # JSON результаты форматируем для читаемости
            flat[key] = json.dumps(value, ensure_ascii=False, indent=2) if value else ""
        else:
            # ВСЕ остальные колонки (включая исходные данные компании) сохраняем как есть
            if isinstance(value, (dict, list)):
                flat[key] = json.dumps(value, ensure_ascii=False, indent=2) if value else ""
            else:
                flat[key] = value
    
    return flat 