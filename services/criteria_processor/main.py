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
from src.core.processor import run_analysis, run_analysis_optimized, run_analysis_super_optimized
from src.core.parallel_processor import run_parallel_analysis
from src.core.recovery import resume_processing, get_resumable_sessions

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
        '--optimized',
        action='store_true',
        help='Использовать оптимизированный алгоритм: компания за компанией с асинхронностью'
    )
    
    parser.add_argument(
        '--super-optimized',
        action='store_true',
        help='СУПЕР-оптимизированный режим: несколько компаний + асинхронность (самый быстрый)'
    )

    parser.add_argument(
        '--max-concurrent',
        type=int,
        default=12,
        help='Максимальное количество одновременно обрабатываемых компаний (только с --parallel)'
    )
    
    # Circuit Breaker and Recovery arguments
    parser.add_argument(
        '--resume-session',
        type=str,
        help='Возобновить прерванную сессию по ID (например: crit_20241201_143022)'
    )
    
    parser.add_argument(
        '--list-resumable',
        action='store_true',
        help='Показать список сессий которые можно возобновить'
    )
    
    parser.add_argument(
        '--disable-circuit-breaker',
        action='store_true',
        help='Отключить Circuit Breaker (не рекомендуется)'
    )
    
    parser.add_argument(
        '--selected-products',
        type=str,
        help='Comma-separated list of selected products to analyze (e.g., "Product 1,Product 2")'
    )
    
    parser.add_argument(
        '--write-to-hubspot-criteria',
        action='store_true',
        help='Записывать результаты критериев в HubSpot (включено по умолчанию)'
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
        log_info("Новая модульная архитектура с Circuit Breaker и State Management")
        
        # Handle list resumable sessions command
        if args.list_resumable:
            log_info("📋 Поиск возобновляемых сессий...")
            resumable_sessions = get_resumable_sessions()
            
            if not resumable_sessions:
                log_info("❌ Нет сессий для возобновления")
                return
            
            log_info(f"📊 Найдено {len(resumable_sessions)} сессий:")
            for session in resumable_sessions:
                if session.get('can_resume', False):
                    log_info(f"  ✅ {session['session_id']} - {session.get('status', 'unknown')}")
                    log_info(f"     Прогресс: {session.get('progress', {})}")
                    log_info(f"     Обновлено: {session.get('last_updated', 'unknown')}")
                else:
                    log_info(f"  ❌ {session['session_id']} - {session.get('resume_reason', 'cannot resume')}")
            
            log_info("💡 Для возобновления используйте: --resume-session SESSION_ID")
            return
        
        # Handle resume session command
        if args.resume_session:
            log_info(f"🔄 Возобновление сессии: {args.resume_session}")
            
            # Disable circuit breaker if requested
            if args.disable_circuit_breaker:
                log_info("⚠️ Circuit Breaker отключен по запросу")
                from src.utils.config import CIRCUIT_BREAKER_CONFIG
                CIRCUIT_BREAKER_CONFIG['enable_circuit_breaker'] = False
            
            success, message, results = resume_processing(
                session_id=args.resume_session,
                companies_file=args.file,
                load_all_companies=args.all_files,
                use_deep_analysis=args.deep_analysis,
                max_concurrent_companies=args.max_concurrent
            )
            
            if success:
                log_info(f"🎉 {message}")
                log_info(f"📊 Результатов: {len(results) if results else 0}")
            else:
                log_error(f"❌ {message}")
                sys.exit(1)
            
            return
        
        # Логирование выбора файлов для обычного режима
        if args.all_files:
            log_info("РЕЖИМ: Загрузка ВСЕХ файлов компаний из папки data/")
        elif args.file:
            log_info(f"РЕЖИМ: Загрузка конкретного файла: {args.file}")
        else:
            log_info("РЕЖИМ: Загрузка файла по умолчанию из конфигурации")
        
        # Disable circuit breaker if requested
        if args.disable_circuit_breaker:
            log_info("⚠️ Circuit Breaker отключен по запросу")
            from src.utils.config import CIRCUIT_BREAKER_CONFIG
            CIRCUIT_BREAKER_CONFIG['enable_circuit_breaker'] = False
        
        # Parse selected products
        selected_products_list = None
        if args.selected_products:
            selected_products_list = [p.strip() for p in args.selected_products.split(',') if p.strip()]
            log_info(f"🎯 Будут обрабатываться только выбранные продукты: {selected_products_list}")
        
        # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ HUBSPOT ПАРАМЕТРА
        log_info(f"🔍 HUBSPOT ПАРАМЕТР В MAIN.PY:")
        log_info(f"   🔗 args.write_to_hubspot_criteria = {args.write_to_hubspot_criteria}")
        log_info(f"   📝 Тип параметра: {type(args.write_to_hubspot_criteria)}")
        
        # Валидация конфигурации
        log_info("Проверяем конфигурацию...")
        validate_config()
        
        # Запуск анализа с параметрами
        log_info("Начинаем анализ...")
        
        if args.super_optimized:
            log_info(f"🔥 СУПЕР-ОПТИМИЗИРОВАННЫЙ РЕЖИМ: {args.max_concurrent} компаний + асинхронность")
            results = run_analysis_super_optimized(
                companies_file=args.file,
                load_all_companies=args.all_files,
                session_id=args.session_id,
                use_deep_analysis=args.deep_analysis,
                max_concurrent_companies=args.max_concurrent,
                selected_products=selected_products_list
            )
        elif args.optimized:
            log_info("🚀 ОПТИМИЗИРОВАННЫЙ РЕЖИМ: компания за компанией с асинхронностью")
            results = run_analysis_optimized(
                companies_file=args.file,
                load_all_companies=args.all_files,
                session_id=args.session_id,
                use_deep_analysis=args.deep_analysis,
                selected_products=selected_products_list
            )
        elif args.parallel:
            log_info(f"🚀 ПАРАЛЛЕЛЬНЫЙ РЕЖИМ: max_concurrent={args.max_concurrent}")
            log_info(f"🔗 ПЕРЕДАЕМ В run_parallel_analysis: write_to_hubspot_criteria={args.write_to_hubspot_criteria}")
            results = run_parallel_analysis(
                companies_file=args.file,
                load_all_companies=args.all_files,
                session_id=args.session_id,
                use_deep_analysis=args.deep_analysis,
                max_concurrent_companies=args.max_concurrent,
                selected_products=selected_products_list,
                write_to_hubspot_criteria=args.write_to_hubspot_criteria
            )
        else:
            log_info("🐌 ОБЫЧНЫЙ РЕЖИМ: последовательная обработка")
            results = run_analysis(
                companies_file=args.file,
                load_all_companies=args.all_files,
                session_id=args.session_id,
                use_deep_analysis=args.deep_analysis,
                selected_products=selected_products_list
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