"""
Пакетная обработка SERPER запросов для ускорения критерий анализа
"""

import asyncio
import aiohttp
import time
import json
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from src.utils.config import SERPER_API_KEY, SERPER_API_URL, SERPER_MAX_RETRIES, SERPER_RETRY_DELAY
from src.utils.logging import log_info, log_debug, log_error
from src.external.serper import save_serper_result


class BatchSerperClient:
    """
    Клиент для пакетной обработки SERPER запросов
    """
    
    def __init__(self, max_concurrent_requests=10, rate_limit_delay=0.1):
        self.max_concurrent = max_concurrent_requests
        self.rate_limit_delay = rate_limit_delay
        self.session = None
        self._lock = threading.Lock()
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def single_search_async(self, query: str, session_id: str = None, company_name: str = None) -> Dict[str, Any]:
        """
        Выполняет один поисковый запрос асинхронно
        """
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json"
        }
        
        payload = {
            "q": query,
            "gl": "us",
            "hl": "en", 
            "num": 10
        }
        
        for attempt in range(SERPER_MAX_RETRIES):
            try:
                # Rate limiting
                await asyncio.sleep(self.rate_limit_delay)
                
                log_debug(f"🔎 Batch search: {query}")
                
                async with self.session.post(SERPER_API_URL, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    result = await response.json()
                    
                    # Save result if session provided
                    if session_id and company_name:
                        save_serper_result(session_id, company_name, query, result)
                    
                    log_debug(f"✅ Batch search success: {query}")
                    return result
                    
            except Exception as e:
                log_error(f"⚠️ Batch search attempt {attempt + 1}/{SERPER_MAX_RETRIES} failed for '{query}': {e}")
                if attempt < SERPER_MAX_RETRIES - 1:
                    await asyncio.sleep(SERPER_RETRY_DELAY)
                else:
                    log_error(f"❌ All batch search attempts failed for: {query}")
                    return {}
        
        return {}
    
    async def batch_search_async(self, search_requests: List[Tuple[str, str, str]]) -> List[Dict[str, Any]]:
        """
        Выполняет пакет поисковых запросов асинхронно
        
        Args:
            search_requests: List of (query, session_id, company_name) tuples
            
        Returns:
            List of search results in the same order
        """
        if not search_requests:
            return []
        
        log_info(f"🚀 Starting batch search for {len(search_requests)} queries")
        
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def limited_search(request):
            query, session_id, company_name = request
            async with semaphore:
                return await self.single_search_async(query, session_id, company_name)
        
        # Execute all searches concurrently
        start_time = time.time()
        tasks = [limited_search(req) for req in search_requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log_error(f"❌ Batch search failed for query {i}: {result}")
                processed_results.append({})
            else:
                processed_results.append(result)
        
        elapsed = time.time() - start_time
        success_count = sum(1 for r in processed_results if r)
        
        log_info(f"🎉 Batch search completed: {success_count}/{len(search_requests)} successful in {elapsed:.2f}s")
        
        return processed_results


def run_batch_search_sync(search_requests: List[Tuple[str, str, str]], max_concurrent=10) -> List[Dict[str, Any]]:
    """
    Синхронная обертка для пакетного поиска
    
    Args:
        search_requests: List of (query, session_id, company_name) tuples
        max_concurrent: Maximum concurrent requests
        
    Returns:
        List of search results
    """
    async def _run_batch():
        async with BatchSerperClient(max_concurrent_requests=max_concurrent) as client:
            return await client.batch_search_async(search_requests)
    
    # Run async function in new event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an event loop, use thread executor
            with ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _run_batch())
                return future.result()
        else:
            return loop.run_until_complete(_run_batch())
    except RuntimeError:
        # No event loop, create a new one
        return asyncio.run(_run_batch())


def batch_search_for_criteria(company_info: Dict[str, Any], criteria_df, session_id: str = None, max_concurrent=8) -> Dict[str, Dict[str, Any]]:
    """
    Выполняет пакетный поиск для всех критериев компании
    
    Args:
        company_info: Dictionary with company information
        criteria_df: DataFrame with criteria that need search
        session_id: Session ID for logging
        max_concurrent: Maximum concurrent SERPER requests
        
    Returns:
        Dictionary mapping criterion ID to search results
    """
    company_name = company_info.get("Company_Name", "Unknown")
    log_info(f"🔍 Preparing batch search for {company_name}")
    
    # Collect all search queries that need to be made
    search_requests = []
    criterion_map = {}  # Maps request index to criterion info
    
    for idx, row in criteria_df.iterrows():
        search_query_template = row.get('Search Query')
        if not search_query_template or str(search_query_template).strip() == '' or str(search_query_template).lower() in ['nan', 'none']:
            continue
        
        search_query = str(search_query_template)
        
        # Handle {website} placeholder
        if '{website}' in search_query:
            website = company_info.get("Official_Website", "")
            if website:
                from src.external.serper import format_search_query
                search_query = format_search_query(search_query, website)
            else:
                log_debug(f"⚠️ Skipping criterion with {{website}} placeholder - no website available")
                continue
        
        # Handle {company_name} placeholder
        if '{company_name}' in search_query:
            search_query = search_query.replace('{company_name}', company_name)
        
        # Add to batch
        request_idx = len(search_requests)
        search_requests.append((search_query, session_id, company_name))
        criterion_map[request_idx] = {
            'criterion_idx': idx,
            'criterion': row,
            'query': search_query
        }
    
    if not search_requests:
        log_debug(f"📭 No search queries found for {company_name}")
        return {}
    
    log_info(f"🚀 Executing {len(search_requests)} batch searches for {company_name}")
    
    # Execute batch search
    search_results = run_batch_search_sync(search_requests, max_concurrent)
    
    # Map results back to criteria
    criteria_results = {}
    for request_idx, search_result in enumerate(search_results):
        if request_idx in criterion_map:
            criterion_info = criterion_map[request_idx]
            criterion_idx = criterion_info['criterion_idx']
            
            # Extract organic results
            organic_results = search_result.get('organic', []) if search_result else []
            
            criteria_results[criterion_idx] = {
                'criterion': criterion_info['criterion'],
                'query': criterion_info['query'],
                'search_results': organic_results,
                'full_response': search_result
            }
    
    log_info(f"✅ Batch search completed for {company_name}: {len(criteria_results)} results")
    return criteria_results


def batch_search_for_companies(companies_data: List[Dict[str, Any]], criteria_df, session_id: str = None, max_concurrent=5) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Выполняет пакетный поиск для нескольких компаний одновременно
    
    Args:
        companies_data: List of company dictionaries
        criteria_df: DataFrame with criteria
        session_id: Session ID for logging
        max_concurrent: Maximum concurrent company processing
        
    Returns:
        Dictionary mapping company names to their criteria search results
    """
    log_info(f"🎯 Starting batch search for {len(companies_data)} companies")
    
    def process_company(company_info):
        company_name = company_info.get("Company_Name", "Unknown")
        try:
            results = batch_search_for_criteria(company_info, criteria_df, session_id)
            return company_name, results
        except Exception as e:
            log_error(f"❌ Batch search failed for {company_name}: {e}")
            return company_name, {}
    
    # Process companies in parallel
    all_results = {}
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_company = {
            executor.submit(process_company, company): company.get("Company_Name", f"Company_{i}")
            for i, company in enumerate(companies_data)
        }
        
        for future in as_completed(future_to_company):
            company_name = future_to_company[future]
            try:
                result_company_name, company_results = future.result()
                all_results[result_company_name] = company_results
                log_info(f"✅ Batch search completed for {result_company_name}")
            except Exception as e:
                log_error(f"❌ Batch search failed for {company_name}: {e}")
                all_results[company_name] = {}
    
    log_info(f"🎉 All batch searches completed for {len(all_results)} companies")
    return all_results 