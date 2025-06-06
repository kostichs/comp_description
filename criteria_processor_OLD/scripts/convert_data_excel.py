#!/usr/bin/env python3
"""
Скрипт для конвертации Excel файлов в CSV в папке data
"""

import pandas as pd
import os

def convert_excel_to_csv():
    """Конвертирует Excel файл в CSV"""
    excel_file = "data/conf_wgs.xlsx"
    csv_file = "data/companies.csv"
    
    if not os.path.exists(excel_file):
        print(f"❌ Файл не найден: {excel_file}")
        return False
    
    print(f"📊 Конвертируем {excel_file} в {csv_file}")
    
    try:
        # Читаем Excel
        df = pd.read_excel(excel_file)
        
        # Сохраняем CSV
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        
        print(f"✅ Успешно конвертировано: {len(df)} компаний")
        print(f"📄 Создан файл: {csv_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

if __name__ == "__main__":
    convert_excel_to_csv() 