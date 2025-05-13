import requests
import json
# from dotenv import load_dotenv # Больше не нужно, ключи передаются как аргументы
import os
# import pandas as pd # Не используется в этом модуле
# from pathlib import Path # Не используется в этом модуле
from urllib.parse import urlparse, unquote
import socket
import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup
from openai import AsyncOpenAI

# load_dotenv() # Удалено

# --- Вспомогательные функции из test_serper.py ---

def normalize_name_for_domain_comparison(name: str) -> str:
    """Очищает название компании для сравнения с доменом."""
    name = re.sub(r'\\s*\\([^)]*\\)', '', name)
    name = name.lower()
    common_suffixes = [
        ', inc.', ' inc.', ', llc', ' llc', ', ltd.', ' ltd.', ' ltd', ', gmbh', ' gmbh',
        ', s.a.', ' s.a.', ' plc', ' se', ' ag', ' oyj', ' ab', ' as', ' nv', ' bv', ' co.', ' co'
        ' corporation', ' company', ' group', ' holding', ' solutions', ' services',
        ' technologies', ' systems', ' international'
    ]
    for suffix in common_suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = re.sub(r'[^\\w-]', '', name)
    return name.strip('-')

async def check_domain_availability(domain: str, timeout: float = 3.0) -> bool:
    """Проверяет доступность домена и возвращает валидный HTTP ответ."""
    try:
        try:
            socket.gethostbyname(domain)
        except socket.gaierror:
            # print(f"DNS resolution failed for {domain}")
            return False

        async with aiohttp.ClientSession() as session:
            tasks = [
                session.head(f"https://{domain}", timeout=timeout, allow_redirects=True),
                session.head(f"http://{domain}", timeout=timeout, allow_redirects=True)
            ]
            # Используем return_exceptions=True чтобы обработать ошибки индивидуально
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            for resp_or_exc in responses:
                if isinstance(resp_or_exc, aiohttp.ClientResponse):
                    # print(f"Checked {resp_or_exc.url}: {resp_or_exc.status}")
                    if 200 <= resp_or_exc.status < 400:
                        await resp_or_exc.release() # Важно освободить соединение
                        return True
                    await resp_or_exc.release()
                # elif isinstance(resp_or_exc, Exception):
                    # print(f"Exception for {domain} during HTTP check: {resp_or_exc}")
        return False
    except Exception as e:
        # print(f"General exception for {domain} in check_domain_availability: {e}")
        return False

async def check_domains_batch(domains: list[str], batch_size: int = 10) -> list[str]:
    """Проверяет доступность доменов батчами. Возвращает список доступных URL (с https://)."""
    found_domains_urls = []
    for i in range(0, len(domains), batch_size):
        batch = domains[i:i + batch_size]
        tasks = [check_domain_availability(domain) for domain in batch]
        results = await asyncio.gather(*tasks)
        
        for domain, is_available in zip(batch, results):
            if is_available:
                found_domains_urls.append(f"https://{domain}") # Возвращаем с https для единообразия
    return found_domains_urls

async def find_domain_by_tld(company_name: str, serper_api_key: str | None = None, openai_api_key: str | None = None) -> list[str]:
    """Пытается найти домены компании, проверяя популярные TLD."""
    common_tlds = [
        "com", "org", "net", "io", "co", "app", "dev", "tech", "digital", "cloud", "online", "site", "website", "info", "biz", "me", "tv", "studio",
        "agency", "group", "team", "solutions", "services", "systems", "technology", "international", "global", "world", "media",
        "eu", "uk", "de", "fr", "it", "es", "pt", "nl", "be", "ch", "at", "se", "no", "dk", "fi", "pl", "cz", "sk", "hu", "ro", "bg", "gr", "hr", "si",
        "jp", "cn", "kr", "in", "sg", "my", "id", "th", "vn", "ph", "hk", "tw", "ae", "sa", "qa", "kw", "bh", "om", "tr", "il",
        "us", "ca", "mx", "br", "ar", "cl", "co", "pe", "uy", "ve", "ec", "py", "bo", "cr", "pa", "do", "pr",
        "au", "nz", 
        "za", "ng", "ke", "eg", 
        "asia"
    ]
    common_tlds = list(dict.fromkeys(common_tlds)) # Убираем дубликаты
    clean_name = normalize_name_for_domain_comparison(company_name)
    if not clean_name:
        return []
        
    domains_to_check = [f"{clean_name}.{tld}" for tld in common_tlds]
    return await check_domains_batch(domains_to_check, batch_size=20)

