#!/usr/bin/env python3
"""
Тест для проверки RAW ответа HubSpot API
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

async def test_raw_hubspot_response():
    """Тестируем RAW ответ от HubSpot API"""
    load_dotenv()
    api_key = os.getenv("HUBSPOT_API_KEY")
    
    if not api_key:
        logger.error("HUBSPOT_API_KEY не найден!")
        return
    
    # Данные тестовой компании
    domain = "wargaming.com"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 1. Поиск компании
    logger.info(f"🔍 Ищем компанию по домену: {domain}")
    
    search_url = "https://api.hubapi.com/crm/v3/objects/companies/search"
    search_payload = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "domain",
                "operator": "EQ",
                "value": domain
            }]
        }],
        "properties": ["name", "domain", "gcore_predator_id"],
        "limit": 1
    }
    
    async with aiohttp.ClientSession() as session:
        # Поиск компании
        async with session.post(search_url, headers=headers, json=search_payload) as response:
            if response.status == 200:
                search_data = await response.json()
                logger.info(f"📋 RAW SEARCH RESPONSE:")
                logger.info(json.dumps(search_data, indent=2, ensure_ascii=False))
                
                results = search_data.get("results", [])
                if not results:
                    logger.error("❌ Компания не найдена")
                    return
                
                company = results[0]
                company_id = company.get("id")
                properties = company.get("properties", {})
                predator_value = properties.get("gcore_predator_id")
                
                logger.info(f"\n📊 АНАЛИЗ ПОЛЯ gcore_predator_id:")
                logger.info(f"   RAW значение: {repr(predator_value)}")
                logger.info(f"   Тип: {type(predator_value)}")
                logger.info(f"   is None: {predator_value is None}")
                logger.info(f"   == '': {predator_value == ''}")
                logger.info(f"   bool(): {bool(predator_value)}")
                
                # 2. Записываем тестовое значение
                logger.info(f"\n✏️ Записываем predator_id = 999")
                
                update_url = f"https://api.hubapi.com/crm/v3/objects/companies/{company_id}"
                update_payload = {
                    "properties": {
                        "gcore_predator_id": 999  # Записываем как число
                    }
                }
                
                async with session.patch(update_url, headers=headers, json=update_payload) as update_response:
                    if update_response.status == 200:
                        logger.info("✅ Запись успешна")
                        
                        # 3. Читаем обратно
                        await asyncio.sleep(1)
                        
                        get_url = f"https://api.hubapi.com/crm/v3/objects/companies/{company_id}?properties=gcore_predator_id,name"
                        
                        async with session.get(get_url, headers=headers) as get_response:
                            if get_response.status == 200:
                                get_data = await get_response.json()
                                logger.info(f"\n📋 RAW GET RESPONSE:")
                                logger.info(json.dumps(get_data, indent=2, ensure_ascii=False))
                                
                                get_properties = get_data.get("properties", {})
                                new_predator = get_properties.get("gcore_predator_id")
                                
                                logger.info(f"\n📊 АНАЛИЗ ПОСЛЕ ЗАПИСИ:")
                                logger.info(f"   RAW значение: {repr(new_predator)}")
                                logger.info(f"   Тип: {type(new_predator)}")
                                logger.info(f"   Записали: 999 (int)")
                                logger.info(f"   Получили: {new_predator} ({type(new_predator)})")
                            else:
                                logger.error(f"❌ Ошибка чтения: {get_response.status}")
                    else:
                        error_text = await update_response.text()
                        logger.error(f"❌ Ошибка записи: {update_response.status} - {error_text}")
            else:
                error_text = await response.text()
                logger.error(f"❌ Ошибка поиска: {response.status} - {error_text}")

if __name__ == "__main__":
    asyncio.run(test_raw_hubspot_response()) 