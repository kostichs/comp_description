import sys
import os
import re
import aiohttp

# Добавляем корневую директорию проекта в путь Python для прямого запуска
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from finders.base import Finder
from finders.linkedin_finder.utils import normalize_name_for_domain_comparison, normalize_linkedin_url
from finders.linkedin_finder.google_search import search_google, score_linkedin_url

class LinkedInFinder(Finder):
    """
    Находит LinkedIn страницу компании, используя поиск через Google Serper API.
    
    Алгоритм:
    1. Выполняет поиск через Google с запросом "{company_name} official website linkedin company profile"
    2. Фильтрует результаты, оставляя только ссылки на LinkedIn
    3. Нормализует URL LinkedIn для единообразия
    4. Оценивает релевантность каждого URL на основе различных факторов
    5. Возвращает наиболее релевантный LinkedIn URL
    """
    
    def __init__(self, serper_api_key: str, verbose: bool = False):
        """
        Инициализирует финдер с необходимым API ключом для Serper.
        
        Args:
            serper_api_key: API ключ для Google Serper
            verbose: Выводить подробные логи поиска (по умолчанию False)
        """
        self.serper_api_key = serper_api_key
        self.verbose = verbose
    
    async def find(self, company_name: str, **context) -> dict:
        """
        Ищет LinkedIn страницу компании с использованием Google Serper API.
        
        Args:
            company_name: Название компании
            context: Словарь с контекстом, должен содержать 'session' с aiohttp.ClientSession
            
        Returns:
            dict: Результат поиска {"source": "linkedin_finder", "result": url или None, "snippet": snippet или None}
        """
        session = context.get('session')
        if not session:
            raise ValueError("LinkedInFinder требует aiohttp.ClientSession в context['session']")
        
        if self.verbose:
            print(f"\n--- Поиск LinkedIn URL для компании '{company_name}' ---")
        
        # Нормализуем название компании для сравнения
        normalized_company_name = normalize_name_for_domain_comparison(company_name)
        if self.verbose:
            print(f"Нормализованное название для сравнения: '{normalized_company_name}'")
        
        # Выполняем поиск через Google
        serper_results = await search_google(company_name, session, self.serper_api_key)
        if not serper_results or not serper_results.get("organic"):
            if self.verbose:
                print(f"Не найдены органические результаты для '{company_name}'")
            return {"source": "linkedin_finder", "result": None, "snippet": None}
        
        organic_results = serper_results["organic"]
        if self.verbose:
            print(f"Получено {len(organic_results)} органических результатов")
        
        # Находим и оцениваем LinkedIn кандидатов
        linkedin_candidates = []
        for result in organic_results:
            link = result.get("link")
            title = result.get("title", "")
            
            if not link or not isinstance(link, str) or "linkedin.com/" not in link.lower():
                continue
                
            normalized_url = normalize_linkedin_url(link)
            if not normalized_url:
                if self.verbose:
                    print(f"Пропущен не нормализуемый LinkedIn URL: {link}")
                continue
                
            # Извлекаем slug для оценки
            slug_match = re.search(r"linkedin\.com/(?:company|school|showcase)/([^/]+)/about/?", normalized_url.lower())
            slug = slug_match.group(1) if slug_match else ""
            
            # Оцениваем URL
            score, reasons = score_linkedin_url(normalized_url, title, normalized_company_name, slug)
            
            if score > 0:
                linkedin_candidates.append({
                    "url": normalized_url,
                    "score": score,
                    "title": title,
                    "slug": slug,
                    "reason": ", ".join(reasons),
                    "snippet": result.get("snippet", "")
                })
                if self.verbose:
                    print(f"Кандидат LinkedIn: {normalized_url}, Оценка: {score}, Слаг: '{slug}', Причина: {', '.join(reasons)}")
        
        # Выбираем лучшего кандидата
        if linkedin_candidates:
            linkedin_candidates.sort(key=lambda x: x["score"], reverse=True)
            best_candidate = linkedin_candidates[0]
            
            selected_url = best_candidate["url"]
            selected_snippet = best_candidate["snippet"]
            
            print(f"LinkedIn URL для '{company_name}': {selected_url}")
            
            return {
                "source": "linkedin_finder", 
                "result": selected_url, 
                "snippet": selected_snippet
            }
        else:
            if self.verbose:
                print(f"Не найден подходящий LinkedIn URL для '{company_name}'")
            return {"source": "linkedin_finder", "result": None, "snippet": None}


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