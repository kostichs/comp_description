#!/usr/bin/env python3
"""
Тестовый скрипт для проверки CSV утилит с нормализацией кодировки.
"""

import sys
import os
import tempfile
import csv
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.csv_utils import (
    detect_file_encoding, 
    read_csv_with_normalization, 
    write_csv_with_proper_encoding,
    analyze_csv_encoding_issues
)

def create_test_csv_with_encoding_issues():
    """Создает тестовый CSV файл с проблемами кодировки."""
    
    test_data = [
        {'Company Name': 'Bourse OÃœ', 'Industry': 'Technology', 'Country': 'Estonia'},
        {'Company Name': 'OKOS VÃ–LGY Kft', 'Industry': 'Undefined', 'Country': 'Hungary'},
        {'Company Name': 'Innova Co. S.Ã  r.l.', 'Industry': 'Gaming', 'Country': 'France'},
        {'Company Name': 'PMTECH ENGINEERING OÃœ', 'Industry': 'Technology', 'Country': 'Estonia'},
        {'Company Name': 'Privacy Technologies OÃœ', 'Industry': 'Technology', 'Country': 'Estonia'},
        {'Company Name': '"Quoted Company"', 'Industry': 'Software', 'Country': 'USA'},
        {'Company Name': '  Spaced Company  ', 'Industry': 'Consulting', 'Country': 'UK'},
        {'Company Name': 'Normal Company Inc.', 'Industry': 'Finance', 'Country': 'USA'},
    ]
    
    # Создаем временный файл
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8')
    
    try:
        writer = csv.DictWriter(temp_file, fieldnames=['Company Name', 'Industry', 'Country'])
        writer.writeheader()
        writer.writerows(test_data)
        temp_file.close()
        
        print(f"Created test CSV file: {temp_file.name}")
        return temp_file.name
        
    except Exception as e:
        print(f"Error creating test CSV: {e}")
        return None

def test_csv_utilities():
    """Тестирует CSV утилиты."""
    
    print("=== Тест CSV утилит с нормализацией кодировки ===\n")
    
    # Создаем тестовый файл
    test_file = create_test_csv_with_encoding_issues()
    if not test_file:
        print("Failed to create test file")
        return
    
    try:
        # 1. Определение кодировки
        print("1. Определение кодировки файла:")
        encoding = detect_file_encoding(test_file)
        print(f"   Определенная кодировка: {encoding}\n")
        
        # 2. Анализ проблем с кодировкой
        print("2. Анализ проблем с кодировкой:")
        analysis = analyze_csv_encoding_issues(test_file)
        print(f"   Всего строк: {analysis['total_rows']}")
        print(f"   Строк с проблемами: {analysis['rows_with_issues']}")
        print(f"   Общие проблемы: {analysis['common_issues']}")
        if analysis['suggested_fixes']:
            print(f"   Рекомендации: {analysis['suggested_fixes']}")
        print()
        
        # 3. Чтение без нормализации
        print("3. Чтение без нормализации:")
        data_raw = read_csv_with_normalization(test_file, normalize_names=False)
        for i, row in enumerate(data_raw[:3]):  # Показываем первые 3 строки
            print(f"   Строка {i+1}: {row['Company Name']}")
        print()
        
        # 4. Чтение с нормализацией
        print("4. Чтение с нормализацией:")
        data_normalized = read_csv_with_normalization(test_file, normalize_names=True)
        for i, row in enumerate(data_normalized[:3]):  # Показываем первые 3 строки
            print(f"   Строка {i+1}: {row['Company Name']}")
        print()
        
        # 5. Сравнение результатов
        print("5. Сравнение результатов:")
        for i in range(min(len(data_raw), len(data_normalized))):
            raw_name = data_raw[i]['Company Name']
            norm_name = data_normalized[i]['Company Name']
            if raw_name != norm_name:
                print(f"   Изменение {i+1}: '{raw_name}' -> '{norm_name}'")
        print()
        
        # 6. Запись нормализованных данных
        output_file = test_file.replace('.csv', '_normalized.csv')
        print(f"6. Запись нормализованных данных в {output_file}:")
        write_csv_with_proper_encoding(data_normalized, output_file)
        print(f"   Записано {len(data_normalized)} строк")
        print()
        
        # 7. Проверка результата
        print("7. Проверка записанного файла:")
        final_data = read_csv_with_normalization(output_file, normalize_names=False)
        print(f"   Прочитано {len(final_data)} строк из нормализованного файла")
        for i, row in enumerate(final_data[:3]):
            print(f"   Строка {i+1}: {row['Company Name']}")
        
        # Очистка
        os.unlink(test_file)
        os.unlink(output_file)
        print(f"\nТестовые файлы удалены")
        
    except Exception as e:
        print(f"Error during testing: {e}")
        # Очистка в случае ошибки
        try:
            os.unlink(test_file)
        except:
            pass

if __name__ == "__main__":
    test_csv_utilities() 