#!/usr/bin/env python3
"""
Тест валидации названий компаний
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.input_validators import validate_company_name, is_generic_term

def test_validation():
    """Тестирует валидацию названий компаний"""
    
    test_cases = [
        # (название, ожидаемый_результат, описание)
        ("فرص عمل عن بعد", False, "Арабский термин 'удаленная работа'"),
        ("Remote Job Opportunities", False, "Английский термин 'возможности удаленной работы'"),
        ("Google", True, "Реальное название компании"),
        ("Microsoft Corporation", True, "Реальное название компании с Corporation"),
        ("job opportunities", False, "Общий термин работа"),
        ("career", False, "Карьера - общий термин"),
        ("удаленная работа", False, "Русский термин удаленная работа"),
        ("работа на дому", False, "Русский термин работа на дому"),
        ("Apple Inc", True, "Реальная компания"),
        ("فرص وظيفية", False, "Арабский термин возможности работы"),
        ("123", False, "Только цифры"),
        ("", False, "Пустая строка"),
        ("A", False, "Слишком короткое"),
        ("OpenAI", True, "Реальная компания"),
        ("trabajo remoto", False, "Испанский термин удаленная работа"),
        ("freelance opportunities", False, "Фриланс возможности"),
        ("Remote Work Solutions Ltd", False, "Содержит 'remote work'"),
        ("Tesla Motors", True, "Реальная компания"),
        ("employment agency", False, "Агентство занятости")
    ]
    
    print("Тестирование валидации названий компаний:")
    print("=" * 60)
    
    failed_tests = 0
    for company_name, expected_valid, description in test_cases:
        is_valid, error_msg = validate_company_name(company_name)
        
        status = "✓" if is_valid == expected_valid else "✗"
        if is_valid != expected_valid:
            failed_tests += 1
        
        print(f"{status} {company_name:25} | Ожидается: {'✓' if expected_valid else '✗'} | Результат: {'✓' if is_valid else '✗'} | {description}")
        if not is_valid and error_msg:
            print(f"   Ошибка: {error_msg}")
    
    print("=" * 60)
    print(f"Тестов пройдено: {len(test_cases) - failed_tests}/{len(test_cases)}")
    if failed_tests == 0:
        print("✓ Все тесты пройдены успешно!")
    else:
        print(f"✗ Провалено тестов: {failed_tests}")
    
    return failed_tests == 0

def test_generic_terms():
    """Тестирует функцию is_generic_term отдельно"""
    print("\n\nТестирование функции is_generic_term:")
    print("=" * 60)
    
    generic_terms = [
        "فرص عمل عن بعد",
        "remote work", 
        "job opportunities",
        "career opportunities",
        "удаленная работа",
        "trabajo remoto",
        "emploi à distance"
    ]
    
    real_companies = [
        "Google",
        "Microsoft", 
        "Apple",
        "Tesla",
        "OpenAI"
    ]
    
    print("Общие термины (должны быть распознаны как общие):")
    for term in generic_terms:
        result = is_generic_term(term)
        status = "✓" if result else "✗"
        print(f"{status} {term:30} | Общий термин: {result}")
    
    print("\nНазвания реальных компаний (НЕ должны быть общими терминами):")
    for company in real_companies:
        result = is_generic_term(company)
        status = "✓" if not result else "✗"
        print(f"{status} {company:30} | Общий термин: {result}")

if __name__ == "__main__":
    success = test_validation()
    test_generic_terms()
    
    if success:
        print("\n🎉 Валидация работает корректно!")
    else:
        print("\n⚠️  Есть проблемы с валидацией, требуется доработка")
        sys.exit(1) 