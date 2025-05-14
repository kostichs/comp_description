import aiohttp
import sys
import os

# Добавляем корневую директорию проекта в путь Python
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from finders.base import Finder
from finders.homepage_finder.wikidata import get_wikidata_url
from finders.homepage_finder.domain_check import find_domain_by_tld
from finders.homepage_finder.google_search import search_google, filter_wikipedia_links
from finders.homepage_finder.wikipedia import extract_company_name_from_wiki_url, parse_wikipedia_website
from finders.homepage_finder.llm import choose_best_wiki_link

class HomepageFinder(Finder):
    """
    Единый алгоритм поиска официального сайта компании, реализующий логику из test_serper.py.
    Последовательно проверяет следующие источники:
    1. Wikidata
    2. Проверка доменов
    3. Google (через Serper API) -> поиск Wikipedia -> выбор через LLM -> парсинг Wikipedia
    """
    
    def __init__(self, serper_api_key: str, openai_api_key: str = None):
        """
        Инициализирует финдер с необходимыми API ключами.
        
        Args:
            serper_api_key: API ключ для Google Serper
            openai_api_key: API ключ для OpenAI (опционально)
        """
        self.serper_api_key = serper_api_key
        self.openai_api_key = openai_api_key
    
    async def find(self, company_name: str, **context) -> dict:
        """
        Ищет официальный сайт компании, последовательно проверяя различные источники.
        
        Args:
            company_name: Название компании
            context: Словарь с контекстом, должен содержать 'session' с aiohttp.ClientSession
            
        Returns:
            dict: Результат поиска {"source": "название_источника", "result": url или None}
        """
        session = context.get('session')
        if not session:
            raise ValueError("HomepageFinder требует aiohttp.ClientSession в context['session']")
        
        # 1. Сначала пробуем получить URL из Wikidata
        wikidata_url = get_wikidata_url(company_name)
        if wikidata_url:
            return {"source": "wikidata", "result": wikidata_url}
        
        # 2. Если через Wikidata не нашли, пробуем найти через проверку доменов
        domain_url = await find_domain_by_tld(company_name, session)
        if domain_url:
            return {"source": "domains", "result": domain_url}
        
        # 3. Если не нашли ни через Wikidata, ни через домены, ищем через Google
        results = await search_google(company_name, session, self.serper_api_key)
        if results and "organic" in results:
            # Фильтруем результаты, оставляя только ссылки на Wikipedia
            wiki_links = filter_wikipedia_links(results["organic"], company_name)
            if wiki_links:
                # Выбираем лучшую ссылку на Wikipedia через LLM
                if self.openai_api_key:
                    selected_url = await choose_best_wiki_link(
                        company_name, 
                        wiki_links, 
                        self.openai_api_key
                    )
                    
                    if selected_url:
                        # Пробуем получить название компании из URL Wikipedia
                        wiki_company_name = extract_company_name_from_wiki_url(selected_url)
                        if wiki_company_name:
                            # Пробуем найти через Wikidata используя название из Wikipedia
                            wikidata_url = get_wikidata_url(wiki_company_name)
                            if wikidata_url:
                                return {"source": "wikidata_via_wiki", "result": wikidata_url}
                        
                        # Если через Wikidata не нашли, пробуем парсить Wikipedia
                        website_url = await parse_wikipedia_website(selected_url, session)
                        if website_url != selected_url:  # Если нашли официальный сайт в инфобоксе
                            return {"source": "wikipedia", "result": website_url}
                        else:  # Если вернулась ссылка на Wikipedia
                            return {"source": "wikipedia_page", "result": website_url}
                
                # Если нет OpenAI API ключа или LLM не выбрал, берем первую ссылку
                first_url = wiki_links[0]["link"]
                website_url = await parse_wikipedia_website(first_url, session)
                if website_url != first_url:
                    return {"source": "wikipedia_first", "result": website_url}
                else:
                    return {"source": "wikipedia_page_first", "result": first_url}
        
        # Ничего не нашли
        return {"source": "homepage_finder", "result": None}


# Код для тестового запуска при прямом выполнении файла
if __name__ == "__main__":
    import asyncio
    import os
    from dotenv import load_dotenv
    
    async def test_finder():
        # Загрузка переменных окружения
        load_dotenv()
        
        # Получение API ключей
        serper_api_key = os.getenv("SERPER_API_KEY")
        openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if not serper_api_key:
            print("Ошибка: SERPER_API_KEY не найден в .env файле")
            return
            
        if not openai_api_key:
            print("Ошибка: OPENAI_API_KEY не найден в .env файле")
            return
        
        # Создаем финдер
        finder = HomepageFinder(serper_api_key, openai_api_key)
        
        # Тестовые компании
        test_companies = ["Microsoft", "Apple", "Google"]
        
        # Создаем HTTP сессию
        async with aiohttp.ClientSession() as session:
            for company in test_companies:
                print(f"\nПоиск для компании: {company}")
                result = await finder.find(company, session=session)
                if result["result"]:
                    print(f"Найден сайт через {result['source']}: {result['result']}")
                else:
                    print("Сайт не найден")
    
    # Запускаем тестовую функцию
    asyncio.run(test_finder()) 