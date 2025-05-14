import json
import aiohttp
import logging

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
        "q": f"{company_name} official website linkedin company profile",
        "num": 30,
        "gl": "us",
        "hl": "en"
    })
    
    try:
        async with session.post("https://google.serper.dev/search", headers=headers, data=payload, timeout=20) as response:
            if response.status == 200:
                results = await response.json()
                return results
            else:
                print(f"Ошибка при запросе к Serper API: {response.status}")
                return None
    except Exception as e:
        print(f"Ошибка при запросе к Serper API: {e}")
        return None

def score_linkedin_url(url: str, title: str, normalized_company_name: str, slug: str) -> tuple[int, list[str]]:
    """
    Оценивает LinkedIn URL для определения релевантности к компании.
    
    Args:
        url: LinkedIn URL
        title: Заголовок результата поиска
        normalized_company_name: Нормализованное название компании
        slug: Slug из LinkedIn URL
        
    Returns:
        tuple[int, list[str]]: Оценка релевантности и список причин
    """
    score = 0
    reason = []
    
    url_lower = url.lower()
    title_lower = title.lower()
    
    if "/company/" in url_lower: 
        score += 20
        reason.append("/company/ link:+20")
    elif "/showcase/" in url_lower: 
        score += 5
        reason.append("/showcase/ link:+5")
    elif "/school/" in url_lower: 
        score += 3
        reason.append("/school/ link:+3")
        
    if slug and normalized_company_name in slug.replace('-', ''): 
        score += 15
        reason.append(f"Name in slug ({slug}):+15")
    elif normalized_company_name in title_lower.replace('-', '').replace(' ', ''): 
        score += 10
        reason.append(f"Name in title ({title_lower[:30]}...):+10")
    elif any(part in slug.replace('-', '') for part in normalized_company_name.split('-') if len(part) > 2): 
        score += 7
        reason.append(f"Part of name in slug ({slug}):+7")
    elif any(part in title_lower.replace('-', '').replace(' ', '') for part in normalized_company_name.split('-') if len(part) > 2): 
        score += 5
        reason.append(f"Part of name in title ({title_lower[:30]}...):+5")
        
    if "jobs" in title_lower or "careers" in title_lower or "/jobs" in url_lower or "/careers" in url_lower:
        if not ("/company/" in url_lower and score > 20): 
            score -= 5
            reason.append("Jobs/careers term:-5")
            
    return score, reason 