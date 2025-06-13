#!/usr/bin/env python3
"""
Тестовый скрипт для проверки записи predator_id в HubSpot
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Добавляем корневую папку проекта в sys.path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.hubspot.adapter import HubSpotAdapter
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_predator_save():
    """Тестирует сохранение predator_id в HubSpot"""
    
    # Загружаем переменные окружения
    load_dotenv()
    
    # Создаем адаптер HubSpot
    hubspot_adapter = HubSpotAdapter()
    
    if not hubspot_adapter.client.api_key:
        logger.error("HUBSPOT_API_KEY не найден в переменных окружения!")
        return
    
    # Тестовые данные из вашего файла
    test_company_name = "Wargaming Group Limited"
    test_url = "wargaming.com" 
    test_predator_id = "383"
    test_description = "Test description for predator functionality"
    
    logger.info(f"Тестируем сохранение predator_id: {test_predator_id} для компании: {test_company_name}")
    
    try:
        # Сначала проверим, есть ли компания в HubSpot
        logger.info(f"Проверяем наличие компании '{test_company_name}' в HubSpot...")
        description_is_fresh, hubspot_company_data = await hubspot_adapter.check_company_description(
            test_company_name, test_url
        )
        
        if hubspot_company_data:
            logger.info(f"Компания найдена в HubSpot. ID: {hubspot_company_data.get('id')}")
            
            # Получаем текущие данные
            description, timestamp, linkedin_url, current_predator = hubspot_adapter.get_company_details_from_hubspot_data(hubspot_company_data)
            logger.info(f"Текущий predator_id в HubSpot: {current_predator}")
        else:
            logger.info("Компания НЕ найдена в HubSpot, будет создана новая")
        
        # Сохраняем/обновляем данные с predator_id
        logger.info(f"Сохраняем predator_id: {test_predator_id}...")
        success, company_id = await hubspot_adapter.save_company_description(
            company_data=hubspot_company_data,
            company_name=test_company_name,
            url=test_url,
            description=test_description,
            linkedin_url=None,
            predator_id=test_predator_id
        )
        
        if success:
            logger.info(f"✅ Успешно сохранено! Company ID: {company_id}")
            
            # Проверяем результат
            logger.info("Проверяем результат...")
            description_is_fresh, updated_company_data = await hubspot_adapter.check_company_description(
                test_company_name, test_url
            )
            
            if updated_company_data:
                _, _, _, final_predator = hubspot_adapter.get_company_details_from_hubspot_data(updated_company_data)
                logger.info(f"Финальный predator_id в HubSpot: {final_predator}")
                
                if str(final_predator) == str(test_predator_id):
                    logger.info("✅ ТЕСТ ПРОЙДЕН: predator_id корректно сохранен в HubSpot!")
                else:
                    logger.error(f"❌ ТЕСТ НЕ ПРОЙДЕН: predator_id не совпадает. Ожидалось: {test_predator_id}, получено: {final_predator}")
            else:
                logger.error("❌ Не удалось повторно найти компанию для проверки")
        else:
            logger.error(f"❌ Ошибка при сохранении данных. Company ID: {company_id}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при выполнении теста: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_predator_save()) 