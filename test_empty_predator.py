#!/usr/bin/env python3
"""
Тест для проверки пустого поля predator в HubSpot
"""

import os
import sys
import asyncio
import logging
import json
from pathlib import Path
import aiohttp

# Добавляем корневую папку проекта в sys.path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

async def test_empty_predator():
    """Тестируем как выглядит пустое поле predator"""
    load_dotenv()
    api_key = os.getenv("HUBSPOT_API_KEY")
    
    if not api_key:
        logger.error("HUBSPOT_API_KEY не найден!")
        return
    
    domain = "wargaming.com"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Найти компанию
    search_url = "https://api.hubapi.com/crm/v3/objects/companies/search"
    search_payload = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "domain", 
                "operator": "EQ",
                "value": domain
            }]
        }],
        "properties": ["name", "gcore_predator_id"],
        "limit": 1
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(search_url, headers=headers, json=search_payload) as response:
            search_data = await response.json()
            company = search_data["results"][0]
            company_id = company["id"]
            
            logger.info(f"Найдена компания: {company['properties']['name']}")
            
            # 1. Очищаем поле - пробуем разные способы
            logger.info("\n🗑️ ТЕСТИРУЕМ ОЧИСТКУ ПОЛЯ:")
            
            clear_methods = [
                ("Очистка через None", None),
                ("Очистка через пустую строку", ""),
                ("Очистка через 0", 0),
            ]
            
            for method_name, clear_value in clear_methods:
                logger.info(f"\n--- {method_name} ---")
                
                # Очистка
                update_url = f"https://api.hubapi.com/crm/v3/objects/companies/{company_id}"
                update_payload = {"properties": {"gcore_predator_id": clear_value}}
                
                async with session.patch(update_url, headers=headers, json=update_payload) as update_response:
                    if update_response.status == 200:
                        logger.info(f"✅ Отправка успешна")
                        
                        # Читаем результат
                        await asyncio.sleep(1)
                        get_url = f"https://api.hubapi.com/crm/v3/objects/companies/{company_id}?properties=gcore_predator_id"
                        
                        async with session.get(get_url, headers=headers) as get_response:
                            get_data = await get_response.json()
                            logger.info(f"RAW ответ: {json.dumps(get_data['properties'], indent=2)}")
                            
                            predator_value = get_data["properties"].get("gcore_predator_id")
                            logger.info(f"Значение: {repr(predator_value)} (тип: {type(predator_value)})")
                            
                            # Проверки
                            checks = [
                                ("is None", predator_value is None),
                                ("== ''", predator_value == ""),
                                ("== '0'", predator_value == "0"),
                                ("not in properties", "gcore_predator_id" not in get_data["properties"]),
                                ("bool()", bool(predator_value)),
                            ]
                            
                            for check_name, result in checks:
                                logger.info(f"   {check_name}: {result}")
                    else:
                        error_text = await update_response.text()
                        logger.error(f"❌ Ошибка: {update_response.status} - {error_text}")

if __name__ == "__main__":
    asyncio.run(test_empty_predator()) 