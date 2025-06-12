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
    
    # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ПАРАМЕТРОВ
    log_info(f"🔧 save_results вызвана с параметрами:")
    log_info(f"   📊 results: {len(results)} записей")
    log_info(f"   📦 product: {product}")
    log_info(f"   🕒 timestamp: {timestamp}")
    log_info(f"   🆔 session_id: {session_id}")
    log_info(f"   🔗 write_to_hubspot_criteria: {write_to_hubspot_criteria}")
    log_info(f"   📄 original_file_path: {original_file_path}")
    
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
    
    # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ HUBSPOT ИНТЕГРАЦИИ
    log_info(f"🔍 ПРОВЕРКА HUBSPOT ИНТЕГРАЦИИ:")
    log_info(f"   🔗 write_to_hubspot_criteria = {write_to_hubspot_criteria}")
    log_info(f"   📊 Количество результатов = {len(results)}")
    
    # HubSpot Integration for Criteria - ПРОСТАЯ ВЕРСИЯ КАК В ПЕРВОЙ ВКЛАДКЕ
    if write_to_hubspot_criteria:
        log_info("🚀 HUBSPOT ИНТЕГРАЦИЯ ВКЛЮЧЕНА - начинаем обработку...")
        
        try:
            log_info("🔗 Начинаем интеграцию с HubSpot для критериев...")
            
            # Проверяем API ключ
            hubspot_api_key = os.getenv("HUBSPOT_API_KEY")
            log_info(f"🔑 Проверка API ключа: {'НАЙДЕН' if hubspot_api_key else 'НЕ НАЙДЕН'}")
            if hubspot_api_key:
                log_info(f"🔑 API ключ начинается с: {hubspot_api_key[:10]}...")
            
            if not hubspot_api_key:
                log_info("⚠️ HUBSPOT_API_KEY не найден - пропускаем интеграцию")
                return json_path, csv_path
            
            # Импортируем HubSpot клиент напрямую
            log_info("📦 Импортируем HubSpot клиент...")
            
            # Добавляем корень проекта в sys.path для доступа к src.integrations
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
                log_info(f"📁 Добавлен путь в sys.path: {project_root}")
            
            # Проверяем что путь к HubSpot клиенту существует
            hubspot_client_path = os.path.join(project_root, "src", "integrations", "hubspot", "client.py")
            log_info(f"🔍 Проверяем путь к HubSpot клиенту: {hubspot_client_path}")
            log_info(f"📄 Файл существует: {os.path.exists(hubspot_client_path)}")
            
            # Используем importlib для динамического импорта
            import importlib.util
            spec = importlib.util.spec_from_file_location("hubspot_client", hubspot_client_path)
            hubspot_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(hubspot_module)
            HubSpotClient = hubspot_module.HubSpotClient
            log_info("✅ HubSpot клиент импортирован успешно через importlib")
            
            # Создаем клиент
            log_info("🔧 Создаем HubSpot клиент...")
            hubspot_client = HubSpotClient(api_key=hubspot_api_key)
            log_info("✅ HubSpot клиент создан успешно")
            
            stats = {"processed": 0, "updated": 0, "errors": 0, "skipped": 0}
            
            log_info(f"🔄 Начинаем обработку {len(results)} компаний...")
            
            for i, result in enumerate(results):
                try:
                    company_name = result.get("Company_Name", "")
                    hubspot_company_id = result.get("HubSpot_Company_ID")
                    
                    log_info(f"🏢 [{i+1}/{len(results)}] Обрабатываем: {company_name}")
                    log_info(f"   🆔 HubSpot_Company_ID: {hubspot_company_id}")
                    
                    if not company_name or not hubspot_company_id:
                        log_info(f"   ⚠️ Пропускаем - отсутствует Company_Name или HubSpot_Company_ID")
                        stats["skipped"] += 1
                        continue
                    
                    # Извлекаем ID из URL если нужно
                    original_id = hubspot_company_id
                    if isinstance(hubspot_company_id, str) and "hubspot.com" in hubspot_company_id:
                        hubspot_company_id = hubspot_company_id.split("/")[-1]
                        log_info(f"   🔗 Извлечен ID {hubspot_company_id} из URL {original_id}")
                    
                    # Подготавливаем данные для записи - ТОЛЬКО ai_criteria
                    criteria_data = result.get("All_Results", {})
                    log_info(f"   📊 All_Results содержит {len(criteria_data)} продуктов: {list(criteria_data.keys())}")
                    
                    # Формируем данные для обновления
                    criteria_json = json.dumps(criteria_data, ensure_ascii=False, separators=(',', ':'))
                    update_data = {
                        "ai_criteria": criteria_json
                    }
                    log_info(f"   📝 Подготовлены данные для записи: ai_criteria ({len(criteria_json)} символов)")
                    
                    # Обновляем компанию в HubSpot синхронно
                    log_info(f"   🚀 Отправляем данные в HubSpot для компании ID {hubspot_company_id}...")
                    import asyncio
                    
                    # Простой способ запуска async функции
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        success = loop.run_until_complete(
                            hubspot_client.update_company_properties(hubspot_company_id, update_data)
                        )
                        log_info(f"   📡 HubSpot API вернул: {success}")
                    finally:
                        loop.close()
                    
                    if success:
                        log_info(f"   ✅ {company_name}: критерии записаны в HubSpot")
                        stats["updated"] += 1
                    else:
                        log_info(f"   ❌ {company_name}: ошибка записи в HubSpot")
                        stats["errors"] += 1
                    
                    stats["processed"] += 1
                    
                except Exception as e:
                    log_info(f"   ❌ Ошибка обработки {company_name}: {e}")
                    import traceback
                    log_info(f"   📋 Traceback: {traceback.format_exc()}")
                    stats["errors"] += 1
            
            log_info(f"🎉 HubSpot интеграция завершена:")
            log_info(f"   📊 Обработано: {stats['processed']}")
            log_info(f"   ✅ Обновлено: {stats['updated']}")
            log_info(f"   ❌ Ошибок: {stats['errors']}")
            log_info(f"   ⏭️ Пропущено: {stats['skipped']}")
            
        except Exception as e:
            log_info(f"❌ КРИТИЧЕСКАЯ ОШИБКА HubSpot интеграции: {e}")
            import traceback
            log_info(f"📋 Полный traceback: {traceback.format_exc()}")
    else:
        log_info("📝 HUBSPOT ИНТЕГРАЦИЯ ОТКЛЮЧЕНА (write_to_hubspot_criteria=False)")
    
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