def parse_wikipedia_website(wiki_url: str) -> str | None:
    """Парсит официальный сайт компании из инфобокса Wikipedia.
    Возвращает URL сайта или саму wiki_url если не найден сайт или произошла ошибка.
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(wiki_url, headers=headers, timeout=10)
        response.raise_for_status() # Проверка на HTTP ошибки
            
        soup = BeautifulSoup(response.text, 'html.parser')
        infobox = soup.find('table', {'class': ['infobox', 'vcard']}) # Ищем по нескольким классам
        if not infobox: infobox = soup.find('table', class_=lambda x: x and 'infobox' in x)


        if not infobox:
            # print(f"No infobox found on {wiki_url}")
            return wiki_url 

        # Более гибкий поиск "Website" или "Веб-сайт"
        website_header_texts = ['Website', 'Веб-сайт', 'Сайт']
        website_row = None
        for text in website_header_texts:
            website_row = infobox.find(['th', 'td'], string=re.compile(f'^{re.escape(text)}$', re.IGNORECASE))
            if website_row:
                break
        
        if not website_row:
            # print(f"No website row found in infobox on {wiki_url}")
            return wiki_url 
            
        website_cell = website_row.find_next_sibling('td')
        if not website_cell:
            # print(f"No website cell found for {wiki_url}")
            return wiki_url 
            
        website_link_tag = website_cell.find('a', href=True)
        if website_link_tag and website_link_tag['href'].startswith(('http://', 'https://')):
            return website_link_tag['href']
        
        # Попытка найти URL в тексте ячейки, если нет тега <a>
        url_in_text = re.search(r'https?://[^\s<>"]+|www\\.[^\s<>"]+', website_cell.get_text())
        if url_in_text:
            url_str = url_in_text.group(0)
            if not url_str.startswith(('http://', 'https://')):
                url_str = 'http://' + url_str # Добавляем http если только www
            return url_str

        # print(f"No website link found in cell for {wiki_url}")
        return wiki_url
    except requests.exceptions.RequestException as e:
        # print(f"Request error parsing Wikipedia {wiki_url}: {e}")
        return wiki_url
    except Exception as e:
        # print(f"Error parsing Wikipedia {wiki_url}: {e}")
        return wiki_url

def get_wikidata_url(company_name: str, language_code: str = 'en') -> str | None:
    """Получает официальный URL компании из Wikidata через SPARQL."""
    query = f"""
    SELECT ?company ?url WHERE {{
      ?company rdfs:label "{company_name}"@{language_code};
               wdt:P856 ?url.
      FILTER(ISURI(?url)) # Убедимся, что это действительно URL
    }} LIMIT 1
    """
    endpoint_url = "https://query.wikidata.org/sparql"
    headers = {
        'Accept': 'application/sparql-results+json',
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 IntegrationBot/1.0'
    }
    try:
        response = requests.get(endpoint_url, params={'query': query}, headers=headers, timeout=10)
        response.raise_for_status()
        results = response.json()
        bindings = results.get('results', {}).get('bindings')
        if bindings and 'url' in bindings[0] and 'value' in bindings[0]['url']:
            return bindings[0]['url']['value']
    except requests.exceptions.RequestException as e:
        print(f"Wikidata request error for {company_name}: {e}")
    except Exception as e:
        print(f"Error processing Wikidata response for {company_name}: {e}")
    return None

def calculate_relevance_score(company_name: str, wiki_url: str, title: str | None = None, snippet: str | None = None) -> float:
    """Вычисляет оценку релевантности Wikipedia страницы для компании."""
    # Используем название страницы из URL как основной источник
    path = urlparse(wiki_url).path
    if '/wiki/' not in path:
        return 0.0
    page_name_from_url = unquote(path.split('/wiki/')[-1]).replace('_', ' ').lower()
    
    # Нормализуем имя компании
    company_name_norm = company_name.lower()
    company_name_words = company_name_norm.split()

    score = 0.0

    # 1. Прямое совпадение с URL
    if company_name_norm in page_name_from_url:
        score += 2.0
    # Оценка по словам для URL
    page_name_words = page_name_from_url.split()
    common_words_url = len(set(company_name_words) & set(page_name_words))
    score += common_words_url

    # 2. Используем предоставленный title если есть
    if title:
        title_norm = title.lower()
        if company_name_norm in title_norm:
            score += 1.5
        common_words_title = len(set(company_name_words) & set(title_norm.split()))
        score += common_words_title * 0.5

    # 3. Используем snippet если есть
    if snippet:
        snippet_norm = snippet.lower()
        if company_name_norm in snippet_norm:
            score += 1.0
        # Можно добавить более сложный анализ совпадений в snippet
        if any(word in snippet_norm for word in ["official website", "company", "corporation", "inc."]):
             score += 0.5
             
    # Штраф за "(company)" или подобные уточнения, если они не часть имени
    if "(company)" in page_name_from_url and "(company)" not in company_name_norm:
        score -= 0.5
    if "(disambiguation)" in page_name_from_url: # Сильный штраф за страницы неоднозначностей
        score -= 2.0

    return max(0, score)


def filter_wikipedia_links(search_results: list, company_name: str) -> list:
    """Фильтрует результаты поиска, оставляя только ссылки на Wikipedia, оценивая и сортируя их."""
    wiki_links = []
    for result in search_results:
        url = result.get('link', '')
        title = result.get('title')
        snippet = result.get('snippet')
        
        parsed_url = urlparse(url)
        if 'wikipedia.org' in parsed_url.netloc and '/wiki/' in parsed_url.path and 'disambiguation' not in parsed_url.path.lower():
            relevance = calculate_relevance_score(company_name, url, title, snippet)
            if relevance > 0: # Добавляем только если есть хоть какая-то релевантность
                wiki_links.append({
                    'link': url,
                    'title': title,
                    'snippet': snippet,
                    'relevance_score': relevance
                })
    
    return sorted(wiki_links, key=lambda x: x.get('relevance_score', 0), reverse=True)

async def choose_best_wiki_link(company_name: str, candidates: list, openai_api_key: str) -> str | None:
    """Выбирает наиболее подходящую страницу Wikipedia через LLM, если есть кандидаты."""
    if not candidates:
        return None
    
    # Если есть только один кандидат с хорошей оценкой, можно его и вернуть
    if len(candidates) == 1 and candidates[0].get('relevance_score', 0) > 2.0 : # Порог можно настроить
        return candidates[0]['link']

    try:
        candidates_text = []
        for idx, candidate in enumerate(candidates[:5], 1): # Ограничиваем до топ-5 для LLM
            text = f"{idx}. URL: {candidate['link']}\\n   Title: {candidate.get('title', 'N/A')}\\n   Relevance: {candidate.get('relevance_score', 0):.2f}"
            if 'snippet' in candidate:
                text += f"\\n   Snippet: {candidate['snippet'][:200]}..." # Обрезаем сниппет
            candidates_text.append(text)

        system_prompt = f"""You are an expert assistant. Your task is to identify the single most relevant Wikipedia page for the company: "{company_name}".
