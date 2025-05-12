import requests
import json
from dotenv import load_dotenv
import os
import pandas as pd
from pathlib import Path
from urllib.parse import urlparse, unquote
import socket
import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup
from openai import AsyncOpenAI

def normalize_name_for_domain_comparison(name: str) -> str:
    """Очищает название компании для сравнения с доменом."""
    # Удаляем всё в скобках
    name = re.sub(r'\s*\([^)]*\)', '', name)
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
    name = re.sub(r'[^\w-]', '', name)
    return name.strip('-')

async def check_domain_availability(domain: str, timeout: float = 2.0) -> bool:
    """Проверяет доступность домена и возвращает валидный HTTP ответ."""
    try:
        # Сначала пробуем разрешить DNS
        try:
            socket.gethostbyname(domain)
        except socket.gaierror:
            return False

        # Пробуем HTTPS сначала
        async with aiohttp.ClientSession() as session:
            try:
                async with session.head(f"https://{domain}", timeout=timeout, allow_redirects=True) as response:
                    if 200 <= response.status < 400:
                        return True
            except:
                pass

            # Если HTTPS не сработал, пробуем HTTP
            try:
                async with session.head(f"http://{domain}", timeout=timeout, allow_redirects=True) as response:
                    if 200 <= response.status < 400:
                        return True
            except:
                pass

        return False
    except Exception:
        return False

async def find_domain_by_tld(company_name: str) -> str | None:
    """Пытается найти домен компании, проверяя популярные TLD."""
    # Популярные TLD в порядке приоритета
    common_tlds = [
        "com", "ru", "ua", "cz", "ch", "org", "io", "net", "co", "ai", "app", "dev", "tech", "digital",
        "cloud", "online", "site", "website", "info", "biz", "me", "tv", "studio",
        "agency", "group", "team", "solutions", "services", "systems", "technology"
    ]
    
    # Очищаем название компании
    clean_name = normalize_name_for_domain_comparison(company_name)
    
    # Пробуем каждый TLD
    for tld in common_tlds:
        domain = f"{clean_name}.{tld}"
        if await check_domain_availability(domain):
            return f"https://{domain}"
    
    return None

def parse_wikipedia_website(wiki_url: str) -> str | None:
    """Парсит официальный сайт компании из инфобокса Wikipedia."""
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
    except Exception:
        return wiki_url  # При любой ошибке возвращаем ссылку на Wikipedia

def load_company_names(file_path: str | Path, col_index: int = 0) -> list[str] | None:
    """Loads the first column from Excel/CSV, handles headers, returns list of names."""
    file_path_str = str(file_path)
    df_loaded = None
    read_params = {"usecols": [col_index], "header": 0}
    try:
        reader = pd.read_excel if file_path_str.lower().endswith(('.xlsx', '.xls')) else pd.read_csv
        df_loaded = reader(file_path_str, **read_params)
    except (ValueError, ImportError, FileNotFoundError) as ve:
        print(f"Initial read failed for {file_path_str}, trying header=None: {ve}")
        read_params["header"] = None
        try: 
            df_loaded = reader(file_path_str, **read_params)
        except Exception as read_err_no_header: 
            print(f"Error reading {file_path_str} even with header=None: {read_err_no_header}")
            return None
    except Exception as read_err: 
        print(f"Error reading file {file_path_str}: {read_err}")
        return None

    if df_loaded is not None and not df_loaded.empty:
        company_names = df_loaded.iloc[:, 0].astype(str).str.strip().tolist()
        valid_names = [name for name in company_names if name and name.lower() not in ['nan', '']]
        if valid_names: 
            return valid_names
        else: 
            print(f"No valid names in first column of {file_path_str}.")
            return None
    else: 
        print(f"Could not load data from first column of {file_path_str}.")
        return None

def get_wikidata_url(company_name: str) -> str | None:
    """Получает официальный URL компании из Wikidata через SPARQL."""
    # Формируем SPARQL запрос
    query = f"""
    SELECT ?company ?url WHERE {{
      ?company rdfs:label "{company_name}"@en;
               wdt:P856 ?url.
    }}
    """
    
    # URL для SPARQL эндпоинта Wikidata
    url = "https://query.wikidata.org/sparql"
    
    # Заголовки для запроса
    headers = {
        'Accept': 'application/sparql-results+json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        # Отправляем запрос
        response = requests.get(url, params={'query': query}, headers=headers)
        if response.status_code == 200:
            results = response.json()
            # Проверяем, есть ли результаты
            if results.get('results', {}).get('bindings'):
                # Берем первый URL из результатов
                return results['results']['bindings'][0]['url']['value']
    except Exception as e:
        print(f"Ошибка при запросе к Wikidata: {e}")
    
    return None

def calculate_relevance_score(company_name: str, wiki_url: str) -> float:
    """Вычисляет оценку релевантности Wikipedia страницы для компании."""
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
    """Фильтрует результаты поиска, оставляя только ссылки на Wikipedia и оценивая их релевантность."""
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

async def choose_best_wiki_link(company_name: str, candidates: list) -> str | None:
    """Выбирает наиболее подходящую страницу Wikipedia через LLM."""
    try:
        # Формируем список кандидатов с их сниппетами и релевантностью
        candidates_text = []
        for idx, candidate in enumerate(candidates, 1):
            candidates_text.append(f"{idx}. URL: {candidate['link']}")
            if 'snippet' in candidate:
                candidates_text.append(f"   Snippet: {candidate['snippet']}")
            if 'relevance_score' in candidate:
                candidates_text.append(f"   Relevance: {candidate['relevance_score']:.2f}")
            candidates_text.append("")

        system_prompt = f"""You are an expert assistant that identifies the single most relevant Wikipedia page for a company.
Company Name: {company_name}

Your task is to analyze the provided list of Wikipedia URLs and their snippets.
Select EXACTLY ONE URL that is most likely to be the main Wikipedia page for this company.
Consider:
1. Relevance scores (higher is better)
2. Snippets content (look for official company information)
3. URL patterns (prefer shorter, cleaner URLs)
4. Company name matches in URL and snippet

Output ONLY the selected URL. No explanations, no other text."""

        user_prompt = f"""Here are the candidate Wikipedia pages for {company_name}:

{chr(10).join(candidates_text)}

Which single URL is the main Wikipedia page for this company?
Answer:"""

        openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=150,
            top_p=1.0,
            n=1,
            stop=["\n"]
        )

        selected_url = response.choices[0].message.content.strip()
        # print(f"LLM выбрал: {selected_url}")
        return selected_url

    except Exception as e:
        print(f"\n!!! Ошибка при анализе через LLM: {e}")
        return None

