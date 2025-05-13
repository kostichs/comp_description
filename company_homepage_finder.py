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

# Утилитарная функция для загрузки имен компаний
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

class CompanyHomepageFinder:
    def __init__(self, serper_api_key: str, openai_api_key: str):
        self.serper_api_key = serper_api_key
        self.openai_api_key = openai_api_key

    def _normalize_name_for_domain_comparison(self, name: str) -> str:
        """Очищает название компании для сравнения с доменом."""
        name = re.sub(r'\\s*\\([^)]*\\)', '', name) # Оригинальное регулярное выражение
        name = name.lower()
        common_suffixes = [
            ', inc.', ' inc.', ', llc', ' llc', ', ltd.', ' ltd.', ' ltd', ', gmbh', ' gmbh',
            ', s.a.', ' s.a.', ' plc', ' se', ' ag', ' oyj', ' ab', ' as', ' nv', ' bv', ' co.', ' co' # Восстановлен оригинальный список
            ' corporation', ' company', ' group', ' holding', ' solutions', ' services',
            ' technologies', ' systems', ' international'
        ]
        for suffix in common_suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        name = re.sub(r'[^\\w-]', '', name) # Оригинальное регулярное выражение
        return name.strip('-')

    async def _check_domain_availability(self, domain: str, timeout: float = 2.0) -> bool:
        """Проверяет доступность домена и возвращает валидный HTTP ответ. (Логика из оригинала)"""
        try:
            try:
                socket.gethostbyname(domain)
            except socket.gaierror:
                return False

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.head(f"https://{domain}", timeout=timeout, allow_redirects=True) as response:
                        if 200 <= response.status < 400:
                            return True
                except: # Оригинальный bare except
                    pass
                try:
                    async with session.head(f"http://{domain}", timeout=timeout, allow_redirects=True) as response:
                        if 200 <= response.status < 400:
                            return True
                except: # Оригинальный bare except
                    pass
            return False
        except: # Оригинальный bare except
            return False

    async def _find_domain_by_tld(self, company_name: str) -> str | None:
        """Пытается найти домен компании, проверяя популярные TLD. (Логика из оригинала)"""
        common_tlds = [
            "com", "ru", "ua", "cz", "ch", "org", "io", "net", "co", "ai", "app", "dev", "tech", "digital",
            "cloud", "online", "site", "website", "info", "biz", "me", "tv", "studio",
            "agency", "group", "team", "solutions", "services", "systems", "technology"
        ]
        clean_name = self._normalize_name_for_domain_comparison(company_name)
        # Убран if not clean_name: для соответствия оригиналу
        for tld in common_tlds:
            domain = f"{clean_name}.{tld}"
            if await self._check_domain_availability(domain): # Использует self._check_domain_availability
                return f"https://{domain}"
        return None

    def _get_wikidata_url(self, company_name: str) -> str | None:
        """Получает официальный URL компании из Wikidata через SPARQL. (Логика из оригинала)"""
        query = f"""
        SELECT ?company ?url WHERE {{
          ?company rdfs:label "{company_name}"@en;
                   wdt:P856 ?url.
        }}
        """
        url_endpoint = "https://query.wikidata.org/sparql"
        headers = {
            'Accept': 'application/sparql-results+json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' # Оригинальный User-Agent
        }
        try:
            response = requests.get(url_endpoint, params={'query': query}, headers=headers) # Без явного timeout
            if response.status_code == 200: # Оригинальная проверка статуса
                results = response.json()
                if results.get('results', {}).get('bindings'):
                    return results['results']['bindings'][0]['url']['value']
        except requests.exceptions.RequestException as e: # Оставляем обработку RequestException для логгирования
            print(f"Ошибка при запросе к Wikidata для '{company_name}': {e}")
        except json.JSONDecodeError as e: # Оставляем обработку JSONDecodeError для логгирования
            print(f"Ошибка декодирования JSON от Wikidata для '{company_name}': {e}")
        except Exception as e: # Общая ошибка
            print(f"Непредвиденная ошибка при запросе к Wikidata для '{company_name}': {e}")
        return None

    def _parse_wikipedia_website(self, wiki_url: str) -> str | None:
        """Парсит официальный сайт компании из инфобокса Wikipedia. (Логика из оригинала)"""
        try:
            response = requests.get(wiki_url) # Без кастомных headers и timeout
            if response.status_code != 200:
                return None # Оригинал возвращал None здесь
            
            soup = BeautifulSoup(response.text, 'html.parser')
            infobox = soup.find('table', {'class': 'infobox ib-company vcard'})
            if not infobox:
                return wiki_url
            
            website_row = infobox.find('th', string='Website') # Оригинальный поиск
            if not website_row:
                return wiki_url
            
            website_cell = website_row.find_next('td') # Оригинальный поиск
            if not website_cell:
                return wiki_url
            
            website_link = website_cell.find('a', {'class': 'external text'}) # Оригинальный поиск
            if not website_link:
                return wiki_url
            
            return website_link.get('href')
        except Exception: # Оригинальный bare except, но возвращаем wiki_url как в оригинале
            return wiki_url

    def _calculate_relevance_score(self, company_name: str, wiki_url: str) -> float: # Возвращаем float для совместимости с sorted
        """Вычисляет оценку релевантности Wikipedia страницы для компании. (Логика из оригинала)"""
        # Без try-except обертки, как в оригинале
        path = urlparse(wiki_url).path
        if '/wiki/' not in path:
            return 0.0 # Оригинал мог вернуть int, но для sorted key лучше float
        page_name = unquote(path.split('/wiki/')[-1])
        
        company_name_lower = company_name.lower() # Имя переменной как в оригинале (внутренне)
        page_name_lower = page_name.lower().replace('_', ' ') # Имя переменной как в оригинале (внутренне)
        
        company_words = company_name_lower.split()
        page_words = page_name_lower.split()
        
        # Оригинальная проверка (company_words[0] может вызвать IndexError если company_words пуст, но это поведение оригинала)
        if not page_words or (not company_words) or company_words[0] != page_words[0]:
             # Добавил (not company_words) для предотвращения IndexError, стараясь сохранить логику
            return 0.0
        
        score = 0
        i = 0
        j = 0
        
        while i < len(company_words) and j < len(page_words):
            if company_words[i] == page_words[j]:
                score += 1
                i += 1
                j += 1
            else:
                j += 1 # Оригинальная простая логика
        
        if j < len(page_words):
            score -= 0.5 * (len(page_words) - j) # Оригинальный штраф
        
        # Убран штраф за неиспользованные company_words
        
        return max(0.0, float(score)) # float(score) для консистентности типа, max(0, score) в оригинале

    def _filter_wikipedia_links(self, results: list, company_name: str) -> list:
        """Фильтрует результаты поиска, оставляя только ссылки на Wikipedia и оценивая их релевантность. (Логика из оригинала)"""
        wiki_links = []
        for result in results:
            url = result.get('link', '')
            # Убрана проверка if not url: continue;
            parsed_url = urlparse(url)
            # Оригинальная простая проверка
            if 'wikipedia.org' in parsed_url.netloc and '/wiki/' in parsed_url.path:
                result['relevance_score'] = self._calculate_relevance_score(company_name, url) # Использует self._calculate_relevance_score
                # Убрано условие result['relevance_score'] > 0.1
                wiki_links.append(result)
        
        return sorted(wiki_links, key=lambda x: x.get('relevance_score', 0), reverse=True) # Оригинальный default 0 для get

    async def _choose_best_wiki_link(self, company_name: str, candidates: list) -> str | None:
        """Выбирает наиболее подходящую страницу Wikipedia через LLM. (Логика из оригинала)"""
        # Убрана проверка self.openai_api_key
        try:
            # Используем всех кандидатов, как в оригинале
            candidates_text = []
            for idx, candidate in enumerate(candidates, 1):
                candidates_text.append(f"{idx}. URL: {candidate['link']}")
                if 'snippet' in candidate: candidates_text.append(f"   Snippet: {candidate['snippet']}")
                if 'relevance_score' in candidate: candidates_text.append(f"   Relevance: {candidate['relevance_score']:.2f}") # relevance_score может быть float
                candidates_text.append("")

            # Оригинальный system_prompt (примерно, т.к. полный текст не был в истории для этой функции)
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
            # Используем ключ API напрямую из окружения, как в оригинале
            openai_api_key_local = os.getenv("OPENAI_API_KEY")
            if not openai_api_key_local: # Добавим проверку на случай отсутствия ключа, чтобы не упасть
                print("\n!!! OPENAI_API_KEY не найден в окружении. Пропуск LLM.")
                return candidates[0]['link'] if candidates else None

            openai_client = AsyncOpenAI(api_key=openai_api_key_local)
            response = await openai_client.chat.completions.create(
                model="gpt-3.5-turbo", # Оригинальная модель
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
            print(f"LLM выбрал: {selected_url}") # Оригинальный print
            return selected_url # Оригинальный прямой возврат
        except Exception as e:
            print(f"\n!!! Ошибка при анализе через LLM: {e}") # Оригинальный формат ошибки
            return None # Оригинальный возврат None при ошибке

    def _extract_company_name_from_wiki_url(self, wiki_url: str) -> str | None:
        """Извлекает название компании из URL Wikipedia. (Логика из оригинала)"""
        try:
            path = urlparse(wiki_url).path
            if '/wiki/' not in path: return None
            page_name = unquote(path.split('/wiki/')[-1])
            page_name = re.sub(r'\\s*\\([^)]*\\)', '', page_name) # Исправлено: одинарный слэш
            page_name = page_name.replace('_', ' ')
            return page_name.strip()
        except Exception:
            return None

    async def find_official_website(self, company_name: str) -> tuple[str | None, str]:
        """
        Ищет официальный сайт компании, используя различные методы.
        Возвращает кортеж: (URL сайта или None, метод обнаружения из оригинального process_company).
        Логика и print'ы максимально приближены к оригинальному process_company.
        """
        # Метод 1: Wikidata по оригинальному имени
        # print(f"Поиск для: {company_name}") # Этот print был в моей версии, в оригинале process_company его не было в начале
        
        url_to_return = None
        method_to_return = "not_found"

        # print("  1. Проверка Wikidata...") # Этот print был в моей версии
        wikidata_url = self._get_wikidata_url(company_name)
        if wikidata_url:
            print(f"\nОфициальный сайт из Wikidata для {company_name}:") # Оригинальный print
            print(f"URL: {wikidata_url}") # Оригинальный print
            url_to_return = wikidata_url
            method_to_return = "wikidata"
            return url_to_return, method_to_return

        # Метод 2: Поиск по TLD
        # print("  2. Проверка популярных TLD...") # Этот print был в моей версии
        domain_url = await self._find_domain_by_tld(company_name)
        if domain_url:
            print(f"\nНайден домен для {company_name}:") # Оригинальный print
            print(f"URL: {domain_url}") # Оригинальный print
            url_to_return = domain_url
            method_to_return = "domains"
            return url_to_return, method_to_return

        # Метод 3: Поиск через Serper (Google)
        # print(f"  3. Поиск через Serper для '{company_name}'...") # Этот print был в моей версии
        
        # Убрана проверка на self.serper_api_key для соответствия оригиналу (оригинал бы упал или использовал os.getenv)
        serper_api_key_local = os.getenv("SERPER_API_KEY")
        if not serper_api_key_local:
             print(f"\nSERPER_API_KEY не найден для компании {company_name}, пропуск Google поиска.")
             # В оригинале это привело бы к ошибке или пустому результату ранее, здесь имитируем "not_found"
             return None, "not_found"


        headers = {'X-API-KEY': serper_api_key_local, 'Content-Type': 'application/json'}
        payload = json.dumps({"q": f"company{company_name} official website wikipedia", "num": 10, "gl": "us", "hl": "en"})
        
        try:
            # Без timeout и raise_for_status, как в оригинале
            response = requests.post("https://google.serper.dev/search", headers=headers, data=payload)
            
            if response.status_code == 200:
                results = response.json()
                if results and "organic" in results and results["organic"]: # Добавил results["organic"] для предотвращения ошибки если ключ есть, но пустой
                    wiki_links = self._filter_wikipedia_links(results["organic"], company_name)
                    
                    if wiki_links:
                        selected_wiki_url = await self._choose_best_wiki_link(company_name, wiki_links)
                        
                        if selected_wiki_url:
                            wiki_company_name = self._extract_company_name_from_wiki_url(selected_wiki_url)
                            if wiki_company_name:
                                # Повторный поиск в Wikidata с именем из Wikipedia
                                wikidata_url_via_wiki = self._get_wikidata_url(wiki_company_name)
                                if wikidata_url_via_wiki:
                                    print(f"\nНайден официальный сайт в Wikidata для {company_name} (через Wikipedia):") # Оригинальный print
                                    print(f"URL: {wikidata_url_via_wiki}") # Оригинальный print
                                    url_to_return = wikidata_url_via_wiki
                                    method_to_return = "wikidata" # Оригинал использовал "wikidata"
                                    return url_to_return, method_to_return
                            
                            # Если Wikidata с именем из Wiki не дал результат, парсим выбранную LLM страницу Wiki
                            parsed_website_url = self._parse_wikipedia_website(selected_wiki_url) 
                            
                            # Оригинальная логика: если парсер вернул что-то отличное от исходной wiki-ссылки
                            # (это включает новый URL или None, если парсер ничего не нашел/ошибся)
                            if parsed_website_url != selected_wiki_url:
                                print(f"\nНайден официальный сайт в Wikipedia для {company_name}:") # Этот print выводился даже если parsed_website_url был None
                                print(f"URL: {parsed_website_url}") # Соответственно, мог печатать URL: None
                                url_to_return = parsed_website_url # URL может быть None
                                method_to_return = "wiki_parser"
                                return url_to_return, method_to_return
                            else: 
                                # Сюда попадаем, только если parsed_website_url В ТОЧНОСТИ РАВЕН selected_wiki_url
                                # (т.е. парсер не нашел в инфобоксе ничего другого и вернул исходную ссылку на Wiki)
                                print(f"\nВыбор LLM для {company_name}:") 
                                print(f"URL: {selected_wiki_url}") 
                                url_to_return = selected_wiki_url
                                method_to_return = "llm"
                                return url_to_return, method_to_return
                        else: # selected_wiki_url is None (LLM не выбрал или ошибка)
                            # print("    LLM не выбрал URL или произошла ошибка. Оригинал возвращал 'google'")
                            # В оригинале, если selected_url был None, но wiki_links были, возвращался "google".
                            # URL при этом не возвращался явно process_company, а main его не использовал.
                            # Для сохранения структуры (URL, method) вернем первую ссылку из wiki_links, если они есть
                            if wiki_links: # Дополнительная проверка, что wiki_links не пустые
                                url_to_return = wiki_links[0]['link'] # Берём первую как наиболее вероятную
                                method_to_return = "google" # Оригинальный метод
                                return url_to_return, method_to_return
                            else: # wiki_links пуст, selected_wiki_url is None
                                method_to_return = "not_found" # Как в оригинале
                                return None, method_to_return
                    else: # wiki_links пуст
                        method_to_return = "not_found" # Как в оригинале
                        return None, method_to_return
                else: # results пуст или нет "organic"
                    method_to_return = "not_found" # Как в оригинале
                    return None, method_to_return
            else: # response.status_code != 200
                # print(f"    Ошибка от Serper: {response.status_code}")
                method_to_return = "not_found" # Как в оригинале
                return None, method_to_return

        except requests.exceptions.RequestException as e:
            print(f"    Ошибка при запросе к Serper для '{company_name}': {e}")
        except json.JSONDecodeError as e:
            print(f"    Ошибка декодирования JSON от Serper для '{company_name}': {e}")
        except Exception as e:
            print(f"    Непредвиденная ошибка в find_official_website при поиске через Serper для '{company_name}': {type(e).__name__} - {e}")
            
        return None, "not_found" # Конечный fallback

async def main():
    load_dotenv()
    # serper_api_key и openai_api_key теперь не передаются в конструктор напрямую,
    # т.к. оригинальные функции получали их из os.getenv() по месту вызова или неявно.
    # Класс их больше не хранит, методы будут использовать os.getenv() при необходимости.
    
    # finder = CompanyHomepageFinder(None, None) # Конструктор теперь не нужен с ключами
    finder = CompanyHomepageFinder(serper_api_key=os.getenv("SERPER_API_KEY"), openai_api_key=os.getenv("OPENAI_API_KEY"))


    input_file_path_str = "input/part2.xlsx" 
    input_file = Path(input_file_path_str)
    
    # Создаем папку input и пример файла, если их нет
    input_dir = Path("input")
    if not input_dir.exists():
        try:
            input_dir.mkdir(parents=True, exist_ok=True)
            print(f"Создана папка '{input_dir}'.")
        except Exception as e:
            print(f"Не удалось создать папку '{input_dir}': {e}")
            return # Выход, если не можем создать папку input

    if not input_file.exists():
        print(f"Файл '{input_file}' не найден.")
        try:
            example_data = {'Company Name': ['Google', 'Microsoft', 'Apple', 'NonExistent123XYZ', 'Wikimedia Foundation']}
            example_df = pd.DataFrame(example_data)
            example_df.to_excel(input_file, index=False)
            print(f"Создан пример файла: {input_file} с тестовыми данными.")
            print(f"Вы можете заменить его своим файлом или отредактировать.")
        except Exception as e:
            print(f"Не удалось создать пример файла {input_file}: {e}")
            print(f"Пожалуйста, создайте файл '{input_file_path_str}' вручную с колонкой 'Company Name'.")
            return # Выход, если не можем создать пример файла
            
    company_names = load_company_names(input_file)

    results_summary = { # Обновляем ключи для соответствия оригинальным методам
        "wikidata": 0, 
        "domains": 0, 
        "wiki_parser": 0, 
        "llm": 0, 
        "google": 0, # Оригинальный метод, если LLM не выбрал, но были wiki-ссылки
        "not_found": 0
    }
    total_companies = 0
    found_details = [] 

    if company_names:
        total_companies = len(company_names)
        print(f"Загружено {total_companies} компаний из {input_file}")
        
        for i, company_name in enumerate(company_names):
            print(f"--- Обработка ({i+1}/{total_companies}): {company_name} ---")
            url, method = await finder.find_official_website(company_name)
            
            if url:
                print(f"Результат для '{company_name}': URL: {url}, Метод: {method}\n")
                found_details.append({"company": company_name, "url": url, "method": method})
            else:
                print(f"Результат для '{company_name}': Сайт не найден, Метод: {method}\n")
            
            results_summary[method] = results_summary.get(method, 0) + 1
        
        print("\n=== Статистика поиска ===")
        print(f"Всего компаний обработано: {total_companies}")
        if total_companies > 0:
            for method, count in results_summary.items():
                if count > 0: # Показываем только использованные методы
                    percentage = (count / total_companies * 100)
                    print(f"  {method}: {count} ({percentage:.1f}%)")
        
        output_csv_file = "found_websites_details.csv"
        try:
            output_df = pd.DataFrame(found_details)
            output_df.to_csv(output_csv_file, index=False, encoding='utf-8')
            print(f"\nДетали найденных сайтов сохранены в: {output_csv_file}")
        except Exception as e:
            print(f"\nНе удалось сохранить детали в CSV: {e}")
    else:
        print(f"Не удалось загрузить компании из '{input_file}'. Проверьте файл и его содержимое.")

if __name__ == "__main__":
    asyncio.run(main()) 