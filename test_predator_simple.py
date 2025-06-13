#!/usr/bin/env python3
"""
Простой тест для быстрой проверки predator операций
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Добавляем корневую папку проекта в sys.path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.hubspot.client import HubSpotClient
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

async def quick_test():
    """Быстрый тест"""
    load_dotenv()
    client = HubSpotClient()
    
    # Тестовые данные из последней сессии
    domain = "wargaming.com"
    test_predator = "383"
    
    if not client.api_key:
        logger.error("HUBSPOT_API_KEY не найден!")
        return
    
    logger.info(f"🔍 Ищем компанию по домену: {domain}")
    
    # 1. Найти компанию
    company = await client.search_company_by_domain(domain)
    if not company:
        logger.error("❌ Компания не найдена!")
        return
    
    company_id = company.get("id")
    properties = company.get("properties", {})
    current_predator = properties.get("gcore_predator_id")
    
    logger.info(f"✅ Компания найдена: {properties.get('name')}")
    logger.info(f"   ID: {company_id}")
    logger.info(f"   Текущий predator: {current_predator} (тип: {type(current_predator)})")
    
    # 2. Записать тестовое значение
    logger.info(f"\n✏️ Записываем predator_id = {test_predator}")
    success = await client.update_company_properties(company_id, {
        "gcore_predator_id": int(test_predator)
    })
    
    if success:
        logger.info("✅ Запись успешна")
        
        # 3. Прочитать обратно
        await asyncio.sleep(1)
        properties = await client.get_company_properties(company_id, ["gcore_predator_id"])
        new_value = properties.get("gcore_predator_id") if properties else None
        
        logger.info(f"📖 Прочитано значение: {new_value} (тип: {type(new_value)})")
        
        # 4. Проверить соответствие
        if str(new_value) == test_predator:
            logger.info("✅ Значения совпадают!")
        else:
            logger.error(f"❌ Значения НЕ совпадают! Ожидалось: {test_predator}, получено: {new_value}")
    else:
        logger.error("❌ Ошибка при записи")
    
    # 5. Тестируем очистку
    logger.info(f"\n🗑️ Очищаем predator_id")
    success = await client.update_company_properties(company_id, {
        "gcore_predator_id": ""  # ИСПРАВЛЕНО: используем пустую строку!
    })
    
    if success:
        logger.info("✅ Очистка успешна")
        
        await asyncio.sleep(1)
        properties = await client.get_company_properties(company_id, ["gcore_predator_id"])
        empty_value = properties.get("gcore_predator_id") if properties else None
        
        logger.info(f"📖 Пустое значение: {repr(empty_value)} (тип: {type(empty_value)})")
        logger.info(f"   is None: {empty_value is None}")
        logger.info(f"   bool(): {bool(empty_value)}")
        
        # 6. Восстанавливаем исходное значение
        if current_predator is not None:
            logger.info(f"\n🔄 Восстанавливаем исходное значение: {current_predator}")
            await client.update_company_properties(company_id, {
                "gcore_predator_id": current_predator
            })
            logger.info("✅ Исходное значение восстановлено")
    else:
        logger.error("❌ Ошибка при очистке")

if __name__ == "__main__":
    asyncio.run(quick_test()) 