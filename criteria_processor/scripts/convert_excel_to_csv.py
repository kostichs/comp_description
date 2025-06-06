#!/usr/bin/env python3
"""
Скрипт для конвертации Excel файлов в CSV в папке criteria
"""

import os
import sys
import pandas as pd
import glob
from pathlib import Path

def convert_excel_file_to_csv(excel_file_path):
    """Конвертирует один Excel файл в CSV"""
    print(f"📊 Обрабатываем файл: {os.path.basename(excel_file_path)}")
    
    try:
        # Читаем Excel файл
        df = pd.read_excel(excel_file_path)
        
        # Создаем путь для CSV файла
        base_name = os.path.splitext(os.path.basename(excel_file_path))[0]
        csv_file_path = os.path.join(os.path.dirname(excel_file_path), f"Criteria_{base_name}.csv")
        
        # Сохраняем в CSV
        df.to_csv(csv_file_path, index=False, encoding='utf-8-sig')
        
        print(f"✅ Конвертировано: {os.path.basename(excel_file_path)} → {os.path.basename(csv_file_path)}")
        print(f"📋 Строк: {len(df)}, Колонок: {len(df.columns)}")
        
        # Показываем первые несколько строк для проверки
        print("🔍 Превью данных:")
        print(df.head().to_string())
        print("-" * 60)
        
        return csv_file_path
        
    except Exception as e:
        print(f"❌ Ошибка при обработке {excel_file_path}: {e}")
        return None

def main():
    """Главная функция"""
    # Определяем путь к папке criteria
    criteria_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "criteria")
    
    if not os.path.exists(criteria_dir):
        print(f"❌ Папка criteria не найдена: {criteria_dir}")
        return False
    
    print(f"📁 Ищем Excel файлы в: {criteria_dir}")
    
    # Ищем все Excel файлы
    excel_files = glob.glob(os.path.join(criteria_dir, "*.xlsx")) + \
                  glob.glob(os.path.join(criteria_dir, "*.xls"))
    
    if not excel_files:
        print("✅ Excel файлов не найдено")
        return True
    
    print(f"📊 Найдено Excel файлов: {len(excel_files)}")
    
    converted = 0
    failed = 0
    
    for excel_file in excel_files:
        result = convert_excel_file_to_csv(excel_file)
        if result:
            converted += 1
        else:
            failed += 1
    
    print("=" * 60)
    print(f"📊 Итоги конвертации:")
    print(f"✅ Успешно конвертировано: {converted}")
    print(f"❌ Ошибок: {failed}")
    
    if converted > 0:
        print("\n💡 Рекомендации:")
        print("1. Проверьте содержимое новых CSV файлов")
        print("2. Убедитесь что структура соответствует ожидаемой")
        print("3. После проверки можно удалить исходные Excel файлы")
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 