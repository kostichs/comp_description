#!/usr/bin/env python3
"""
Тестовый скрипт для проверки нормализации названий компаний.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.input_validators import normalize_company_name, detect_encoding_issues

def test_normalization():
    """Тестирует нормализацию названий компаний с проблемами кодировки."""
    
    test_cases = [
        # Эстонские компании
        "Bourse OÃœ",
        "PMTECH ENGINEERING OÃœ", 
        "Privacy Technologies OÃœ",
        
        # Немецкие компании
        "OKOS VÃ–LGY Kft",
        
        # Французские компании
        "Innova Co. S.Ã  r.l.",
        
        # Кириллица (поврежденная)
        "ÐÑ‡ÐµÑ‚Ð½Ð¸ÐºÐ¾Ð² Ð˜Ð²Ð°Ð½ Ð'Ð°ÑÐ¸Ð»ÑŒÐµÐ²Ð¸Ñ‡",
        "Нуриддин",
        
        # Нормальные названия для сравнения
        "Microsoft Corporation",
        "Apple Inc.",
        "Google LLC",
        
        # Смешанные проблемы
        '"Quoted Company Name"',
        "  Spaced Company  ",
        "Company&nbsp;with&nbsp;HTML",
        "Café François",
        "Müller GmbH",
        "José María S.A.",
    ]
    
    print("=== Тест нормализации названий компаний ===\n")
    
    for original in test_cases:
        print(f"Исходное название: '{original}'")
        
        # Проверяем на проблемы с кодировкой
        issues = detect_encoding_issues(original)
        if issues:
            print(f"  Обнаруженные проблемы: {', '.join(issues)}")
        
        # Нормализуем для поиска
        normalized = normalize_company_name(original, for_search=True)
        
        if normalized != original:
            print(f"  Нормализованное: '{normalized}'")
            print(f"  Изменения: ДА")
        else:
            print(f"  Изменения: НЕТ")
        
        print(f"  Длина: {len(original)} -> {len(normalized)}")
        print()

if __name__ == "__main__":
    test_normalization() 