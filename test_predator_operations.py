#!/usr/bin/env python3
"""
Полный тест операций с predator_id в HubSpot

Этот скрипт тестирует:
1. Запись значения в поле gcore_predator_id
2. Чтение значения из поля
3. Удаление значения из поля
4. Проверку как выглядит пустое значение
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
import aiohttp

# Добавляем корневую папку проекта в sys.path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.hubspot.client import HubSpotClient
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PredatorTester:
    def __init__(self):
        load_dotenv()
        self.client = HubSpotClient()
        
        # Данные тестовой компании из последней сессии
        self.test_company_name = "Wargaming Group Limited"
        self.test_domain = "wargaming.com"
        self.test_predator_values = ["383", "999", "0", "1234"]
        
        if not self.client.api_key:
            raise ValueError("HUBSPOT_API_KEY не найден в переменных окружения!")
            
    async def find_company_by_domain(self) -> dict:
        """Найти компанию по домену"""
        logger.info(f"🔍 Поиск компании '{self.test_company_name}' по домену '{self.test_domain}'")
        
        company = await self.client.search_company_by_domain(self.test_domain)
        
        if company:
            company_id = company.get("id")
            properties = company.get("properties", {})
            current_predator = properties.get("gcore_predator_id")
            
            logger.info(f"✅ Компания найдена!")
            logger.info(f"   ID: {company_id}")
            logger.info(f"   Name: {properties.get('name')}")
            logger.info(f"   Domain: {properties.get('domain')}")
            logger.info(f"   Current predator_id: {current_predator} (type: {type(current_predator)})")
            
            return company
        else:
            logger.error("❌ Компания НЕ найдена!")
            return None
    
    async def read_predator_value(self, company_id: str) -> any:
        """Прочитать текущее значение predator_id"""
        logger.info(f"📖 Чтение текущего значения predator_id для компании {company_id}")
        
        properties = await self.client.get_company_properties(
            company_id, 
            ["gcore_predator_id", "name", "domain"]
        )
        
        if properties:
            predator_value = properties.get("gcore_predator_id")
            logger.info(f"   Текущее значение predator_id: {predator_value}")
            logger.info(f"   Тип значения: {type(predator_value)}")
            logger.info(f"   Значение == None: {predator_value is None}")
            logger.info(f"   Значение == '': {predator_value == ''}")
            logger.info(f"   bool(значение): {bool(predator_value)}")
            return predator_value
        else:
            logger.error("❌ Не удалось получить свойства компании")
            return None
    
    async def write_predator_value(self, company_id: str, value: str) -> bool:
        """Записать значение в predator_id"""
        logger.info(f"✏️ Запись predator_id = '{value}' для компании {company_id}")
        
        try:
            # Конвертируем в число, как это делается в основном коде
            predator_numeric = int(value) if value else None
            
            properties = {
                "gcore_predator_id": predator_numeric
            }
            
            success = await self.client.update_company_properties(company_id, properties)
            
            if success:
                logger.info(f"✅ Успешно записано predator_id = {predator_numeric}")
                return True
            else:
                logger.error(f"❌ Ошибка при записи predator_id = {value}")
                return False
                
        except ValueError as e:
            logger.error(f"❌ Ошибка конвертации '{value}' в число: {e}")
            return False
    
    async def clear_predator_value(self, company_id: str) -> bool:
        """Удалить/очистить значение predator_id"""
        logger.info(f"🗑️ Очистка predator_id для компании {company_id}")
        
        # Пробуем разные способы очистки
        clear_methods = [
            ("Очистка через None", {"gcore_predator_id": None}),
            ("Очистка через пустую строку", {"gcore_predator_id": ""}),
        ]
        
        for method_name, properties in clear_methods:
            logger.info(f"   Пробуем: {method_name}")
            
            success = await self.client.update_company_properties(company_id, properties)
            
            if success:
                logger.info(f"   ✅ {method_name} - успешно")
                # Проверяем результат
                await asyncio.sleep(1)  # Небольшая пауза для обновления в HubSpot
                current_value = await self.read_predator_value(company_id)
                logger.info(f"   Результат после очистки: {current_value}")
                return True
            else:
                logger.error(f"   ❌ {method_name} - не удалось")
        
        return False
    
    async def test_all_operations(self):
        """Выполнить все тесты операций с predator_id"""
        logger.info("🚀 Начинаем полное тестирование операций с predator_id")
        logger.info("=" * 60)
        
        # 1. Найти компанию
        company = await self.find_company_by_domain()
        if not company:
            logger.error("❌ Невозможно продолжить тестирование без компании")
            return
        
        company_id = company.get("id")
        logger.info("=" * 60)
        
        # 2. Прочитать начальное значение
        logger.info("📋 ЭТАП 1: Чтение начального значения")
        initial_value = await self.read_predator_value(company_id)
        logger.info("=" * 60)
        
        # 3. Тестирование записи разных значений
        logger.info("📋 ЭТАП 2: Тестирование записи значений")
        for test_value in self.test_predator_values:
            logger.info(f"--- Тестируем значение: '{test_value}' ---")
            
            # Записываем значение
            write_success = await self.write_predator_value(company_id, test_value)
            
            if write_success:
                # Читаем обратно
                await asyncio.sleep(1)  # Пауза для обновления
                read_value = await self.read_predator_value(company_id)
                
                # Проверяем соответствие
                expected_value = int(test_value)
                if read_value == expected_value:
                    logger.info(f"✅ Тест ПРОЙДЕН: записано {test_value}, прочитано {read_value}")
                else:
                    logger.error(f"❌ Тест НЕ ПРОЙДЕН: записано {test_value}, прочитано {read_value}")
            
            logger.info("")
        
        logger.info("=" * 60)
        
        # 4. Тестирование очистки
        logger.info("📋 ЭТАП 3: Тестирование очистки значения")
        clear_success = await self.clear_predator_value(company_id)
        
        if clear_success:
            logger.info("✅ Очистка выполнена успешно")
        else:
            logger.error("❌ Очистка не удалась")
        
        logger.info("=" * 60)
        
        # 5. Проверка пустого значения
        logger.info("📋 ЭТАП 4: Анализ пустого значения")
        empty_value = await self.read_predator_value(company_id)
        logger.info(f"🔍 Пустое значение предатора выглядит как: {repr(empty_value)}")
        
        # Различные проверки пустого значения
        checks = [
            ("is None", empty_value is None),
            ("== None", empty_value == None),
            ("== ''", empty_value == ''),
            ("== 0", empty_value == 0),
            ("bool(value)", bool(empty_value)),
            ("not value", not empty_value),
        ]
        
        logger.info("🔍 Результаты проверок пустого значения:")
        for check_name, result in checks:
            logger.info(f"   {check_name}: {result}")
        
        logger.info("=" * 60)
        
        # 6. Восстановление исходного значения (если было)
        if initial_value is not None:
            logger.info(f"📋 ЭТАП 5: Восстановление исходного значения {initial_value}")
            restore_success = await self.write_predator_value(company_id, str(initial_value))
            if restore_success:
                logger.info("✅ Исходное значение восстановлено")
            else:
                logger.error("❌ Не удалось восстановить исходное значение")
        
        logger.info("🎉 Тестирование завершено!")

async def main():
    """Основная функция"""
    try:
        tester = PredatorTester()
        await tester.test_all_operations()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 