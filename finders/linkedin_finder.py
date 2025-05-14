from .base import Finder
import aiohttp
import re
from bs4 import BeautifulSoup

class LinkedInFinder(Finder):
    async def find(self, company_name: str, **context) -> dict:
        """
        Ищет информацию о компании через поиск LinkedIn.
        
        Args:
            company_name: Название компании
            context: Словарь с контекстом, должен содержать 'session' с aiohttp.ClientSession
            
        Returns:
            dict: Результат поиска {"source": "linkedin", "result": url или None}
        """
        session = context.get('session')
        if not session:
            raise ValueError("LinkedInFinder требует aiohttp.ClientSession в context['session']")
            
        result = await self._search_linkedin(company_name, session)
        return {"source": "linkedin", "result": result}
        
    async def _search_linkedin(self, company_name: str, session: aiohttp.ClientSession) -> str | None:
        """
        Выполняет поиск компании в LinkedIn и извлекает официальный сайт.
        
        Args:
            company_name: Название компании
            session: aiohttp.ClientSession для HTTP-запросов
            
        Returns:
            str | None: URL компании или None в случае ошибки
        """
        try:
            # Формируем строку поиска для Google, чтобы найти страницу LinkedIn компании
            search_url = f"https://www.google.com/search?q=linkedin+{company_name.replace(' ', '+')}+company"
            
            # Заголовки для имитации браузера
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
            
            # Выполняем запрос к Google
            async with session.get(search_url, headers=headers) as response:
                if response.status != 200:
                    return None
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем ссылки на LinkedIn в результатах поиска
                linkedin_pattern = re.compile(r'linkedin\.com/company/[^/]+/?.*')
                for a in soup.find_all('a', href=True):
                    if linkedin_pattern.search(a['href']):
                        linkedin_url = a['href']
                        # Извлекаем прямую ссылку из редиректа Google
                        if '/url?q=' in linkedin_url:
                            linkedin_url = linkedin_url.split('/url?q=')[1].split('&')[0]
                        
                        # Теперь, когда у нас есть URL LinkedIn компании, извлекаем официальный сайт
                        website = await self._extract_website_from_linkedin(linkedin_url, session)
                        return website
            
            return None
                
        except Exception as e:
            print(f"Ошибка при поиске LinkedIn: {e}")
            return None
            
    async def _extract_website_from_linkedin(self, linkedin_url: str, session: aiohttp.ClientSession) -> str | None:
        """
        Извлекает официальный сайт из страницы LinkedIn компании.
        
        Args:
            linkedin_url: URL страницы LinkedIn компании
            session: aiohttp.ClientSession для HTTP-запросов
            
        Returns:
            str | None: URL официального сайта или None
        """
        try:
            # Заголовки для имитации браузера
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
            
            # Выполняем запрос к странице LinkedIn
            async with session.get(linkedin_url, headers=headers) as response:
                if response.status != 200:
                    return None
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем ссылку на официальный сайт в разделе "About"
                # Обратите внимание, что это упрощенная реализация, которая может потребовать доработки
                # в зависимости от структуры страницы LinkedIn
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    # Исключаем ссылки на сам LinkedIn и другие социальные сети
                    if ('linkedin.com' not in href and 
                        'facebook.com' not in href and 
                        'twitter.com' not in href and
                        'instagram.com' not in href and
                        href.startswith('http')):
                        # Проверяем, что это похоже на URL сайта компании
                        if '.' in href and not href.startswith('mailto:'):
                            return href
            
            return None
                
        except Exception as e:
            print(f"Ошибка при извлечении сайта из LinkedIn: {e}")
            return None 