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

async def test_linkedin_finder_with_llm():
    # Загрузка переменных окружения
    load_dotenv()
    serper_api_key = os.getenv('SERPER_API_KEY')
    openai_api_key = os.getenv('OPENAI_API_KEY')
    
    if not serper_api_key or not openai_api_key:
        logger.error("API ключи не найдены в .env файле")
        return
    
    # Создаем финдер с LLM поддержкой
    finder = LinkedInFinder(serper_api_key, openai_api_key, verbose=True)
    
    # Примеры компаний разного размера/известности
    test_companies = [
        "Microsoft",  # Крупная, известная
        "Stripe",     # Средняя, известная
        "MongoDB",    # Средняя технологическая
        "Databricks", # Специализированная
        "Segment",    # Более мелкая, может иметь схожие названия
        "Plaid"       # Неоднозначное название
    ]
    
    # Создаем HTTP сессию
    async with aiohttp.ClientSession() as session:
        for company in test_companies:
            logger.info(f"Поиск LinkedIn для компании: {company}")
            
            # Поиск через финдер с LLM
            result = await finder.find(
                company, 
                session=session, 
                serper_api_key=serper_api_key,
                openai_api_key=openai_api_key
            )
            
            if result["result"]:
                logger.info(f"LinkedInFinder нашел: {result['result']}")
                if "snippet" in result and result["snippet"]:
                    logger.info(f"Сниппет: {result['snippet'][:150]}...")
            else:
                logger.error(f"LinkedInFinder не нашел результатов для {company}")
            
            logger.info("-" * 50)

if __name__ == "__main__":
    asyncio.run(test_linkedin_finder_with_llm()) 