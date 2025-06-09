#!/usr/bin/env python3
"""
Система анализа критериев компаний - Новая архитектура
Главная точка входа в приложение
"""

import sys
import os
import argparse

# Добавляем src в путь для импортов
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.config import validate_config
from src.utils.logging import setup_logging, log_info, log_error
from src.core.processor import run_analysis
from src.core.parallel_processor import run_parallel_analysis

def parse_arguments():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(description='Система анализа критериев компаний')
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--file', '-f',
        type=str,
        help='Путь к конкретному файлу компаний (CSV/Excel): data/companies.csv или data/companies.xlsx'
    )
    group.add_argument(
        '--all-files', '-a',
        action='store_true',
        help='Загрузить ВСЕ CSV/Excel файлы из папки data/'
    )
    
    parser.add_argument(
        '--session-id', '-s',
        type=str,
        help='ID сессии для создания отдельной папки результатов'
    )

    parser.add_argument(
        '--deep-analysis',
        action='store_true',
        help='Включить глубокий анализ с использованием ScrapingBee'
    )

    parser.add_argument(
        '--parallel',
        action='store_true',
        help='Включить параллельную обработку компаний (быстрее, но больше нагрузка на API)'
    )

    parser.add_argument(
        '--max-concurrent',
        type=int,
        default=12,
        help='Максимальное количество одновременно обрабатываемых компаний (только с --parallel)'
    )
    
    return parser.parse_args()

def main():
    """Главная функция приложения"""
    try:
        # Парсинг аргументов
        args = parse_arguments()
        
        # Настройка логирования
        setup_logging()
        
        log_info("Запуск системы анализа критериев компаний v2.0")
        log_info("Новая модульная архитектура")
        
        # Логирование выбора файлов
        if args.all_files:
            log_info("РЕЖИМ: Загрузка ВСЕХ файлов компаний из папки data/")
        elif args.file:
            log_info(f"РЕЖИМ: Загрузка конкретного файла: {args.file}")
        else:
            log_info("РЕЖИМ: Загрузка файла по умолчанию из конфигурации")
        
        # Валидация конфигурации
        log_info("Проверяем конфигурацию...")
        validate_config()
        
        # Запуск анализа с параметрами
        log_info("Начинаем анализ...")
        
        if args.parallel:
            log_info(f"🚀 ПАРАЛЛЕЛЬНЫЙ РЕЖИМ: max_concurrent={args.max_concurrent}")
            results = run_parallel_analysis(
                companies_file=args.file,
                load_all_companies=args.all_files,
                session_id=args.session_id,
                use_deep_analysis=args.deep_analysis,
                max_concurrent_companies=args.max_concurrent
            )
        else:
            log_info("🐌 ОБЫЧНЫЙ РЕЖИМ: последовательная обработка")
            results = run_analysis(
                companies_file=args.file,
                load_all_companies=args.all_files,
                session_id=args.session_id,
                use_deep_analysis=args.deep_analysis
            )
        
        log_info(f"Анализ завершен успешно! Обработано компаний: {len(results)}")
        
    except KeyboardInterrupt:
        log_info("Анализ прерван пользователем")
        sys.exit(1)
    except Exception as e:
        log_error(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 