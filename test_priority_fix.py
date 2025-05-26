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

async def test_priority_fix():
    """Тестирует что Homepage Finder теперь имеет приоритет"""
    load_dotenv()
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    serper_api_key = os.getenv("SERPER_API_KEY")
    
    if not openai_api_key or not serper_api_key:
        print("❌ API ключи не найдены в .env")
        return
    
    print("✅ Тестируем новую логику приоритета")
    
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
        
        # Проверяем что URL правильный
        expected_urls = ["idcollect.ru", "idfeurasia.com"]
        found_url = result.get('Official_Website', '')
        
        if any(expected in found_url for expected in expected_urls):
            print("✅ УСПЕХ: Найден правильный URL!")
        else:
            print(f"❌ ОШИБКА: Неправильный URL: {found_url}")

if __name__ == "__main__":
    asyncio.run(test_priority_fix()) 