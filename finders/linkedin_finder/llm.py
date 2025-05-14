import aiohttp
from openai import AsyncOpenAI
import logging

# Получаем экземпляр логгера
logger = logging.getLogger(__name__)

async def choose_best_linkedin_url(company_name: str, candidates: list, openai_api_key: str) -> str | None:
    """
    Выбирает наиболее подходящую страницу LinkedIn для компании через LLM.
    
    Args:
        company_name: Название компании
        candidates: Список кандидатов с их сниппетами из поиска
        openai_api_key: API ключ для OpenAI
        
    Returns:
        str | None: Выбранный LinkedIn URL или None
    """
    try:
        # Формируем список кандидатов с их сниппетами для анализа
        candidates_text = []
        for idx, candidate in enumerate(candidates, 1):
            url = candidate.get('link', '')
            title = candidate.get('title', '')
            snippet = candidate.get('snippet', '')
            
            candidates_text.append(f"{idx}. URL: {url}")
            candidates_text.append(f"   Title: {title}")
            candidates_text.append(f"   Snippet: {snippet}")
            candidates_text.append("")

        system_prompt = f"""You are an expert assistant that identifies the official LinkedIn company profile for a given company.
Company Name: {company_name}

Your task is to analyze the provided list of LinkedIn URLs, titles, and snippets.
Select EXACTLY ONE URL that is most likely to be the OFFICIAL LinkedIn Company Page for this company.
Consider:
1. The URL should typically follow pattern linkedin.com/company/[company-name]
2. The company name in the title (e.g., "Company Name - LinkedIn")
3. Official information in the snippet (headquarters, employees, founded date, etc.)
4. Avoid selecting LinkedIn job pages, careers pages, or personal profiles
5. Prefer the primary/main company page, not subsidiary or regional variants if multiple exist

Verify that this is truly the company requested, not a similarly named one.
Output ONLY the selected LinkedIn URL. No explanations, no other text."""

        user_prompt = f"""Here are the candidate LinkedIn pages for {company_name}:

{chr(10).join(candidates_text)}

Which single URL is most likely the official LinkedIn company page for {company_name}?
Answer:"""

        openai_client = AsyncOpenAI(api_key=openai_api_key)
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
        
        # Проверка, что это действительно LinkedIn URL
        if "linkedin.com/company/" in selected_url:
            # Простая очистка от конечного слеша для единообразия перед возвратом
            if selected_url.endswith('/'):
                selected_url = selected_url.rstrip('/')
            # Можно добавить более сложную нормализацию здесь или в основном файле LinkedInFinder
            return selected_url
        else:
            # Если модель вернула что-то другое, попробуем интерпретировать как номер кандидата
            try:
                if selected_url.isdigit() and 1 <= int(selected_url) <= len(candidates):
                    url = candidates[int(selected_url)-1].get('link', '')
                    
                    # Простая очистка от конечного слеша
                    if url.endswith('/'):
                        url = url.rstrip('/')
                    return url
            except:
                pass # Ошибка приведения к числу или индекс вне диапазона
            
            # Если не смогли получить валидный URL или LLM вернула нерелевантный текст
            logger.warning(f"LLM_LinkedIn_URL_Selector: LLM returned non-company URL or unparseable selection: {selected_url}")
            return None

    except Exception as e:
        print(f"Ошибка при анализе LinkedIn URL через LLM: {e}")
        return None 