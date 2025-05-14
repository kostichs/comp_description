import asyncio
import aiohttp
import os
import logging
import sys
from dotenv import load_dotenv
from openai import AsyncOpenAI
from scrapingbee import ScrapingBeeClient

# Добавляем путь к src, чтобы можно было импортировать pipeline_adapter
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from src.pipeline_adapter import process_companies

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_pipeline():
    # Загрузка переменных окружения
    load_dotenv()
    openai_api_key = os.getenv('OPENAI_API_KEY')
    serper_api_key = os.getenv('SERPER_API_KEY')
    sb_api_key = os.getenv('SCRAPINGBEE_API_KEY')
    
    if not openai_api_key or not serper_api_key or not sb_api_key:
        logger.error("Не все API ключи найдены в .env")
        return
    
    # Список тестовых компаний
    companies = ['Microsoft', 'Apple', 'Google', 'Tesla', 'Amazon']
    
    # Тестируем пайплайн
    async with aiohttp.ClientSession() as session:
        # Инициализируем клиентов API
        openai_client = AsyncOpenAI(api_key=openai_api_key)
        sb_client = ScrapingBeeClient(api_key=sb_api_key)
        
        # Запускаем пайплайн только с базовыми финдерами (без LLM Deep Search)
        logger.info("Запускаем пайплайн без LLM Deep Search")
        results = await process_companies(
            companies,
            openai_client,
            session,
            sb_client,
            serper_api_key,
            run_llm_deep_search_pipeline=False
        )
        
        # Выводим результаты
        logger.info("Результаты пайплайна:")
        for result in results:
            logger.info(f"Компания: {result['name']}")
            logger.info(f"  - LinkedIn: {result['linkedin']}")
            logger.info(f"  - Homepage: {result['homepage']}")
            logger.info(f"  - Описание: {result['description'][:100]}..." if len(result['description']) > 100 else result['description'])
            logger.info("-" * 50)

if __name__ == "__main__":
    asyncio.run(test_pipeline()) 