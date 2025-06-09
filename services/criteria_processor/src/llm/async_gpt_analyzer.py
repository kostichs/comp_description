"""
Асинхронный GPT анализатор для параллельной обработки критериев
"""

import asyncio
import pandas as pd
import openai
from openai import AsyncOpenAI
import re
from typing import List, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from src.utils.logging import log_info, log_debug, log_error
from src.external.serper import perform_google_search, save_serper_result, format_search_query
from src.external.scrapingbee_client import scrape_multiple_urls_with_signals
from src.external.async_scrapingbee import run_async_scrape_sync
from src.utils.signals_processor import extract_signals_keywords
from src.utils.config import ASYNC_SCRAPING_CONFIG


class AsyncGPTAnalyzer:
    """
    Асинхронный класс для анализа данных с помощью GPT с пакетной обработкой критериев
    """
    
    def __init__(self, session_id: str = None, max_concurrent_gpt_requests: int = 10):
        self.client = AsyncOpenAI()
        self.session_id = session_id
        self.max_concurrent = max_concurrent_gpt_requests
        self.website = None
    
    async def analyze_criteria_async(self, context: str, criteria_df: pd.DataFrame, website: str = None) -> dict:
        """
        Асинхронно анализирует критерии с пакетной обработкой GPT запросов
        """
        self.website = website
        results = {}
        
        # Группируем критерии по продуктам
        for product, product_group in criteria_df.groupby('Product'):
            results[product] = await self._evaluate_product_async(product, product_group, context)
        
        return self._format_results(results)
    
    async def _evaluate_product_async(self, product_name: str, product_df: pd.DataFrame, context: str) -> list:
        """Асинхронно оценивает соответствие по всем целевым аудиториям одного продукта."""
        log_info(f"🔄 Async evaluating product: {product_name}")
        
        # Создаем задачи для всех аудиторий параллельно
        audience_tasks = []
        for audience, audience_group in product_df.groupby('Target Audience'):
            task = self._evaluate_audience_async(audience, audience_group, context, product_name)
            audience_tasks.append(task)
        
        # Выполняем все аудитории параллельно
        audience_results = await asyncio.gather(*audience_tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        processed_results = []
        for i, result in enumerate(audience_results):
            if isinstance(result, Exception):
                log_error(f"❌ Audience evaluation failed: {result}")
                processed_results.append({"Target Audience": f"Error_{i}", "Qualified": False, "Reason": str(result), "Score": 0})
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def _evaluate_audience_async(self, audience_name: str, audience_df: pd.DataFrame, context: str, product_name: str) -> dict:
        """Асинхронно оценивает соответствие по всем критериям для одной целевой аудитории."""
        company_name_match = re.search(r"Company: (.*?)\\n", context)
        company_name = company_name_match.group(1) if company_name_match else "Unknown Company"
        
        log_info(f"🎯 Async checking {product_name} -> {audience_name}")

        # Шаг 1: Проверка обязательных критериев (последовательно, т.к. при первом провале останавливаемся)
        mandatory_criteria = audience_df[audience_df['Criteria Type'] == 'Mandatory']
        for _, criterion in mandatory_criteria.iterrows():
            passed, _, _ = await self._process_dynamic_criterion_async(company_name, criterion, context)
            if not passed:
                log_info(f"❌ Mandatory failed for {product_name} -> {audience_name}")
                return {"Target Audience": audience_name, "Qualified": False, "Reason": "Mandatory criteria failed", "Score": 0}

        log_info(f"✅ Mandatory passed for {product_name} -> {audience_name}")

        # Шаг 2: Оценка квалификационных критериев (параллельно)
        qualification_criteria = audience_df[audience_df['Criteria Type'] == 'Qualification']
        if qualification_criteria.empty:
            return {"Target Audience": audience_name, "Qualified": True, "Reason": "No qualification criteria", "Score": 1}

        # Создаем задачи для всех квалификационных критериев
        qualification_tasks = []
        for _, criterion in qualification_criteria.iterrows():
            task = self._process_dynamic_criterion_async(company_name, criterion, context)
            qualification_tasks.append(task)
        
        # Выполняем все квалификационные критерии параллельно
        qualification_results = await asyncio.gather(*qualification_tasks, return_exceptions=True)
        
        # Подсчитываем результаты
        total_score = 0
        max_score = len(qualification_criteria)
        
        for i, result in enumerate(qualification_results):
            if isinstance(result, Exception):
                log_error(f"❌ Qualification criterion {i} failed: {result}")
                continue
            
            passed, reason, _ = result
            if passed:
                total_score += 1
        
        final_score = total_score / max_score if max_score > 0 else 0
        qualified = final_score > 0.5

        reason = f"{total_score}/{max_score} qualification criteria passed."
        log_info(f"{'✅ Qualified' if qualified else '❌ Not qualified'}: {product_name} -> {audience_name} (Score: {final_score:.3f})")

        return {"Target Audience": audience_name, "Qualified": qualified, "Reason": reason, "Score": final_score}
    
    async def _process_dynamic_criterion_async(self, company_name: str, criterion: pd.Series, context: str) -> Tuple[bool, str, str]:
        """Асинхронно обрабатывает один критерий, выполняя поиск и анализ если необходимо."""
        criterion_text = criterion['Criteria']
        full_context = context

        if pd.notna(criterion.get('Search Query')):
            search_query_template = str(criterion['Search Query'])
            
            # Handle both {website} and {company_name} placeholders
            search_query = search_query_template
            
            # First replace {website} if present and available
            if '{website}' in search_query:
                if self.website:
                    search_query = format_search_query(search_query, self.website)
                else:
                    log_debug(f"⚠️ Warning: Search query contains {{website}} but no website provided")
                    return False, "No website provided for site: search", ""
            
            # Then replace {company_name} if present
            if '{company_name}' in search_query:
                search_query = search_query.replace('{company_name}', company_name)
            
            log_debug(f"🔍 Async dynamic search: {search_query}")
            
            # Выполняем поиск в отдельном потоке (SERPER API синхронный)
            loop = asyncio.get_event_loop()
            search_response = await loop.run_in_executor(
                None, perform_google_search, search_query, self.session_id, company_name
            )
            search_results = search_response.get('organic', []) if search_response else []
            
            if search_results:
                search_context = "\\n".join([f"Title: {r.get('title', '')}\\nSnippet: {r.get('snippet', '')}" for r in search_results])
                full_context += "\\n--- Dynamic Search Results ---\\n" + search_context

                if str(criterion.get('Deep Analysis')).lower() == 'true':
                    # Use async scraping
                    if ASYNC_SCRAPING_CONFIG['enable_async_scraping']:
                        log_info(f"🐝 Starting async deep analysis with signals for '{search_query}'...")
                        try:
                            scraped_text = await loop.run_in_executor(
                                None, run_async_scrape_sync,
                                search_results, criterion, self.session_id, company_name, search_query,
                                ASYNC_SCRAPING_CONFIG['max_concurrent_scrapes']
                            )
                            if scraped_text:
                                full_context += "\\n--- Deep Analysis Content (Async) ---\\n" + scraped_text
                        except Exception as e:
                            log_error(f"❌ Async scraping failed: {e}")
                            if ASYNC_SCRAPING_CONFIG['fallback_to_sync']:
                                log_info("🔄 Falling back to sync scraping...")
                                scraped_text = await loop.run_in_executor(
                                    None, scrape_multiple_urls_with_signals,
                                    search_results, criterion, self.session_id, company_name, search_query
                                )
                                if scraped_text:
                                    full_context += "\\n--- Deep Analysis Content (Sync Fallback) ---\\n" + scraped_text
                    else:
                        log_info(f"🐝 Starting sync deep analysis with signals for '{search_query}'...")
                        scraped_text = await loop.run_in_executor(
                            None, scrape_multiple_urls_with_signals,
                            search_results, criterion, self.session_id, company_name, search_query
                        )
                        if scraped_text:
                            full_context += "\\n--- Deep Analysis Content ---\\n" + scraped_text
        
        # Enhance prompt with signals context
        signals_keywords = extract_signals_keywords(criterion)
        signals_context = ""
        if signals_keywords:
            signals_context = f"\\nKey signals to look for: {', '.join(signals_keywords)}"
        
        prompt = f"""
        Context:
        {full_context}
        ---
        Criterion: {criterion_text}{signals_context}
        ---
        Based on the context, does the company meet the criterion? 
        {f"Pay special attention to mentions of: {', '.join(signals_keywords)}" if signals_keywords else ""}
        Respond with "Yes" or "No" and a brief, one-sentence explanation.
        Example: Yes, the company provides cloud services which aligns with the criterion.
        """
        
        response_text = await self._get_gpt_response_async(prompt)
        parsed_response = GPTResponse(response_text)
        return parsed_response.is_yes(), parsed_response.get_reason(), response_text
    
    async def _get_gpt_response_async(self, prompt: str) -> str:
        """Асинхронно отправляет запрос в GPT и возвращает текстовый ответ."""
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=100
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            log_error(f"❌ Async OpenAI API error: {e}")
            return f"Error: {e}"
    
    def _format_results(self, results: dict) -> dict:
        """Форматирует финальный результат для вывода."""
        output = {}
        for product, audiences in results.items():
            qualified_audiences = [a for a in audiences if a['Qualified']]
            if qualified_audiences:
                output[f"Qualified_{product}"] = "Yes"
                output[f"Qualified_Audiences_{product}"] = ", ".join([a['Target Audience'] for a in qualified_audiences])
            else:
                output[f"Qualified_{product}"] = "No"
        return output


class GPTResponse:
    """Класс для парсинга и хранения ответа от GPT."""
    def __init__(self, response_text: str):
        self.text = response_text.lower()
        self.original_text = response_text

    def is_yes(self) -> bool:
        """Проверяет, является ли ответ положительным."""
        return self.text.startswith('yes')

    def get_reason(self) -> str:
        """Извлекает причину из ответа."""
        match = re.search(r'yes,?(.*)', self.text, re.IGNORECASE)
        if not match:
            match = re.search(r'no,?(.*)', self.text, re.IGNORECASE)
        
        if match and match.group(1):
            return match.group(1).strip()
        
        # Если не удалось распарсить, возвращаем исходный текст
        return self.original_text


def run_async_gpt_analysis_sync(context: str, criteria_df: pd.DataFrame, session_id: str = None, website: str = None, max_concurrent: int = 10) -> dict:
    """
    Синхронная обертка для асинхронного GPT анализа
    """
    async def _run_async_analysis():
        analyzer = AsyncGPTAnalyzer(session_id=session_id, max_concurrent_gpt_requests=max_concurrent)
        return await analyzer.analyze_criteria_async(context, criteria_df, website)
    
    # Run async function in new event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an event loop, use thread executor
            with ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _run_async_analysis())
                return future.result()
        else:
            return loop.run_until_complete(_run_async_analysis())
    except RuntimeError:
        # No event loop, create a new one
        return asyncio.run(_run_async_analysis()) 