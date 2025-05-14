import asyncio
import aiohttp
import os
from dotenv import load_dotenv
from pathlib import Path

# Импорт компонентов системы
from finders import (
    #WikidataFinder, 
    # DomainFinder, 
    # GoogleFinder, 
    # WikipediaFinder,
    # LinkedInFinder,
    # LLMSearchFinder
    HomepageFinder,
    LinkedInFinderNew,
    LLMDeepSearchFinder
)
from orchestrator import PipelineOrchestrator
from result_processor import ResultProcessor
from description_generator import DescriptionGenerator
from utils import load_company_names, create_output_dirs

def print_company_results(company_result):
    """Выводит результаты поиска для одной компании в консоль"""
    company_name = company_result.get("company", "Неизвестная компания")
    print(f"\n{'='*50}")
    print(f"КОМПАНИЯ: {company_name}")
    print(f"{'='*50}")
    
    # Поиск результатов по разным типам финдеров
    homepage_result = None
    linkedin_result = None
    deep_search_report = None
    deep_search_sources = []
    
    for result in company_result.get("results", []):
        source = result.get("source", "")
        if source == "linkedin_finder" and result.get("result"):
            linkedin_result = result.get("result")
        elif source == "llm_deep_search" and result.get("result"):
            deep_search_report = result.get("result")
            deep_search_sources = result.get("sources", [])
        elif "homepage_finder" not in source and result.get("result"):
            homepage_result = result.get("result")
    
    # Вывод только конечных результатов
    if homepage_result:
        print(f"Домашняя страница: {homepage_result}")
    else:
        print("Домашняя страница: Не найдена")
        
    if linkedin_result:
        print(f"LinkedIn: {linkedin_result}")
    else:
        print("LinkedIn: Не найден")
    
    if deep_search_report:
        print(f"LLM Deep Search: Получен отчет ({len(deep_search_report)} символов)")
        if deep_search_sources:
            print(f"Источники ({len(deep_search_sources)}):")
            # Выводим до 5 источников с названием и URL
            for i, source in enumerate(deep_search_sources[:5], 1):
                title = source.get("title", "Без названия")
                url = source.get("url", "")
                print(f"  {i}. {title[:70]}... - {url}")
            
            # Если источников больше 5, сообщаем об этом
            if len(deep_search_sources) > 5:
                print(f"  ... и еще {len(deep_search_sources) - 5} источников")
        else:
            print("Источники: Не найдены")
    else:
        print("LLM Deep Search: Не проводился или не дал результатов")
    
    if "description" in company_result:
        print("\nОПИСАНИЕ:")
        print(f"{company_result['description']}")
    
    print(f"{'='*50}\n")

async def main():
    # Загрузка переменных окружения
    load_dotenv()
    
    # API ключи
    serper_api_key = os.getenv("SERPER_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not serper_api_key:
        print("Ошибка: SERPER_API_KEY не найден в .env файле")
        exit(1)
        
    if not openai_api_key:
        print("Ошибка: OPENAI_API_KEY не найден в .env файле")
        exit(1)
    
    # Создаем необходимые директории
    create_output_dirs()
    
    # Путь к файлу с компаниями
    input_file = "input/part2.xlsx"
    output_file_json = "output/results.json"
    output_file_excel = "output/results.xlsx"
    
    # Загрузка имен компаний
    company_names = load_company_names(input_file)
    if not company_names:
        print(f"Не удалось загрузить компании из {input_file}")
        exit(1)
        
    print(f"Загружено {len(company_names)} компаний из {input_file}")
    
    # Создаем HTTP сессию
    async with aiohttp.ClientSession() as session:
        # Инициализация финдеров с отключенным подробным логированием
        finders = [
            # WikidataFinder(),
            # DomainFinder(),
            # GoogleFinder(serper_api_key),
            # WikipediaFinder(),
            # LinkedInFinder(),
            # LLMSearchFinder(openai_api_key)
            HomepageFinder(serper_api_key, openai_api_key, verbose=False),
            LinkedInFinderNew(serper_api_key, verbose=False),
            LLMDeepSearchFinder(openai_api_key, verbose=False)
        ]
        
        # Специфические аспекты для LLM Deep Search
        deep_search_aspects = [
            "company founding year",
            "headquarters location (city and country)",
            "names of founders",
            "latest reported annual revenue (specify currency and year)",
            "approximate number of employees",
            "key products, services, or technologies",
            "main competitors"
        ]
        
        # Инициализация оркестратора
        orchestrator = PipelineOrchestrator(finders)
        
        # Инициализация генератора описаний
        description_generator = DescriptionGenerator(openai_api_key)
        
        # Обработка компаний
        print("Начинаем поиск информации о компаниях...")
        
        # Обрабатываем компании пакетами для оптимизации
        batch_size = 3  # Уменьшаем размер пакета из-за LLM Deep Search
        results = []
        
        for i in range(0, len(company_names), batch_size):
            batch = company_names[i:i+batch_size]
            print(f"\nОбрабатываем компании {i+1}-{min(i+batch_size, len(company_names))} из {len(company_names)}...")
            
            # Поиск информации о компаниях
            batch_results = await orchestrator.process_batch(
                batch, 
                session, 
                openai_api_key=openai_api_key,
                specific_aspects=deep_search_aspects
            )
            
            # Вывод только конечных результатов для каждой компании
            print("\nРезультаты поиска:")
            for result in batch_results:
                print_company_results(result)
            
            # Генерация описаний
            enriched_batch = await description_generator.generate_batch_descriptions(batch_results)
            results.extend(enriched_batch)
            
            # Промежуточное сохранение результатов
            ResultProcessor.save_to_json(results, output_file_json)
        
        # Сохранение финальных результатов
        ResultProcessor.save_to_json(results, output_file_json)
        ResultProcessor.save_to_excel(results, output_file_excel)
        
        # Вывод статистики
        ResultProcessor.print_stats(results)
        
        print(f"\nРезультаты сохранены в:")
        print(f"- JSON: {output_file_json}")
        print(f"- Excel: {output_file_excel}")

if __name__ == "__main__":
    asyncio.run(main()) 