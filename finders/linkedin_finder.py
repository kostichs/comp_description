from .base import Finder
import aiohttp
import re
from bs4 import BeautifulSoup
import urllib.parse
import logging

logger = logging.getLogger(__name__)

class LinkedInFinder(Finder):
    async def find(self, company_name: str, **context) -> dict:
        """
        Ищет URL LinkedIn страницы компании через Google и нормализует его.
        
        Args:
            company_name: Название компании
            context: Словарь с контекстом, должен содержать 'session' с aiohttp.ClientSession
            
        Returns:
            dict: Результат поиска {
                "source": "linkedin_finder", 
                "result": url или None, 
                "error": str или None,
                "source_class": "LinkedInFinder"
            }
        """
        session = context.get('session')
        if not session:
            return {
                "source": "linkedin_finder", 
                "result": None, 
                "error": "LinkedInFinder_requires_aiohttp.ClientSession_in_context['session']",
                "source_class": self.__class__.__name__
            }
            
        raw_linkedin_url = await self._get_linkedin_page_url_from_google(company_name, session)
        
        if raw_linkedin_url:
            normalized_url = self._normalize_linkedin_company_url(raw_linkedin_url)
            if normalized_url:
                logger.debug(f"Normalized LinkedIn URL for {company_name}: {raw_linkedin_url} -> {normalized_url}")
                return {
                    "source": "linkedin_finder", 
                    "result": normalized_url,
                    "error": None,
                    "source_class": self.__class__.__name__
                }
            else:
                logger.warning(f"Failed to normalize LinkedIn URL for {company_name}: {raw_linkedin_url}. Returning raw.")
                return {
                    "source": "linkedin_finder", 
                    "result": raw_linkedin_url,
                    "error": f"Failed to normalize LinkedIn URL '{raw_linkedin_url}', returning raw.",
                    "source_class": self.__class__.__name__
                }
        
        return {
            "source": "linkedin_finder", 
            "result": None,
            "error": f"LinkedIn page not found for {company_name}",
            "source_class": self.__class__.__name__
        }
        
    def _normalize_linkedin_company_url(self, url: str) -> str | None:
        """
        Нормализует URL компании LinkedIn, удаляя подпути (например, /about/, /jobs/)
        и параметры запроса (например, ?trk=...). 
        Оставляет только базовый URL вида https://www.linkedin.com/company/company-name/
        """
        try:
            parsed_url = urllib.parse.urlparse(url)
            
            # Проверяем, что это действительно LinkedIn URL и содержит /company/
            if not parsed_url.netloc.endswith("linkedin.com") or '/company/' not in parsed_url.path:
                logger.warning(f"URL '{url}' does not appear to be a standard LinkedIn company URL for normalization.")
                return url # Возвращаем как есть, если это не похоже на целевой URL

            # Ищем паттерн /company/company-name. company-name может содержать буквы, цифры, дефисы.
            match = re.search(r'(/company/([a-zA-Z0-9_-]+/?))?', parsed_url.path, re.IGNORECASE)
            
            if match and match.group(1): 
                # Извлекаем часть пути, которая соответствует /company/slug
                # match.group(2) должен содержать сам slug
                company_slug_part = match.group(2)
                if company_slug_part:
                    # Убираем возможный слеш в конце слага, если он там есть
                    clean_slug = company_slug_part.strip('/') 
                    clean_path = f"/company/{clean_slug}" # Собираем путь без слеша в конце
                
                    normalized = urllib.parse.urlunparse((
                        parsed_url.scheme or 'https', 
                        parsed_url.netloc, 
                        clean_path, 
                        '',  
                        '',  
                        ''   
                    ))
                    return normalized.lower()
            else:
                logger.warning(f"Could not extract base /company/path from LinkedIn URL: {url}")
                if '/company/' in parsed_url.path:
                     base_path_part = parsed_url.path.split('?')[0].split('#')[0]
                     # Попытка извлечь /company/slug и убрать лишние слеши
                     company_match_in_base = re.search(r'(/company/[^/]+)', base_path_part)
                     if company_match_in_base:
                         clean_path_fallback = company_match_in_base.group(1) # Уже без слеша в конце
                         return urllib.parse.urlunparse((
                            parsed_url.scheme or 'https', 
                            parsed_url.netloc, 
                            clean_path_fallback,
                            '', '', ''
                         )).lower()
                return url

        except Exception as e:
            logger.error(f"Error normalizing LinkedIn URL '{url}': {e}", exc_info=True)
            return url # В случае ошибки возвращаем исходный URL, чтобы не потерять данные
            
    async def _get_linkedin_page_url_from_google(self, company_name: str, session: aiohttp.ClientSession) -> str | None:
        """
        Выполняет поиск компании в Google для нахождения ее страницы LinkedIn.
        Возвращает URL страницы LinkedIn как есть (после очистки от Google redirect).
        
        Args:
            company_name: Название компании
            session: aiohttp.ClientSession для HTTP-запросов
            
        Returns:
            str | None: URL страницы LinkedIn или None
        """
        try:
            search_query = f'linkedin company {company_name.replace(" ", "+")}'
            search_url = f"https://www.google.com/search?q={search_query}&hl=en" 
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'
            }
            
            async with session.get(search_url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    # logger.warning(f"Google search for LinkedIn page of '{company_name}' returned status {response.status}")
                    return None
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Паттерн для поиска ссылок на страницы компаний LinkedIn
                # r'https?://(?:www\.)?linkedin\.com/company/([^/?#]+)/?' - более строгий, без подпутей
                # r'https?://(?:www\.)?linkedin\.com/company/[^/?#]+(?:/[^/?#]*)*/?' - захватит с подпутями
                linkedin_pattern = re.compile(r'https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/[^\\s\'\"<>#?&]+')

                for link_tag in soup.find_all('a', href=True):
                    href = link_tag['href']
                    
                    # Попытка извлечь URL из Google redirect, если он есть
                    if '/url?q=' in href:
                        actual_url_match = re.search(r'/url\?q=([^&]+)', href)
                        if actual_url_match:
                            href = urllib.parse.unquote(actual_url_match.group(1))
                    
                    # Проверяем, соответствует ли извлеченный или оригинальный href паттерну LinkedIn
                    match = linkedin_pattern.search(href)
                    if match:
                        found_url = match.group(0)
                        # logger.debug(f"LinkedIn company URL found for {company_name}: {found_url}")
                        # Нормализация происходит в вызывающей функции find
                        return found_url
            
            # logger.warning(f"No LinkedIn company page URL found for '{company_name}' in Google search results.")
            return None
                
        except Exception as e:
            # logger.error(f"Error during LinkedIn page search for '{company_name}': {e}", exc_info=True)
            return None
            
    # async def _extract_website_from_linkedin(self, linkedin_url: str, session: aiohttp.ClientSession) -> str | None:
    #     """
    #     ЗАКОММЕНТИРУЙТЕ МЕНЯ ИЛИ УДАЛИТЕ, ЕСЛИ Я НЕ НУЖНА
    #     Извлекает официальный сайт из страницы LinkedIn компании.
        
    #     Args:
    #         linkedin_url: URL страницы LinkedIn компании
    #         session: aiohttp.ClientSession для HTTP-запросов
            
    #     Returns:
    #         str | None: URL официального сайта или None
    #     """
    #     try:
    #         headers = {
    #             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36',
    #             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    #         }
            
    #         async with session.get(linkedin_url, headers=headers) as response:
    #             if response.status != 200:
    #                 return None
                    
    #             html = await response.text()
    #             soup = BeautifulSoup(html, 'html.parser')
                
    #             for a in soup.find_all('a', href=True):
    #                 href = a['href']
    #                 if ('linkedin.com' not in href and 
    #                     'facebook.com' not in href and 
    #                     'twitter.com' not in href and
    #                     'instagram.com' not in href and
    #                     href.startswith('http')):
    #                     if '.' in href and not href.startswith('mailto:'):
    #                         return href
    #         return None
    #     except Exception as e:
    #         print(f"Ошибка при извлечении сайта из LinkedIn: {e}")
    #         return None 