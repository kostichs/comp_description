"""
HubSpot интеграция для результатов анализа критериев
Использует существующий HubSpotClient как в описаниях
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import logging

def log_info(message):
    logging.info(message)

def log_error(message):
    logging.error(message)
from src.integrations.hubspot.client import HubSpotClient


def process_criteria_results_to_hubspot(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Обрабатывает результаты анализа критериев и записывает их в HubSpot
    
    Алгоритм:
    1. Проверяет существующие критерии в HubSpot
    2. Проверяет свежесть по ai_description_updated (не старше 6 месяцев)
    3. Либо загружает данные из HubSpot, либо записывает новые критерии
    4. Также обновляет описание и timestamp
    
    Args:
        results: Список результатов анализа критериев
        
    Returns:
        Dict с информацией о результатах интеграции
    """
    return asyncio.run(_process_criteria_results_to_hubspot_async(results))

async def _process_criteria_results_to_hubspot_async(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Асинхронная версия функции интеграции"""
    log_info("🔗 Начинаем обработку результатов критериев для HubSpot...")
    
    try:
        # Инициализация HubSpot клиента
        hubspot_client = HubSpotClient()
        
        if not hubspot_client.api_key:
            log_error("❌ Нет API ключа HubSpot")
            return {
                "status": "skipped",
                "reason": "No HubSpot API key",
                "processed": 0,
                "errors": 0
            }

        stats = {
            "processed": 0,
            "updated": 0,
            "loaded_from_hubspot": 0,
            "errors": 0,
            "skipped": 0
        }
        
        for result in results:
            try:
                company_name = result.get("Company_Name", "")
                if not company_name:
                    log_error("❌ Пропускаем запись без Company_Name")
                    stats["skipped"] += 1
                    continue
                
                log_info(f"🏢 Обрабатываем: {company_name}")
                
                # Ищем компанию в HubSpot
                hubspot_company_id = result.get("HubSpot_Company_ID")
                if not hubspot_company_id:
                    log_info(f"⚠️ {company_name}: нет HubSpot_Company_ID - пропускаем")
                    stats["skipped"] += 1
                    continue
                
                # Получаем текущие данные из HubSpot
                existing_data = await hubspot_client.get_company_properties(
                    hubspot_company_id, 
                    ["ai_criteria", "ai_description", "ai_description_updated"]
                )
                
                if not existing_data:
                    log_error(f"❌ {company_name}: не удалось получить данные из HubSpot")
                    stats["errors"] += 1
                    continue
                
                # Проверяем свежесть существующих критериев
                existing_criteria = existing_data.get("ai_criteria")
                existing_updated = existing_data.get("ai_description_updated")
                
                should_update = True
                
                if existing_criteria and existing_updated:
                    try:
                        # Проверяем возраст данных (не старше 6 месяцев)
                        updated_date = datetime.fromisoformat(existing_updated.replace('Z', '+00:00'))
                        six_months_ago = datetime.now().replace(tzinfo=updated_date.tzinfo) - timedelta(days=180)
                        
                        if updated_date > six_months_ago:
                            log_info(f"📋 {company_name}: критерии свежие ({existing_updated}) - загружаем из HubSpot")
                            
                            # Загружаем существующие критерии в результат
                            try:
                                existing_criteria_data = json.loads(existing_criteria)
                                result["All_Results"] = existing_criteria_data
                                result["Qualified_Products"] = "LOADED FROM HUBSPOT"
                                
                                should_update = False
                                stats["loaded_from_hubspot"] += 1
                                
                            except json.JSONDecodeError:
                                log_error(f"❌ {company_name}: ошибка парсинга существующих критериев")
                                should_update = True
                        else:
                            log_info(f"⏰ {company_name}: критерии устарели ({existing_updated}) - обновляем")
                            
                    except Exception as e:
                        log_error(f"❌ {company_name}: ошибка проверки даты: {e}")
                        should_update = True
                
                if should_update:
                    # Подготавливаем данные для записи
                    criteria_data = result.get("All_Results", {})
                    description = result.get("Description", "")
                    
                    # Формируем данные для обновления
                    update_data = {
                        "ai_criteria": json.dumps(criteria_data, ensure_ascii=False, separators=(',', ':')),
                        "ai_description": description,
                        "ai_description_updated": datetime.now().isoformat()
                    }
                    
                    # Обновляем компанию в HubSpot
                    success = await hubspot_client.update_company_properties(
                        hubspot_company_id, 
                        update_data
                    )
                    
                    if success:
                        log_info(f"✅ {company_name}: критерии и описание обновлены в HubSpot")
                        stats["updated"] += 1
                    else:
                        log_error(f"❌ {company_name}: ошибка обновления в HubSpot")
                        stats["errors"] += 1
                
                stats["processed"] += 1
                
            except Exception as e:
                log_error(f"❌ Ошибка обработки компании {result.get('Company_Name', 'Unknown')}: {e}")
                stats["errors"] += 1
        
        log_info(f"""
🎉 HubSpot интеграция критериев завершена:
   📊 Обработано: {stats['processed']}
   ✅ Обновлено: {stats['updated']}
   📋 Загружено из HubSpot: {stats['loaded_from_hubspot']}
   ❌ Ошибок: {stats['errors']}
   ⏭️ Пропущено: {stats['skipped']}""")
        
        return {
            "status": "completed",
            **stats
        }
        
    except Exception as e:
        log_error(f"❌ Критическая ошибка HubSpot интеграции: {e}")
        return {
            "status": "error",
            "error": str(e),
            "processed": 0,
            "errors": 1
        }


def check_hubspot_criteria_freshness(company_id: str, company_name: str) -> Optional[Dict[str, Any]]:
    """
    Синхронная обертка для проверки свежести критериев
    """
    return asyncio.run(_check_hubspot_criteria_freshness_async(company_id, company_name))

async def _check_hubspot_criteria_freshness_async(company_id: str, company_name: str) -> Optional[Dict[str, Any]]:
    """
    Проверяет свежесть критериев в HubSpot для конкретной компании
    
    Args:
        company_id: HubSpot ID компании
        company_name: Название компании для логирования
        
    Returns:
        Dict с критериями если они свежие, None если нужно обновить
    """
    try:
        # Инициализация HubSpot клиента
        hubspot_client = HubSpotClient()
        
        # Получаем данные из HubSpot
        existing_data = await hubspot_client.get_company_properties(
            company_id, 
            ["ai_criteria", "ai_description_updated"]
        )
        
        if not existing_data:
            return None
        
        existing_criteria = existing_data.get("ai_criteria")
        existing_updated = existing_data.get("ai_description_updated")
        
        if not existing_criteria or not existing_updated:
            return None
        
        # Проверяем возраст данных
        try:
            updated_date = datetime.fromisoformat(existing_updated.replace('Z', '+00:00'))
            six_months_ago = datetime.now().replace(tzinfo=updated_date.tzinfo) - timedelta(days=180)
            
            if updated_date > six_months_ago:
                # Критерии свежие - возвращаем их
                criteria_data = json.loads(existing_criteria)
                log_info(f"📋 {company_name}: найдены свежие критерии в HubSpot ({existing_updated})")
                return criteria_data
            else:
                log_info(f"⏰ {company_name}: критерии в HubSpot устарели ({existing_updated})")
                return None
                
        except Exception as e:
            log_error(f"❌ {company_name}: ошибка проверки даты критериев: {e}")
            return None
        
    except Exception as e:
        log_error(f"❌ {company_name}: ошибка проверки критериев в HubSpot: {e}")
        return None 