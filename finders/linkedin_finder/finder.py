import sys
import os
import re
import aiohttp
import logging

# Добавляем корневую директорию проекта в путь Python для прямого запуска
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from finders.base import Finder
from finders.linkedin_finder.utils import normalize_linkedin_url as normalize_linkedin_url_util
from finders.linkedin_finder.google_search import search_google
from finders.linkedin_finder.llm import choose_best_linkedin_url

# Настройка логгера
logger = logging.getLogger(__name__)

class LinkedInFinder(Finder):
    """
    Finds LinkedIn company page using Google Serper API search and LLM for choosing the best link.
    
    Algorithm:
    1. Performs Google search with query "{company_name} official website linkedin company profile"
    2. Filters results, keeping only LinkedIn links
    3. If there's an OpenAI API key, uses LLM to choose the best link
    4. If there's no OpenAI API key or LLM couldn't choose, takes the first suitable link
    5. Normalizes LinkedIn URL for consistency using function from utils.
    """
    
    def __init__(self, serper_api_key: str, openai_api_key: str = None, verbose: bool = False):
        """
        Initialize the finder with necessary API keys.
        
        Args:
            serper_api_key: Google Serper API key
            openai_api_key: OpenAI API key (optional)
            verbose: Output detailed search logs (default False)
        """
        self.serper_api_key = serper_api_key
        self.openai_api_key = openai_api_key
        self.verbose = verbose
    
    async def find(self, company_name: str, **context) -> dict:
        """
        Search for company LinkedIn profile via Google (Serper API) and LLM.
        
        Args:
            company_name: Company name
            context: Dictionary with context, should contain 'session' with aiohttp.ClientSession
                     and 'serper_api_key' with Google Serper API key
            
        Returns:
            dict: Search result {"source": "linkedin_finder", "result": url or None, "snippet": text}
        """
        # Get session and API keys from context
        session = context.get('session')
        if not session:
            raise ValueError("LinkedInFinder requires aiohttp.ClientSession in context['session']")
            
        serper_api_key = context.get('serper_api_key', self.serper_api_key)
        if not serper_api_key:
            raise ValueError("LinkedInFinder requires serper_api_key in context['serper_api_key']")
        
        # Get OpenAI API key from context or from class initialization
        openai_api_key = context.get('openai_api_key', self.openai_api_key)
        # Получаем OpenAI клиент из контекста, если есть
        openai_client = context.get('openai_client')
        if openai_client and not openai_api_key: # Если передан клиент, но не ключ, берем ключ из клиента
            openai_api_key = openai_client.api_key
            
        if self.verbose:
            logger.info(f"\n--- Поиск LinkedIn профиля для компании '{company_name}' ---")
            
        # Выполняем поиск через Serper API
        search_results = await search_google(company_name, session, serper_api_key)
        
        # Обрабатываем результаты поиска
        linkedin_url = None
        linkedin_snippet = None
        selected_candidate = None
        
        if search_results and "organic" in search_results:
            if self.verbose:
                logger.info(f"Найдено {len(search_results['organic'])} результатов поиска Google для LinkedIn")
                
            # Фильтрация результатов - оставляем только LinkedIn ссылки на компании
            linkedin_candidates = []
            for result in search_results["organic"]:
                url = result.get("link", "")
                # Более строгая проверка на /company/ для отсеивания /in/, /pub/ и т.д. на раннем этапе
                if "linkedin.com/company/" in url:
                    if self.verbose:
                        logger.debug(f"LinkedIn URL кандидат: {url} (Title: {result.get('title', '')})")
                    
                    linkedin_candidates.append(result)
            
            if linkedin_candidates:
                # Если у нас есть API ключ OpenAI, используем LLM для выбора лучшей ссылки
                if openai_api_key and len(linkedin_candidates) > 1:
                    if self.verbose:
                        logger.info(f"Используем LLM для выбора лучшего LinkedIn URL из {len(linkedin_candidates)} кандидатов")
                    
                    # Передаем API ключ в LLM функцию
                    selected_url_from_llm = await choose_best_linkedin_url(
                        company_name, 
                        linkedin_candidates, 
                        openai_api_key
                    )
                    
                    if selected_url_from_llm:
                        if self.verbose:
                            logger.info(f"LLM выбрал URL: {selected_url_from_llm}")
                        
                        # Проверяем, есть ли выбранный LLM URL среди наших кандидатов (для получения snippet)
                        for candidate in linkedin_candidates:
                            if selected_url_from_llm in candidate.get("link", "") or candidate.get("link", "") in selected_url_from_llm:
                                selected_candidate = candidate
                                linkedin_url = selected_url_from_llm # Используем URL от LLM
                                linkedin_snippet = candidate.get("snippet", "")
                                break
                
                # Если LLM не выбрал URL или нет API ключа, берем первый LinkedIn URL
                if not linkedin_url and linkedin_candidates: # Если LLM не использовался, не выбрал, или нет ключа
                    first_candidate = linkedin_candidates[0]
                    linkedin_url = first_candidate.get("link", "")
                    linkedin_snippet = first_candidate.get("snippet", "")
                    selected_candidate = first_candidate
                    
                    if self.verbose:
                        logger.info(f"Берем первый LinkedIn URL из Google: {linkedin_url}")
        
        final_linkedin_url = None
        if linkedin_url:
            # Используем импортированную функцию для нормализации
            final_linkedin_url = normalize_linkedin_url_util(linkedin_url)
            if final_linkedin_url:
                if self.verbose:
                    logger.info(f"Нормализованный LinkedIn URL для '{company_name}': {final_linkedin_url}")
            else:
                logger.warning(f"Нормализация не удалась для URL: {linkedin_url}. Используем исходный.")
                final_linkedin_url = linkedin_url # Используем исходный, если нормализация вернула None
                
            return {
                "source": "linkedin_finder", 
                "source_class": self.__class__.__name__,
                "result": final_linkedin_url, 
                "snippet": linkedin_snippet,
            }
        
        # Если не нашли
        if self.verbose:
            logger.info(f"LinkedIn профиль для '{company_name}' не найден")
        return {
            "source": "linkedin_finder", 
            "source_class": self.__class__.__name__,
            "result": None,
            "error": f"LinkedIn profile for '{company_name}' not found after search and selection."
        }


# Код для тестового запуска при прямом выполнении файла
if __name__ == "__main__":
    import asyncio
    import os
    from dotenv import load_dotenv
    
    async def test_finder():
        # Загрузка переменных окружения
        load_dotenv()
        
        # Получение API ключа
        serper_api_key = os.getenv("SERPER_API_KEY")
        
        if not serper_api_key:
            print("Ошибка: SERPER_API_KEY не найден в .env файле")
            return
        
        # Создаем финдер
        finder = LinkedInFinder(serper_api_key, verbose=True)
        
        # Тестовые компании
        test_companies = ["Microsoft", "Apple", "Google"]
        
        # Создаем HTTP сессию
        async with aiohttp.ClientSession() as session:
            for company in test_companies:
                print(f"\nПоиск для компании: {company}")
                result = await finder.find(company, session=session)
                if result["result"]:
                    print(f"Найден LinkedIn: {result['result']}")
                    if result.get("snippet"):
                        print(f"Сниппет: {result['snippet'][:150]}...")
                else:
                    print("LinkedIn не найден")
    
    # Запускаем тестовую функцию
    asyncio.run(test_finder()) 