#!/usr/bin/env python3
"""
Тест загрузки predator из файла
"""

import os
import sys
import logging
from pathlib import Path

# Добавляем корневую папку проекта в sys.path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_io import load_and_prepare_company_names

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_predator_loading():
    """Тестируем загрузку predator из файла"""
    
    # Проверяем последнюю сессию
    test_file = "output/sessions/20250613_164826_criteria_analis19/input_criteria_analis19.csv"
    
    logger.info(f"🔍 Тестируем загрузку predator из файла: {test_file}")
    
    # Загружаем компании
    companies = load_and_prepare_company_names(test_file)
    
    if companies:
        logger.info(f"✅ Загружено {len(companies)} компаний:")
        for i, company in enumerate(companies):
            logger.info(f"   {i+1}. {company}")
            
            predator = company.get('predator')
            if predator:
                logger.info(f"      ✅ PREDATOR найден: '{predator}' (тип: {type(predator)})")
            else:
                logger.error(f"      ❌ PREDATOR не найден!")
    else:
        logger.error("❌ Не удалось загрузить компании")

if __name__ == "__main__":
    test_predator_loading() 