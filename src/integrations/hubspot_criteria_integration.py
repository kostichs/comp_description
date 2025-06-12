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
    1. Всегда перезаписывает критерии при включенном чекбоксе
    2. Обновляет описание и timestamp
    
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
                
                # Всегда обновляем критерии при включенном чекбоксе HubSpot
                log_info(f"🔄 {company_name}: обновляем критерии в HubSpot")
                
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
    УСТАРЕЛА - теперь критерии всегда перезаписываются
    """
    return None

async def _check_hubspot_criteria_freshness_async(company_id: str, company_name: str) -> Optional[Dict[str, Any]]:
    """
    Проверяет свежесть критериев в HubSpot для конкретной компании
    УСТАРЕЛА - теперь критерии всегда перезаписываются
    """
    return None 