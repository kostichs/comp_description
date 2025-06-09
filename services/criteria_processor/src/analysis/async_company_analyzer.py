"""
Асинхронный анализатор компаний с поддержкой async GPT
"""

import json
import asyncio
from typing import Dict, List
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

from src.external.serper import perform_google_search, save_serper_result
from src.llm.gpt_analyzer import GPTAnalyzer
from src.llm.async_gpt_analyzer import run_async_gpt_analysis_sync
from src.utils.logging import log_info, log_error, log_debug
from src.analysis.deep_analysis import process_company_deep_analysis
from src.utils.config import ASYNC_GPT_CONFIG


class AsyncCompanyAnalyzer:
    """
    Асинхронный класс для полного анализа одной компании с поддержкой async GPT
    """
    
    def __init__(self, criteria_df: pd.DataFrame, gpt_analyzer: GPTAnalyzer = None):
        self.criteria_df = criteria_df
        self.gpt_analyzer = gpt_analyzer  # Fallback sync analyzer
    
    async def analyze_async(self, company_name: str, company_description: str, session_id: str, use_deep_analysis: bool = False, website: str = None) -> Dict:
        """
        Асинхронно анализирует одну компанию: строит запрос, ищет в Serper, анализирует с помощью async GPT.
        """
        log_info(f"🔄 Async analyzing company: {company_name}")
        
        query = f"{company_name} {company_description}"
        log_debug(f"🔎 Async Serper query: {query}")
        
        try:
            # Выполняем Serper поиск в отдельном потоке (синхронный API)
            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(
                None, perform_google_search, query, session_id, company_name
            )
            
            if session_id:
                await loop.run_in_executor(
                    None, save_serper_result, session_id, company_name, query, search_results
                )
            
            scraped_text_all = ""
            if use_deep_analysis and search_results:
                log_info(f"🐝 Performing async deep analysis for {company_name}...")
                scraped_text_all = await loop.run_in_executor(
                    None, process_company_deep_analysis,
                    company_name, search_results, session_id, query
                )
        
            analysis_context = self.build_analysis_context(
                company_name=company_name,
                company_description=company_description,
                search_results=search_results,
                scraped_text=scraped_text_all
            )
            
            # Use async GPT analysis if enabled
            if ASYNC_GPT_CONFIG['enable_async_gpt']:
                log_info(f"🤖 Starting async GPT analysis for {company_name}...")
                try:
                    analysis_result = await loop.run_in_executor(
                        None, run_async_gpt_analysis_sync,
                        analysis_context, self.criteria_df, session_id, website,
                        ASYNC_GPT_CONFIG['max_concurrent_gpt_requests']
                    )
                except Exception as e:
                    log_error(f"❌ Async GPT analysis failed: {e}")
                    if ASYNC_GPT_CONFIG['fallback_to_sync'] and self.gpt_analyzer:
                        log_info("🔄 Falling back to sync GPT analysis...")
                        analysis_result = self.gpt_analyzer.analyze_criteria(analysis_context, self.criteria_df, website=website)
                    else:
                        raise e
            else:
                # Use sync GPT analyzer
                if self.gpt_analyzer:
                    log_info(f"🤖 Starting sync GPT analysis for {company_name}...")
                    analysis_result = self.gpt_analyzer.analyze_criteria(analysis_context, self.criteria_df, website=website)
                else:
                    raise ValueError("No GPT analyzer available (neither async nor sync)")
            
            final_result = {
                "Company": company_name,
                "Description": company_description,
                **analysis_result,
                "Serper_Query": query,
                "All_Results": json.dumps(search_results, ensure_ascii=False) if search_results else None,
                "Deep_Analysis_Summary": scraped_text_all[:500] + "..." if scraped_text_all else "Not performed"
            }
            
            log_info(f"✅ Async analysis completed for {company_name}")
            return final_result

        except Exception as e:
            log_error(f"❌ Async analysis error for {company_name}: {e}")
            return {
                "Company": company_name,
                "Description": company_description,
                "error": str(e)
            }

    def build_analysis_context(self, company_name: str, company_description: str, search_results: List[Dict], scraped_text: str) -> str:
        """
        Собирает весь текст для анализа в единый контекст.
        """
        context_parts = []
        context_parts.append(f"Company: {company_name}")
        if company_description:
            context_parts.append(f"Description: {company_description}")
        
        if search_results:
            context_parts.append("\\n--- Search Results ---")
            for item in search_results:
                context_parts.append(f"Title: {item.get('title', 'N/A')}")
                context_parts.append(f"Link: {item.get('link', 'N/A')}")
                context_parts.append(f"Snippet: {item.get('snippet', 'N/A')}")
        
        if scraped_text:
            context_parts.append("\\n--- Scraped Website Content ---")
            context_parts.append(scraped_text)
            
        return "\\n".join(context_parts)


def run_async_company_analysis_sync(company_name: str, company_description: str, criteria_df: pd.DataFrame, session_id: str, use_deep_analysis: bool = False, website: str = None) -> Dict:
    """
    Синхронная обертка для асинхронного анализа компании
    """
    async def _run_async_analysis():
        analyzer = AsyncCompanyAnalyzer(criteria_df)
        return await analyzer.analyze_async(company_name, company_description, session_id, use_deep_analysis, website)
    
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