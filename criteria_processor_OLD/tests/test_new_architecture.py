#!/usr/bin/env python3
"""
Тестирование новой архитектуры системы анализа критериев
"""

import sys
import os

# Добавляем корневую папку проекта в путь для импортов
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

def test_imports():
    """Тестируем импорты всех модулей"""
    print("🧪 Тестируем импорты модулей...")
    
    try:
        # Тестируем utils
        from src.utils.config import validate_config, CRITERIA_TYPE
        from src.utils.logging import setup_logging, log_info
        print("✅ Utils модули импортированы")
        
        # Тестируем data
        from src.data.loaders import load_companies_data, load_all_criteria_files
        from src.data.encodings import detect_encoding, load_csv_with_encoding
        from src.data.savers import save_results
        print("✅ Data модули импортированы")
        
        # Тестируем external
        from src.external.serper import perform_google_search, extract_website_from_company
        from src.external.openai_client import ask_openai_structured, load_prompts
        print("✅ External модули импортированы")
        
        # Тестируем criteria
        from src.criteria.base import get_structured_response, SCHEMAS
        from src.criteria.general import check_general_criteria
        from src.criteria.qualification import check_qualification_questions
        from src.criteria.mandatory import check_mandatory_criteria
        from src.criteria.nth import check_nth_criteria
        print("✅ Criteria модули импортированы")
        
        # Тестируем formatters
        from src.formatters.json_format import create_structured_output
        from src.formatters.csv_format import format_for_csv_output
        print("✅ Formatters модули импортированы")
        
        # Тестируем core
        from src.core.processor import run_analysis, process_company
        print("✅ Core модули импортированы")
        
        return True
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False

def test_config():
    """Тестируем конфигурацию"""
    print("\n🧪 Тестируем конфигурацию...")
    
    try:
        from src.utils.config import validate_config, CRITERIA_TYPE, BASE_DIR
        
        print(f"📁 BASE_DIR: {BASE_DIR}")
        print(f"🎯 CRITERIA_TYPE: {CRITERIA_TYPE}")
        
        validate_config()
        print("✅ Конфигурация валидна")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка конфигурации: {e}")
        return False

def test_data_loading():
    """Тестируем загрузку данных"""
    print("\n🧪 Тестируем загрузку данных...")
    
    try:
        from src.data.loaders import load_companies_data, load_all_criteria_files
        
        # Тестируем загрузку компаний
        companies_df = load_companies_data()
        print(f"✅ Загружено компаний: {len(companies_df)}")
        
        # Тестируем загрузку критериев
        criteria_df = load_all_criteria_files()
        print(f"✅ Загружено критериев: {len(criteria_df)}")
        
        # Показываем типы критериев
        criteria_types = criteria_df['Criteria Type'].unique()
        print(f"📊 Типы критериев: {', '.join(criteria_types)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")
        return False

def main():
    """Главная функция тестирования"""
    print("🚀 Тестирование новой архитектуры системы анализа критериев")
    print("=" * 60)
    
    tests = [
        ("Импорты модулей", test_imports),
        ("Конфигурация", test_config),
        ("Загрузка данных", test_data_loading)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}:")
        if test_func():
            passed += 1
        else:
            print(f"❌ Тест '{test_name}' провален")
    
    print("\n" + "=" * 60)
    print(f"📊 Результаты тестирования: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены! Новая архитектура готова к использованию.")
        return True
    else:
        print("⚠️ Некоторые тесты провалены. Требуется исправление.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 