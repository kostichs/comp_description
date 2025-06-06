#!/usr/bin/env python3
"""
Создание тестового файла с частью компаний
"""

import pandas as pd

def create_test_file():
    """Создает тестовый файл с 50 компаниями"""
    try:
        df = pd.read_csv('data/companies.csv')
        test_df = df.head(50)
        test_df.to_csv('data/test_companies.csv', index=False, encoding='utf-8-sig')
        print(f"✅ Создан тестовый файл: {len(test_df)} компаний")
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

if __name__ == "__main__":
    create_test_file() 