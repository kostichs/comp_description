import re
import aiohttp
from urllib.parse import urlparse, unquote
from bs4 import BeautifulSoup

def extract_company_name_from_wiki_url(wiki_url: str) -> str | None:
    """
    Извлекает название компании из URL Wikipedia.
    
    Args:
        wiki_url: URL страницы Wikipedia
        
    Returns:
        str | None: Название компании или None, если не удалось извлечь
    """
    try:
        # Получаем часть URL после /wiki/
        path = urlparse(wiki_url).path
        if '/wiki/' not in path:
            return None
            
        # Получаем название страницы и декодируем URL
        page_name = unquote(path.split('/wiki/')[-1])
        
        # Убираем скобки и их содержимое
        page_name = re.sub(r'\s*\([^)]*\)', '', page_name)
        
        # Заменяем подчеркивания на пробелы
        page_name = page_name.replace('_', ' ')
        
        return page_name.strip()
    except Exception as e:
        print(f"Ошибка при извлечении названия компании из URL: {e}")
        return None

async def parse_wikipedia_website(wiki_url: str, session: aiohttp.ClientSession) -> str | None:
    """
    Парсит официальный сайт компании из инфобокса Wikipedia.
    
    Args:
        wiki_url: URL страницы Wikipedia
        session: aiohttp.ClientSession для HTTP-запросов
        
    Returns:
        str | None: URL официального сайта или URL Wikipedia, если официальный сайт не найден
    """
    try:
        # Получаем HTML страницы
        async with session.get(wiki_url) as response:
            if response.status != 200:
                return wiki_url
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
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