Analyze the provided list of Wikipedia URLs, their titles, relevance scores, and snippets.
Select EXACTLY ONE URL that is most likely to be the main Wikipedia page for THIS SPECIFIC company.
Consider:
1.  Relevance scores (higher is better).
2.  Titles and Snippets for direct mentions of the company and its business.
3.  URL patterns (prefer cleaner URLs, avoid disambiguation pages if possible, unless it's the only relevant one).
Output ONLY the selected URL. No explanations, no other text. If no URL seems truly relevant, output "None".
"""
        user_prompt = f"""Candidate Wikipedia pages for "{company_name}":

{chr(10).join(candidates_text)}

Which single URL is the main Wikipedia page for this company?
Selected URL:"""

        # print(f"--- LLM Prompt for {company_name} ---")
        # print(user_prompt)
        # print("------------------------------------")

        aclient = AsyncOpenAI(api_key=openai_api_key)
        response = await aclient.chat.completions.create(
            model="gpt-3.5-turbo-0125", # Можно использовать более новую или дешевую модель
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=100, # URL обычно не длинный
            top_p=1.0,
            n=1,
            stop=["\\n"]
        )
        
        selected_url = response.choices[0].message.content.strip()
        # print(f"LLM ({response.model}) for '{company_name}' chose: {selected_url} (usage: {response.usage})")
        
        if selected_url.lower() == "none" or not selected_url.startswith("http"):
            # Если LLM не уверен, или вернул что-то не то, пробуем взять лучшего по скору
            # print(f"LLM returned '{selected_url}', falling back to highest score if available.")
            return candidates[0]['link'] if candidates else None
            
        return selected_url

    except Exception as e:
        print(f"LLM analysis error for {company_name}: {e}")
        # В случае ошибки LLM, возвращаем лучшего кандидата по relevance_score
        if candidates:
            return candidates[0]['link']
        return None

def extract_company_name_from_wiki_url(wiki_url: str) -> str | None:
    """Извлекает название компании из URL Wikipedia."""
    try:
        path = urlparse(wiki_url).path
        if '/wiki/' not in path:
            return None
        page_name = unquote(path.split('/wiki/')[-1])
        page_name = re.sub(r'\\s*\\([^)]*\\)', '', page_name) # Удаляем всё в скобках
        page_name = page_name.replace('_', ' ').strip()
        return page_name
    except Exception:
        return None

# --- Основная функция-оркестратор ---

async def find_company_homepage(
    company_name: str, 
    serper_api_key: str, 
    openai_api_key: str, # Убедимся, что тип str
    wikidata_lang: str = 'en'
) -> dict | None:
    """
    Ищет домашнюю страницу компании, используя различные методы.
    Возвращает словарь {'url': 'found_url', 'source': 'method'} или None.
    """
    if not company_name or not company_name.strip():
        return None
    
    # Убедимся, что openai_api_key не None перед использованием, если это возможно
    # В choose_best_wiki_link AsyncOpenAI(api_key=openai_api_key) ожидает строку
    if not openai_api_key: # Добавил проверку, чтобы избежать ошибки если ключ None
        print(f"OpenAI API key is missing for {company_name}. LLM-based Wiki selection will be skipped.")
        # Можно решить, как обрабатывать - либо падать, либо пропускать шаги с LLM.
        # В текущей choose_best_wiki_link если openai_api_key будет None, будет ошибка при создании AsyncOpenAI.
        # Для простоты, если ключ не предоставлен, LLM этап будет пропущен или вызовет ошибку ниже.
        # Правильнее было бы передавать AsyncOpenAI клиент, а не ключ, если возможно в архитектуре.
        # Но раз уж передаем ключ, он должен быть валидным.

    # 1. Поиск в Wikidata
    # print(f"\\nProcessing {company_name}...")
    wikidata_url = get_wikidata_url(company_name, language_code=wikidata_lang)
    if wikidata_url:
        # print(f"Found in Wikidata for {company_name}: {wikidata_url}")
        if await check_domain_availability(urlparse(wikidata_url).netloc):
             return {"url": wikidata_url, "source": "wikidata"}
        # print(f"Wikidata URL {wikidata_url} for {company_name} is not accessible.")


    # 2. Поиск по TLD (асинхронный)
    # print(f"Searching TLDs for {company_name}...")
    tld_found_urls = await find_domain_by_tld(company_name, serper_api_key, openai_api_key) # openai_api_key здесь не используется, но пусть будет
    if tld_found_urls:
        # print(f"Found by TLD for {company_name}: {tld_found_urls[0]}")
        return {"url": tld_found_urls[0], "source": "tld_check"} # Берем первый найденный

    # 3. Поиск в Google (Serper API) для страницы Wikipedia
    # print(f"Searching Google via Serper for {company_name} Wikipedia page...")
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    # Запрос делаем более общим, чтобы найти официальный сайт или Википедию
    # Можно сделать два запроса: один на вики, другой на оф. сайт напрямую
    queries = [
        f"{company_name} official website",
        f"{company_name} wikipedia"
    ]
    
    organic_results = []
    for q_idx, q_val in enumerate(queries):
        payload = json.dumps({"q": q_val, "num": 5, "gl": "us", "hl": "en"}) # Меньше результатов для скорости
        try:
            response = requests.post("https://google.serper.dev/search", headers=headers, data=payload, timeout=10)
            response.raise_for_status()
            search_data = response.json()
            if search_data and "organic" in search_data:
                # Добавляем источник запроса для последующей фильтрации
                for item in search_data["organic"]:
                    item["query_source"] = "website_search" if q_idx == 0 else "wiki_search"
                organic_results.extend(search_data["organic"])
        except requests.exceptions.RequestException as e:
            print(f"Serper request error for '{q_val}': {e}")
            continue # Пропускаем к следующему запросу если этот не удался
        except Exception as e:
            print(f"Error processing Serper response for '{q_val}': {e}")
            continue


    if not organic_results:
        # print(f"No results from Serper for {company_name}.")
        return None

    # 3.1 Попытка найти прямой сайт из результатов "official website"
    for result in organic_results:
        if result.get("query_source") == "website_search":
            url = result.get('link')
            parsed_url = urlparse(url)
            # Простая эвристика: если имя компании (нормализованное) есть в домене - это хороший кандидат
            normalized_company_name_for_domain = normalize_name_for_domain_comparison(company_name)
            if normalized_company_name_for_domain and normalized_company_name_for_domain in parsed_url.netloc.lower():
                if await check_domain_availability(parsed_url.netloc):
                    # print(f"Found direct website via Serper for {company_name}: {url}")
                    return {"url": url, "source": "serper_direct_website"}

    # 3.2 Обработка ссылок Wikipedia
    wiki_links_candidates = filter_wikipedia_links(
        [res for res in organic_results if res.get("query_source") == "wiki_search"], 
        company_name
    )

    if wiki_links_candidates:
        # print(f"Found {len(wiki_links_candidates)} Wikipedia candidates for {company_name}.")
        # print(f"Top candidate: {wiki_links_candidates[0]['link']} (Score: {wiki_links_candidates[0]['relevance_score']})")
        
        # Выбор лучшей ссылки LLM или по скору
        selected_wiki_url = None
        if openai_api_key: # Только если есть ключ, пытаемся использовать LLM
            selected_wiki_url = await choose_best_wiki_link(company_name, wiki_links_candidates, openai_api_key)
        elif wiki_links_candidates: # Если ключа нет, берем лучший по скору
            selected_wiki_url = wiki_links_candidates[0]['link']
            print(f"OpenAI key missing for {company_name}, using top scored Wiki link: {selected_wiki_url}")

        if selected_wiki_url:
            # print(f"Selected Wikipedia URL for {company_name}: {selected_wiki_url}")
            # 3.2.1 Попытка получить URL из Wikidata по имени из Wikipedia URL
            wiki_company_name = extract_company_name_from_wiki_url(selected_wiki_url)
            if wiki_company_name and wiki_company_name.lower() != company_name.lower(): # Если имя отличается, пробуем еще раз Wikidata
                # print(f"Trying Wikidata with name from Wiki URL: {wiki_company_name}")
                wikidata_url_from_wiki_name = get_wikidata_url(wiki_company_name, language_code=wikidata_lang)
                if wikidata_url_from_wiki_name:
                    if await check_domain_availability(urlparse(wikidata_url_from_wiki_name).netloc):
                        # print(f"Found in Wikidata (via Wiki name) for {company_name}: {wikidata_url_from_wiki_name}")
                        return {"url": wikidata_url_from_wiki_name, "source": "wikidata_via_wiki_name"}
                    # print(f"Wikidata URL (via Wiki name) {wikidata_url_from_wiki_name} for {company_name} is not accessible.")


            # 3.2.2 Парсинг выбранной страницы Wikipedia
            # print(f"Parsing Wikipedia page {selected_wiki_url} for {company_name}...")
            parsed_site_from_wiki = parse_wikipedia_website(selected_wiki_url)
            if parsed_site_from_wiki and parsed_site_from_wiki != selected_wiki_url: # Убедимся, что это не сама ссылка на Вики
                parsed_domain = urlparse(parsed_site_from_wiki).netloc
                if parsed_domain and await check_domain_availability(parsed_domain):
                    # print(f"Found website via Wikipedia parsing for {company_name}: {parsed_site_from_wiki}")
                    return {"url": parsed_site_from_wiki, "source": "wikipedia_parser"}
                # print(f"Parsed Wikipedia site {parsed_site_from_wiki} for {company_name} is not accessible or invalid.")
            
            # Если парсер не нашел или сайт недоступен, и LLM выбрал эту страницу Вики,
            # то, возможно, сама страница Вики и есть то, что нужно (хотя мы ищем сайт)
            # В данном контексте мы ищем именно сайт, поэтому не возвращаем wiki_url как результат,
            # если только это не было единственной находкой из авторитетного источника.
            # Однако, если других опций нет, и LLM подтвердил релевантность страницы,
            # можно вернуть ее как "последнюю надежду" или для информации.
            # Но цель - homepage, так что это под вопросом. Пока не возвращаем.
            # print(f"Could not extract a valid website from {selected_wiki_url} for {company_name}. LLM chose this page.")
            # Можно вернуть саму страницу Википедии, если ничего другого нет, и она релевантна
            # return {"url": selected_wiki_url, "source": "wikipedia_page_llm_verified"}


    # 4. Если ничего не найдено выше, но есть органические результаты от Serper "official website"
    # можно попробовать вернуть самый первый из них, если он доступен.
    for result in organic_results:
        if result.get("query_source") == "website_search":
            url = result.get('link')
            if url:
                parsed_url_netloc = urlparse(url).netloc
                if parsed_url_netloc and await check_domain_availability(parsed_url_netloc):
                    # print(f"Fallback: Using first Serper direct result for {company_name}: {url}")
                    return {"url": url, "source": "serper_direct_fallback"}
                # print(f"Serper fallback URL {url} for {company_name} is not accessible.")
    
    # print(f"Homepage not found for {company_name} after all methods.")
    return None

# Для локального тестирования модуля (удалить или закомментировать при интеграции)
async def _test_module():
    # load_dotenv() # Для теста нужно будет загрузить переменные, если запускать отдельно
    # Для этого добавим импорт load_dotenv только для этого блока
    from dotenv import load_dotenv
    load_dotenv()
    SERPER_API_KEY = os.getenv("SERPER_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    if not SERPER_API_KEY or not OPENAI_API_KEY:
        print("SERPER_API_KEY or OPENAI_API_KEY not found in .env for testing.")
        return

    test_companies = [
        "OpenAI",
        "Microsoft",
        "Google",
        "Unilever",
        "Vale S.A.", # Компания с точкой в имени
        "Несуществующая компания XYZ123",
        "Rostelecom",
        "Example Inc (California)", # Компания с уточнением
        "Gooogle", # с опечаткой
        "Apple Inc."
    ]

    for company in test_companies:
        print(f"\\n----- Testing for: {company} -----")
        result = await find_company_homepage(company, SERPER_API_KEY, OPENAI_API_KEY)
        if result:
            print(f"SUCCESS: Found for {company} -> {result['url']} (Source: {result['source']})")
        else:
            print(f"FAILURE: Not found for {company}")

if __name__ == '__main__':
    # pass # Раскомментировать для запуска _test_module
    # asyncio.run(_test_module()) # Оставляем закомментированным для интеграции
    pass 