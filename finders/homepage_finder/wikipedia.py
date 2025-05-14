import re
import aiohttp
from urllib.parse import urlparse, unquote
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

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
        logger.error(f"Ошибка при извлечении названия компании из URL '{wiki_url}': {e}")
        return None

async def parse_wikipedia_website(wiki_url: str, session: aiohttp.ClientSession) -> str | None:
    """
    Парсит официальный сайт компании из инфобокса Wikipedia.
    Возвращает URL официального сайта или None, если не найден.
    """
    try:
        logger.debug(f"Attempting to parse Wikipedia page: {wiki_url}")
        async with session.get(wiki_url, timeout=10) as response:
            if response.status != 200:
                logger.warning(f"Failed to fetch Wikipedia page {wiki_url}, status: {response.status}")
                return None
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Более гибкий поиск инфобокса
            infobox = soup.find('table', class_=re.compile(r'infobox.*vcard', re.IGNORECASE))
            if not infobox:
                # Дополнительная попытка найти инфобокс по другому распространенному классу
                infobox = soup.find('table', class_=re.compile(r'infobox', re.IGNORECASE))
                if not infobox:
                    logger.debug(f"No infobox found on {wiki_url}")
                    return None

            # Ищем метку "Website" (и аналоги) без учета регистра
            website_labels = ['Website', 'Sitio web', 'Site web', 'Webseite', 'Сайт'] 
            website_row_header = None
            for label_text in website_labels:
                website_row_header = infobox.find('th', string=re.compile(r'^\s*' + re.escape(label_text) + r'\s*$', re.IGNORECASE))
                if website_row_header:
                    break
            
            website_cell = None
            if website_row_header:
                website_cell = website_row_header.find_next_sibling('td')
                # Иногда ссылка может быть в той же ячейке <th>, если она не имеет <td> sibling
                if not website_cell:
                    parent_tr = website_row_header.find_parent('tr')
                    if parent_tr:
                        website_cell = parent_tr.find('td') # Ищем td в том же tr

            # Если не нашли через th->td, пробуем найти td с классом 'url' или содержащий ссылку с itemprop="url"
            if not website_cell:
                possible_cells = infobox.find_all('td')
                for cell in possible_cells:
                    if cell.find('a', itemprop='url', href=True): # Schema.org microdata
                        website_cell = cell
                        break
                    if cell.get('class') and any('url' in c.lower() for c in cell.get('class')):
                        website_cell = cell
                        break
                if not website_cell and website_row_header: # Если нашли th, но не td, попробуем поискать ссылку в родительском tr от th
                    parent_tr = website_row_header.find_parent('tr')
                    if parent_tr:
                         website_cell = parent_tr # Используем весь tr как потенциальную ячейку для поиска ссылки

            if not website_cell:
                logger.debug(f"Website row/cell not found in infobox on {wiki_url}")
                return None
                
            # Ищем ссылку в найденной ячейке
            # Сначала ищем ссылки с классом, содержащим 'external text' или 'url'
            website_link = website_cell.find('a', class_=re.compile(r'(external text|url)', re.IGNORECASE), href=True)
            
            if not website_link: # Если не нашли по классу, ищем любую первую http(s) ссылку
                website_link = website_cell.find('a', href=re.compile(r'^https?://'))

            if not website_link: # Если все еще не нашли
                # Попробуем найти ссылку в элементе span с классом url (часто бывает)
                span_url = website_cell.find('span', class_='url')
                if span_url:
                    website_link = span_url.find('a', href=True)
                
                if not website_link:
                    logger.debug(f"Website link not found in website cell on {wiki_url}")
                    return None
            
            href = website_link.get('href')
            if href:
                # Убираем возможные префиксы типа // (протокол-относительные URL)
                if href.startswith('//'):
                    href = 'https:' + href 
                
                # Проверка, что это не внутренняя ссылка Википедии и не ссылка на файл
                parsed_href = urlparse(href)
                if parsed_href.scheme in ['http', 'https'] and \
                   not parsed_href.netloc.endswith('wikimedia.org') and \
                   not parsed_href.netloc.endswith('wikipedia.org') and \
                   not parsed_href.path.startswith('/wiki/') and \
                   not parsed_href.path.startswith('/w/') and \
                   not any(ext in parsed_href.path.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.pdf']):
                    logger.info(f"Successfully parsed website from Wikipedia {wiki_url}: {href}")
                    return href
                else:
                    logger.debug(f"Found link '{href}' on {wiki_url}, but it seems to be an internal/media link or not a valid website.")
                    return None
            else:
                logger.debug(f"Website link tag found, but no href attribute on {wiki_url}")
                return None
                
    except Exception as e:
        logger.error(f"Error parsing Wikipedia page {wiki_url}: {e}", exc_info=True)
        return None 