from .base import Finder
import requests
from bs4 import BeautifulSoup

class WikipediaFinder(Finder):
    async def find(self, company_name: str, **context) -> dict:
        """
        Извлекает официальный сайт компании из страницы Wikipedia.
        
        Args:
            company_name: Название компании
            context: Словарь с контекстом, должен содержать 'wiki_url' с URL страницы Wikipedia
            
        Returns:
            dict: Результат поиска {"source": "wikipedia", "result": url или None}
        """
        wiki_url = context.get('wiki_url')
        if not wiki_url:
            return {"source": "wikipedia", "result": None}
            
        result = self._parse_wikipedia_website(wiki_url)
        return {"source": "wikipedia", "result": result}
        
    def _parse_wikipedia_website(self, wiki_url: str) -> str | None:
        """
        Парсит официальный сайт компании из инфобокса Wikipedia.
        
        Args:
            wiki_url: URL страницы Wikipedia
            
        Returns:
            str | None: URL официального сайта или URL Wikipedia, если официальный сайт не найден
        """
        try:
            # Получаем HTML страницы
            response = requests.get(wiki_url)
            if response.status_code != 200:
                return None
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем инфобокс компании
            infobox = soup.find('table', {'class': 'infobox ib-company vcard'})
            if not infobox:
                return wiki_url  # Возвращаем ссылку на Wikipedia если нет инфобокса
                
            # Ищем строку с вебсайтом
            website_row = infobox.find('th', string='Website')
            if not website_row:
                return wiki_url  # Возвращаем ссылку на Wikipedia если нет вебсайта
                
            # Получаем ссылку из следующей ячейки
            website_cell = website_row.find_next('td')
            if not website_cell:
                return wiki_url  # Возвращаем ссылку на Wikipedia если нет ячейки с вебсайтом
                
            # Ищем ссылку в ячейке
            website_link = website_cell.find('a', {'class': 'external text'})
            if not website_link:
                return wiki_url  # Возвращаем ссылку на Wikipedia если нет ссылки на вебсайт
                
            return website_link.get('href')
        except Exception as e:
            print(f"Ошибка при парсинге Wikipedia: {e}")
            return wiki_url  # При любой ошибке возвращаем ссылку на Wikipedia 