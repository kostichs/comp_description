import asyncio
import aiohttp
import os
import logging
from dotenv import load_dotenv
from finders.linkedin_finder.finder import LinkedInFinder
from finders.linkedin_finder.google_search import search_google

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_linkedin_finder():
    # Загрузка переменных окружения
    load_dotenv()
    serper_api_key = os.getenv('SERPER_API_KEY')
    
    if not serper_api_key:
        logger.error("SERPER_API_KEY не найден в .env файле")
        return
    
    # Создаем финдер
    finder = LinkedInFinder(serper_api_key, verbose=True)
    
    # Тестовые компании
    test_companies = ["Microsoft", "Apple", "Google", "Tesla", "Amazon"]
    
    # Создаем HTTP сессию
    async with aiohttp.ClientSession() as session:
        for company in test_companies:
            logger.info(f"Поиск LinkedIn для компании: {company}")
            
            # Прямой поиск через search_google
            logger.info(f"1. Тестируем прямой запрос search_google для {company}")
            search_results = await search_google(company, session, serper_api_key)
            
            if search_results and "organic" in search_results:
                logger.info(f"Найдено {len(search_results['organic'])} результатов в поиске")
                
                # Показываем первые 3 LinkedIn результата, если они есть
                linkedin_count = 0
                for i, result in enumerate(search_results["organic"]):
                    url = result.get("link", "")
                    if "linkedin.com/company/" in url:
                        linkedin_count += 1
                        logger.info(f"LinkedIn результат #{linkedin_count}: {url}")
                        if linkedin_count >= 3:
                            break
                
                if linkedin_count == 0:
                    logger.info("LinkedIn ссылок не найдено в результатах поиска")
            else:
                logger.error(f"Ошибка при поиске через Google для {company}")
            
            # Поиск через финдер
            logger.info(f"2. Тестируем LinkedInFinder.find() для {company}")
            result = await finder.find(company, session=session, serper_api_key=serper_api_key)
            
            if result["result"]:
                logger.info(f"LinkedInFinder нашел: {result['result']}")
                if "snippet" in result and result["snippet"]:
                    logger.info(f"Сниппет: {result['snippet'][:150]}...")
            else:
                logger.error(f"LinkedInFinder не нашел результатов для {company}")
            
            logger.info("-" * 50)

if __name__ == "__main__":
    asyncio.run(test_linkedin_finder()) 