def extract_company_name_from_wiki_url(wiki_url: str) -> str | None:
    """Извлекает название компании из URL Wikipedia."""
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
    except Exception:
        return None

async def process_company(company_name: str, serper_api_key: str):
    # Сначала пробуем получить URL из Wikidata
    wikidata_url = get_wikidata_url(company_name)
    if wikidata_url:
        print(f"\nОфициальный сайт из Wikidata для {company_name}:")
        print(f"URL: {wikidata_url}")
        return "wikidata"
    
    # Если через Wikidata не нашли, пробуем найти через проверку доменов
    domain_url = await find_domain_by_tld(company_name)
    if domain_url:
        print(f"\nНайден домен для {company_name}:")
        print(f"URL: {domain_url}")
        return "domains"
    
    # Если не нашли ни через Wikidata, ни через домены, ищем через Google
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    payload = json.dumps({
        "q": f"company{company_name} official website wikipedia",
        "num": 10,
        "gl": "us",
        "hl": "en"
    })
    
    response = requests.post("https://google.serper.dev/search", headers=headers, data=payload)
    if response.status_code == 200:
        results = response.json()
        if results and "organic" in results:
            wiki_links = filter_wikipedia_links(results["organic"], company_name)
            if wiki_links:
                selected_url = await choose_best_wiki_link(company_name, wiki_links)
                
                if selected_url:
                    # Пробуем получить название компании из URL Wikipedia
                    wiki_company_name = extract_company_name_from_wiki_url(selected_url)
                    if wiki_company_name:
                        # Пробуем найти через Wikidata используя название из Wikipedia
                        wikidata_url = get_wikidata_url(wiki_company_name)
                        if wikidata_url:
                            print(f"\nНайден официальный сайт в Wikidata для {company_name} (через Wikipedia):")
                            print(f"URL: {wikidata_url}")
                            return "wikidata"
                    
                    # Если через Wikidata не нашли, пробуем парсить Wikipedia
                    website_url = parse_wikipedia_website(selected_url)
                    if website_url != selected_url:  # Если нашли официальный сайт в инфобоксе
                        print(f"\nНайден официальный сайт в Wikipedia для {company_name}:")
                        print(f"URL: {website_url}")
                        return "wiki_parser"
                    else:  # Если вернулась ссылка на Wikipedia
                        print(f"\nВыбор LLM для {company_name}:")
                        print(f"URL: {website_url}")
                        return "llm"
                else:
                    return "google"
            else:
                return "not_found"
        else:
            return "not_found"
    else:
        return "not_found"

async def main():
    load_dotenv()
    serper_api_key = os.getenv("SERPER_API_KEY")
    if not serper_api_key:
        print("Error: SERPER_API_KEY not found in .env file")
        exit(1)
    
    # Путь к файлу с компаниями
    input_file = "input/part2.xlsx"  # Измените на путь к вашему файлу
    
    # Счетчики для статистики
    total_companies = 0
    found_in_wikidata = 0
    found_in_domains = 0
    found_in_google = 0
    found_in_wiki_parser = 0
    found_in_llm = 0
    not_found = 0
    
    company_names = load_company_names(input_file)
    if company_names:
        total_companies = len(company_names)
        print(f"Loaded {total_companies} companies from {input_file}")
        for company_name in company_names:
            result = await process_company(company_name, serper_api_key)
            if result == "wikidata":
                found_in_wikidata += 1
            elif result == "domains":
                found_in_domains += 1
            elif result == "google":
                found_in_google += 1
            elif result == "wiki_parser":
                found_in_wiki_parser += 1
            elif result == "llm":
                found_in_llm += 1
            else:
                not_found += 1
        
        # Выводим статистику
        print("\n=== Статистика поиска ===")
        print(f"Всего компаний: {total_companies}")
        print(f"Найдено через Wikidata: {found_in_wikidata} ({found_in_wikidata/total_companies*100:.1f}%)")
        print(f"Найдено через проверку доменов: {found_in_domains} ({found_in_domains/total_companies*100:.1f}%)")
        print(f"Найдено через парсер Wikipedia: {found_in_wiki_parser} ({found_in_wiki_parser/total_companies*100:.1f}%)")
        print(f"Найдено через LLM: {found_in_llm} ({found_in_llm/total_companies*100:.1f}%)")
        print(f"Найдено через Google: {found_in_google} ({found_in_google/total_companies*100:.1f}%)")
        print(f"Не найдено: {not_found} ({not_found/total_companies*100:.1f}%)")
    else:
        print(f"Failed to load companies from {input_file}")

if __name__ == "__main__":
    asyncio.run(main()) 