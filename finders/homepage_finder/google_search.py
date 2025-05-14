import json
import aiohttp
from urllib.parse import urlparse

async def search_google(company_name: str, session: aiohttp.ClientSession, serper_api_key: str) -> dict | None:
    """
    Выполняет поиск через Google Serper API.
    
    Args:
        company_name: Название компании
        session: aiohttp.ClientSession для HTTP-запросов
        serper_api_key: API ключ для Serper
        
    Returns:
        dict | None: Результаты поиска или None в случае ошибки
    """
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    payload = json.dumps({
        "q": f"company {company_name} official website wikipedia",
        "num": 10,
        "gl": "us",
        "hl": "en"
    })
    
    try:
        async with session.post("https://google.serper.dev/search", headers=headers, data=payload) as response:
            if response.status == 200:
                return await response.json()
            else:
                print(f"Ошибка при запросе к Serper API: {response.status}")
                return None
    except Exception as e:
        print(f"Ошибка при запросе к Serper API: {e}")
        return None

def calculate_relevance_score(company_name: str, wiki_url: str) -> float:
    """
    Вычисляет оценку релевантности Wikipedia страницы для компании.
    
    Args:
        company_name: Название компании
        wiki_url: URL страницы Wikipedia
        
    Returns:
        float: Оценка релевантности (выше - лучше)
    """
    from urllib.parse import unquote
    
    # Получаем название страницы из URL
    path = urlparse(wiki_url).path
    if '/wiki/' not in path:
        return 0
    page_name = unquote(path.split('/wiki/')[-1])
    
    # Приводим к нижнему регистру и нормализуем разделители
    company_name = company_name.lower()
    page_name = page_name.lower().replace('_', ' ')
    
    # Разбиваем на слова
    company_words = company_name.split()
    page_words = page_name.split()
    
    # Если первое слово не совпадает - сразу 0
    if not page_words or company_words[0] != page_words[0]:
        return 0
    
    # Считаем баллы за совпадения слов в правильном порядке
    score = 0
    i = 0  # индекс в company_words
    j = 0  # индекс в page_words
    
    while i < len(company_words) and j < len(page_words):
        if company_words[i] == page_words[j]:
            score += 1
            i += 1
            j += 1
        else:
            j += 1
    
    # Штраф за лишние слова
    if j < len(page_words):
        score -= 0.5 * (len(page_words) - j)
    
    return max(0, score)  # Не даем отрицательную оценку

def filter_wikipedia_links(results: list, company_name: str) -> list:
    """
    Фильтрует результаты поиска, оставляя только ссылки на Wikipedia и оценивая их релевантность.
    
    Args:
        results: Список результатов поиска
        company_name: Название компании
        
    Returns:
        list: Отфильтрованные результаты с оценкой релевантности
    """
    wiki_links = []
    for result in results:
        url = result.get('link', '')
        parsed_url = urlparse(url)
        if 'wikipedia.org' in parsed_url.netloc and '/wiki/' in parsed_url.path:
            # Добавляем оценку релевантности к результату
            result['relevance_score'] = calculate_relevance_score(company_name, url)
            wiki_links.append(result)
    
    # Сортируем по убыванию оценки релевантности
    return sorted(wiki_links, key=lambda x: x.get('relevance_score', 0), reverse=True) 