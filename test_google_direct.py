import asyncio
import logging
import os
import aiohttp
from dotenv import load_dotenv
from finders.homepage_finder.finder import HomepageFinder
from finders.homepage_finder.google_search import search_google

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_google_direct():
    """Тест прямого поиска в Google"""
    
    # Загружаем переменные окружения
    load_dotenv()
    serper_api_key = os.getenv("SERPER_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not serper_api_key:
        print("SERPER_API_KEY not found in environment")
        return
    
    if not openai_api_key:
        print("OPENAI_API_KEY not found in environment")
        return
    
    # Создаем HTTP сессию
    async with aiohttp.ClientSession() as session:
        # Создаем Homepage Finder
        homepage_finder = HomepageFinder(
            serper_api_key=serper_api_key,
            openai_api_key=openai_api_key
        )
        
        # Тестируем проблемную компанию
        test_company = "Bourse OÜ"
        
        print(f"\nTesting Google search results for: {test_company}")
        
        # Сначала посмотрим что возвращает Google напрямую
        google_results = await search_google(test_company, session, serper_api_key)
        if google_results and "organic" in google_results:
            print(f"\nGoogle organic results (in order):")
            for i, result in enumerate(google_results["organic"]):
                url = result.get('link', '')
                title = result.get('title', '')
                print(f"{i+1}. {url}")
                print(f"   Title: {title}")
                print()
        
        # Теперь посмотрим что выберет наш алгоритм
        try:
            result = await homepage_finder.find(
                test_company,
                session=session,
                serper_api_key=serper_api_key
            )
            
            print(f"Our algorithm result: {result}")
            
            if result and result.get("result"):
                print(f"✅ Found URL via {result.get('source')}: {result['result']}")
            else:
                print("❌ No URL found")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_google_direct()) 