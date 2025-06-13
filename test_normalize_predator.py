#!/usr/bin/env python3
"""
Тест normalize_and_remove_duplicates с predator колонкой
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Добавляем корневую папку проекта в sys.path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from normalize_urls import normalize_and_remove_duplicates

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

async def test_normalize_with_predator():
    """Тестируем normalize_and_remove_duplicates с predator"""
    
    # Создаем тестовый файл с predator колонкой
    test_data = """Company_Name,Official_Website,predator
Wargaming Group Limited,wargaming.com,383
Test Company 2,example.com,999"""
    
    test_file = "test_input_with_predator.csv"
    output_file = "test_output_with_predator.csv"
    
    # Записываем тестовый файл
    with open(test_file, 'w') as f:
        f.write(test_data)
    
    logger.info(f"🔍 Тестируем normalize_and_remove_duplicates с predator колонкой")
    
    try:
        # Запускаем normalize_and_remove_duplicates
        result_file, details = await normalize_and_remove_duplicates(
            test_file, 
            output_file,
            session_id_for_metadata=None
        )
        
        if result_file:
            logger.info(f"✅ Обработка успешна: {result_file}")
            logger.info(f"   Детали: {details}")
            
            # Читаем результат
            with open(result_file, 'r') as f:
                result_content = f.read()
            
            logger.info(f"📄 Содержимое результата:")
            logger.info(result_content)
            
            # Проверяем есть ли predator колонка
            if 'predator' in result_content:
                logger.info("✅ PREDATOR колонка сохранена!")
                
                # Проверяем есть ли значение 383
                if '383' in result_content:
                    logger.info("✅ Значение predator=383 сохранено!")
                else:
                    logger.error("❌ Значение predator=383 потеряно!")
            else:
                logger.error("❌ PREDATOR колонка потеряна!")
                
        else:
            logger.error(f"❌ Ошибка обработки: {details}")
    finally:
        # Очистка тестовых файлов
        for f in [test_file, output_file]:
            if os.path.exists(f):
                os.remove(f)
                logger.info(f"Удален тестовый файл: {f}")

if __name__ == "__main__":
    asyncio.run(test_normalize_with_predator()) 