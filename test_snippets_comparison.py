import asyncio
import aiohttp
import os
from dotenv import load_dotenv
from src.pipeline.core import _process_single_company_async
from openai import AsyncOpenAI
from finders.homepage_finder.finder import HomepageFinder
from finders.llm_deep_search_finder.finder import LLMDeepSearchFinder
from description_generator.generator import DescriptionGenerator
from pathlib import Path
import json

async def test_snippets_and_comparison():
    """Тестирует новую функциональность сохранения сниппетов и сравнения URL"""
    load_dotenv()
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    serper_api_key = os.getenv("SERPER_API_KEY")
    
    if not openai_api_key or not serper_api_key:
        print("❌ API ключи не найдены в .env")
        return
    
    print("✅ Тестируем новую функциональность сохранения сниппетов и сравнения URL")
    
    # Создаем клиенты
    openai_client = AsyncOpenAI(api_key=openai_api_key)
    
    # Создаем finder instances
    finder_instances = {
        "homepage_finder": HomepageFinder(serper_api_key, openai_api_key, verbose=True),
        "llm_deep_search_finder": LLMDeepSearchFinder(openai_api_key, verbose=True)
    }
    
    # Создаем description generator
    description_generator = DescriptionGenerator(openai_client)
    
    # Тестируем на проблемной компании
    test_company = 'Collektorskoye agenstvo "ID Collect "'
    print(f"\n🔍 Тестируем компанию: {test_company}")
    
    async with aiohttp.ClientSession() as session:
        result = await _process_single_company_async(
            company_name=test_company,
            openai_client=openai_client,
            aiohttp_session=session,
            sb_client=None,
            serper_api_key=serper_api_key,
            finder_instances=finder_instances,
            description_generator=description_generator,
            llm_config={},
            raw_markdown_output_path=Path("temp"),
            output_csv_path=None,
            output_json_path=None,
            csv_fields=["Company_Name", "Official_Website", "LinkedIn_URL", "Description"],
            company_index=1,
            total_companies=1,
            run_llm_deep_search_pipeline=True,
            run_standard_homepage_finders=True,
            run_domain_check_finder=False
        )
        
        print(f"\n📊 Результат:")
        print(f"URL: {result.get('Official_Website', 'N/A')}")
        print(f"LinkedIn: {result.get('LinkedIn_URL', 'N/A')}")
        
        # Проверяем данные поиска Google
        google_data = result.get('google_search_data')
        if google_data:
            print(f"\n🔍 Google Search Data:")
            print(f"Selected URL: {google_data.get('selected_url', 'N/A')}")
            
            top_5 = google_data.get('top_5_results', [])
            print(f"\n📋 Первые 5 результатов Google ({len(top_5)} найдено):")
            for i, result_item in enumerate(top_5, 1):
                print(f"{i}. {result_item.get('title', 'N/A')}")
                print(f"   URL: {result_item.get('url', 'N/A')}")
                print(f"   Snippet: {result_item.get('snippet', 'N/A')[:100]}...")
                print()
        else:
            print("\n❌ Google Search Data не найдена")
        
        # Проверяем что URL правильный
        expected_urls = ["idcollect.ru", "idfeurasia.com"]
        found_url = result.get('Official_Website', '')
        
        if any(expected in found_url for expected in expected_urls):
            print("✅ УСПЕХ: Найден правильный URL!")
        else:
            print(f"❌ ОШИБКА: Неправильный URL: {found_url}")
        
        # Сохраняем полный результат в JSON для анализа
        with open("test_snippets_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print("\n💾 Полный результат сохранен в test_snippets_result.json")

if __name__ == "__main__":
    asyncio.run(test_snippets_and_comparison()) 