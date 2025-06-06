#!/usr/bin/env python3
"""
Тестирование структуры системы без API вызовов
"""

import os
import sys
import pandas as pd
import glob

def test_imports():
    """Тестирует импорты всех модулей"""
    print("🧪 Тестирование импортов...")
    
    try:
        from config import CRITERIA_TYPE, PROCESSING_CONFIG, CRITERIA_DIR
        print("✅ config.py импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта config.py: {e}")
        return False
    
    try:
        from sanctions_checker import check_sanctions, apply_sanctions_filter
        print("✅ sanctions_checker.py импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта sanctions_checker.py: {e}")
        return False
    
    try:
        from scoring_system import calculate_nth_score, generate_scoring_summary
        print("✅ scoring_system.py импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта scoring_system.py: {e}")
        return False
    
    try:
        from json_formatter import create_structured_output, format_for_csv_output
        print("✅ json_formatter.py импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта json_formatter.py: {e}")
        return False
    
    try:
        from data_utils import load_companies_data, load_all_criteria_files
        print("✅ data_utils.py импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта data_utils.py: {e}")
        return False
    
    return True

def test_sanctions_checker():
    """Тестирует санкционную проверку"""
    print("\n🚫 Тестирование санкционной проверки...")
    
    from sanctions_checker import check_sanctions
    
    # Тестовые данные
    test_cases = [
        ("Test Company", "A technology company based in California", "https://example.com", False),
        ("RU Tech", "Russian technology company in Moscow", "https://example.ru", True),
        ("China Corp", "Chinese development company", "https://example.cn", True),
        ("Iran Systems", "Software company in Tehran", "", True),
        ("Normal Corp", "Regular tech company", "", False),
    ]
    
    for name, desc, website, should_be_sanctioned in test_cases:
        is_sanctioned, reason = check_sanctions(name, desc, website)
        
        if is_sanctioned == should_be_sanctioned:
            print(f"✅ {name}: {reason}")
        else:
            print(f"❌ {name}: Ожидалось {should_be_sanctioned}, получено {is_sanctioned}")

def test_scoring_system():
    """Тестирует систему скоринга"""
    print("\n📊 Тестирование системы скоринга...")
    
    from scoring_system import calculate_nth_score, generate_scoring_summary
    
    # Тестовые данные
    test_results = {
        "Qualification_Gaming": "Yes",
        "NTH_Gaming_Criterion1": "Passed",
        "NTH_Gaming_Criterion2": "ND", 
        "NTH_Gaming_Criterion3": "Not Passed",
        "Mandatory_Gaming_Criterion1": "Passed",
        "Mandatory_Gaming_Criterion2": "Passed"
    }
    
    score, details = calculate_nth_score(test_results, "Gaming")
    print(f"✅ NTH Score для Gaming: {score:.2f}")
    print(f"   Детали: {details}")
    
    summary = generate_scoring_summary(test_results)
    print(f"✅ Общая сводка: {summary['overall_status']}")

def test_file_structure():
    """Тестирует структуру файлов"""
    print("\n📁 Тестирование структуры файлов...")
    
    from config import INPUT_PATH
    
    # Проверка файла компаний
    if os.path.exists(INPUT_PATH):
        print(f"✅ Файл компаний найден: {INPUT_PATH}")
        
        # Проверка содержимого
        try:
            df = pd.read_csv(INPUT_PATH, nrows=5)
            print(f"   Колонки: {list(df.columns)}")
            print(f"   Записей (примерно): {len(df)}")
        except Exception as e:
            print(f"❌ Ошибка чтения файла компаний: {e}")
    else:
        print(f"❌ Файл компаний не найден: {INPUT_PATH}")

def test_criteria_files():
    """Тестирует доступность файлов критериев"""
    print("\n📋 Тестирование доступности файлов критериев:")
    from config import CRITERIA_DIR
    
    if os.path.exists(CRITERIA_DIR):
        criteria_files = glob.glob(os.path.join(CRITERIA_DIR, "*.csv"))
        print(f"✅ Папка критериев найдена: {CRITERIA_DIR}")
        print(f"✅ Найдено файлов критериев: {len(criteria_files)}")
        for file_path in criteria_files:
            filename = os.path.basename(file_path)
            print(f"   - {filename}")
            
        # Тестируем загрузку всех критериев
        try:
            from data_utils import load_all_criteria_files
            df = load_all_criteria_files()
            print(f"✅ Тест загрузки критериев: {len(df)} записей")
            print(f"   Продукты: {', '.join(df['Product'].unique())}")
        except Exception as e:
            print(f"❌ Ошибка загрузки критериев: {e}")
    else:
        print(f"⚠️  Папка критериев не найдена: {CRITERIA_DIR}")

def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестирования структуры системы\n")
    
    # Тестирование импортов
    if not test_imports():
        print("\n❌ Критические ошибки импортов. Проверьте код.")
        return False
    
    # Тестирование компонентов
    test_sanctions_checker()
    test_scoring_system()
    test_file_structure()
    test_criteria_files()
    
    print(f"\n🎉 Тестирование завершено!")
    print(f"📋 Следующий шаг: создайте .env файл (см. ENV_SETUP.md)")
    
    return True

if __name__ == "__main__":
    main() 