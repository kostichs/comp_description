import aiohttp
import sys
import os
import logging

# Добавляем корневую директорию проекта в путь Python
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from finders.base import Finder
from finders.homepage_finder.wikidata import get_wikidata_url
from finders.homepage_finder.google_search import search_google, filter_wikipedia_links
from finders.homepage_finder.wikipedia import extract_company_name_from_wiki_url, parse_wikipedia_website
from finders.homepage_finder.llm import choose_best_wiki_link

logger = logging.getLogger(__name__)

class HomepageFinder(Finder):
    """
    Единый алгоритм поиска официального сайта компании.
    Приоритеты:
    1. Wikidata (по исходному имени)
    2. Google Search -> Выбор лучшей Wiki страницы (LLM) -> Wikidata (по имени из Wiki URL) -> Парсер Wiki Infobox
    """
    
    def __init__(self, serper_api_key: str, openai_api_key: str = None, verbose: bool = False):
        """
        Инициализирует финдер с необходимыми API ключами.
        
        Args:
            serper_api_key: API ключ для Google Serper
            openai_api_key: API ключ для OpenAI (опционально)
            verbose: Выводить подробные логи поиска (по умолчанию False)
        """
        self.serper_api_key = serper_api_key
        self.openai_api_key = openai_api_key
        self.verbose = verbose
    
    async def find(self, company_name: str, **context) -> dict:
        """
        Ищет официальный сайт компании, последовательно проверяя различные источники.
        
        Args:
            company_name: Название компании
            context: Словарь с контекстом, может содержать:
                - session: aiohttp.ClientSession
                - serper_api_key: API ключ для Google Serper (альтернатива self.serper_api_key)
            
        Returns:
            dict: Результат поиска {"source": "название_источника", "result": url или None}
        """
        # Получаем session из параметров или контекста
        session = context.get('session')
        if not session:
            logger.error("HomepageFinder: aiohttp.ClientSession not found in context['session']")
            raise ValueError("HomepageFinder требует aiohttp.ClientSession в context['session']")
        
        # Получаем serper_api_key из параметров или используем инициализированный
        serper_api_key = context.get('serper_api_key', self.serper_api_key)
        if not serper_api_key:
            logger.error("HomepageFinder: serper_api_key not found")
            raise ValueError("HomepageFinder требует serper_api_key")
        
        logger.info(f"--- Поиск домашней страницы для компании '{company_name}' (HomepageFinder) ---")
        
        # 1. Wikidata (по исходному имени)
        wikidata_url_initial = get_wikidata_url(company_name)
        if wikidata_url_initial:
            logger.info(f"Найден URL через Wikidata (исходное имя) для '{company_name}': {wikidata_url_initial}")
            return {"source": "wikidata", "source_class": "HomepageFinder", "result": wikidata_url_initial}
        
        found_website_from_wiki_pipeline = None
        wiki_source_name = None
        selected_wiki_url = None # Инициализируем здесь, чтобы было доступно в конце

        # 2. Google Search -> Wikipedia pipeline
        google_results = await search_google(company_name, session, serper_api_key)
        if google_results and "organic" in google_results:
            wiki_links = filter_wikipedia_links(google_results["organic"], company_name)
            if wiki_links:
                if self.openai_api_key and len(wiki_links) > 0:
                    logger.debug(f"Используем LLM для выбора лучшей Wiki-ссылки для '{company_name}' из {len(wiki_links)} кандидатов.")
                    selected_wiki_url = await choose_best_wiki_link(company_name, wiki_links, self.openai_api_key)
                elif wiki_links:
                    selected_wiki_url = wiki_links[0]["link"]
                    logger.debug(f"LLM не используется, берем первую Wiki-ссылку для '{company_name}': {selected_wiki_url}")

                if selected_wiki_url:
                    logger.info(f"Выбрана Wiki-ссылка для '{company_name}': {selected_wiki_url}")
                    wiki_company_name = extract_company_name_from_wiki_url(selected_wiki_url)
                    if wiki_company_name:
                        logger.debug(f"Извлечено имя из Wiki URL '{selected_wiki_url}': {wiki_company_name}")
                        wikidata_url_from_wiki_name = get_wikidata_url(wiki_company_name)
                        if wikidata_url_from_wiki_name:
                            logger.info(f"Найден URL через Wikidata (имя из Wiki) для '{company_name}': {wikidata_url_from_wiki_name}")
                            found_website_from_wiki_pipeline = wikidata_url_from_wiki_name
                            wiki_source_name = "wikidata_via_wiki"
                    
                    if not found_website_from_wiki_pipeline:
                        logger.debug(f"Парсинг Wiki-страницы '{selected_wiki_url}' для '{company_name}'")
                        parsed_website_url = await parse_wikipedia_website(selected_wiki_url, session)
                        if parsed_website_url and parsed_website_url != selected_wiki_url:
                            logger.info(f"Найден URL через парсинг Wiki-инфобокса для '{company_name}': {parsed_website_url}")
                            found_website_from_wiki_pipeline = parsed_website_url
                            wiki_source_name = "wikipedia_infobox"
                        elif parsed_website_url == selected_wiki_url:
                             logger.info(f"Парсер Wiki для '{company_name}' вернул ссылку на саму Wiki: {selected_wiki_url}. Игнорируем.")
                        else:
                            logger.info(f"Парсер Wiki для '{company_name}' не нашел сайт в инфобоксе.")
        
        if found_website_from_wiki_pipeline:
            return {"source": wiki_source_name, "source_class": "HomepageFinder", "result": found_website_from_wiki_pipeline}

        # Если selected_wiki_url был, но не разрешился в сайт, и domain_check больше не вызывается здесь,
        # мы НЕ возвращаем selected_wiki_url.
        if selected_wiki_url and not found_website_from_wiki_pipeline:
             logger.info(f"Ни Wikidata, ни парсер Wiki не дали результат для '{company_name}'. Был выбран Wiki URL: {selected_wiki_url}, но он не будет возвращен как homepage.")

        logger.warning(f"Домашняя страница для '{company_name}' не найдена методами HomepageFinder.")
        return {"source": "homepage_finder", "source_class": "HomepageFinder", "result": None, "error": f"Homepage not found for {company_name} by HomepageFinder methods."}


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