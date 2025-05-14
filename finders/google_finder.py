from .base import Finder
import aiohttp
import json
import re
from urllib.parse import urlparse, unquote
from openai import AsyncOpenAI
import os

class GoogleFinder(Finder):
    def __init__(self, serper_api_key: str):
        """
        Инициализирует финдер с API ключом для Google Serper.
        
        Args:
            serper_api_key: API ключ для Google Serper
        """
        self.api_key = serper_api_key
        
    async def find(self, company_name: str, **context) -> dict:
        """
        Ищет информацию о компании через Google Serper API.
        
        Args:
            company_name: Название компании
            context: Словарь с контекстом, должен содержать 'session' с aiohttp.ClientSession
                     и может содержать 'openai_api_key'
            
        Returns:
            dict: Результат поиска {"source": "google", "result": url или None}
        """
        session = context.get('session')
        if not session:
            raise ValueError("GoogleFinder требует aiohttp.ClientSession в context['session']")
            
        openai_api_key = context.get('openai_api_key') or os.getenv("OPENAI_API_KEY")
        
        results = await self._search_google(company_name, session)
        if not results or "organic" not in results:
            return {"source": "google", "result": None}
            
        # Фильтруем результаты, оставляя только ссылки на Wikipedia
        wiki_links = self._filter_wikipedia_links(results["organic"], company_name)
        if not wiki_links:
            return {"source": "google", "result": None}
            
        # Выбираем лучшую ссылку на Wikipedia через LLM
        if openai_api_key:
            selected_url = await self._choose_best_wiki_link(company_name, wiki_links, openai_api_key)
            if selected_url:
                return {"source": "google", "result": selected_url, "wiki_url": selected_url}
        
        # Если LLM не выбрал или нет API ключа, берем первую ссылку
        return {"source": "google", "result": wiki_links[0]["link"], "wiki_url": wiki_links[0]["link"]}
        
    async def _search_google(self, company_name: str, session: aiohttp.ClientSession) -> dict | None:
        """
        Выполняет поиск через Google Serper API.
        
        Args:
            company_name: Название компании
            session: aiohttp.ClientSession для HTTP-запросов
            
        Returns:
            dict | None: Результаты поиска или None в случае ошибки
        """
        headers = {'X-API-KEY': self.api_key, 'Content-Type': 'application/json'}
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
            
    def _filter_wikipedia_links(self, results: list, company_name: str) -> list:
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
                result['relevance_score'] = self._calculate_relevance_score(company_name, url)
                wiki_links.append(result)
        
        # Сортируем по убыванию оценки релевантности
        return sorted(wiki_links, key=lambda x: x.get('relevance_score', 0), reverse=True)
        
    def _calculate_relevance_score(self, company_name: str, wiki_url: str) -> float:
        """
        Вычисляет оценку релевантности Wikipedia страницы для компании.
        
        Args:
            company_name: Название компании
            wiki_url: URL страницы Wikipedia
            
        Returns:
            float: Оценка релевантности (выше - лучше)
        """
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
        
    async def _choose_best_wiki_link(self, company_name: str, candidates: list, api_key: str) -> str | None:
        """
        Выбирает наиболее подходящую страницу Wikipedia через LLM.
        
        Args:
            company_name: Название компании
            candidates: Список кандидатов с их сниппетами и релевантностью
            api_key: API ключ для OpenAI
            
        Returns:
            str | None: Выбранный URL или None
        """
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

            openai_client = AsyncOpenAI(api_key=api_key)
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
            return selected_url

        except Exception as e:
            print(f"Ошибка при анализе через LLM: {e}")
            return None 