"""
Асинхронный клиент ScrapingBee для параллельной обработки
"""

import asyncio
import aiohttp
import json
import time
from typing import List, Dict, Any, Tuple
from pathlib import Path
import pandas as pd

from src.utils.config import SCRAPINGBEE_API_KEY, SCRAPE_TOP_N_RESULTS, SMART_FILTERING_CONFIG
from src.utils.logging import log_info, log_debug, log_error
from src.utils.signals_processor import extract_signals_keywords, prioritize_content, clean_scraped_content, extract_content_metadata
from src.external.scrapingbee_client import save_scrapingbee_result


class AsyncScrapingBeeClient:
    """
    Асинхронный клиент для ScrapingBee API с поддержкой пакетной обработки
    """
    
    def __init__(self, max_concurrent_requests=5, rate_limit_delay=0.2):
        self.max_concurrent = max_concurrent_requests
        self.rate_limit_delay = rate_limit_delay
        self.session = None
        self.api_url = "https://app.scrapingbee.com/api/v1/"
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def scrape_single_url_async(self, url: str, session_id: str, company_name: str, serper_query: str, criterion: pd.Series = None) -> str:
        """
        Асинхронно скрапит один URL
        """
        if not SCRAPINGBEE_API_KEY:
            log_error("ScrapingBee API key is not configured.")
            return None
        
        log_debug(f"🐝 Async scraping URL: {url}")
        
        try:
            # Rate limiting
            await asyncio.sleep(self.rate_limit_delay)
            
            extract_rules_json = json.dumps({"text": "body"})
            
            params = {
                "api_key": SCRAPINGBEE_API_KEY,
                "url": url,
                "extract_rules": extract_rules_json,
            }
            
            async with self.session.get(self.api_url, params=params, timeout=120) as response:
                response.raise_for_status()
                data = await response.json()
                
                # Save result using sync function (it's fast file I/O)
                save_scrapingbee_result(session_id, company_name, url, {
                    "status_code": response.status,
                    "headers": dict(response.headers),
                    "response_body": data
                }, serper_query)
                
                scraped_text = data.get('text')
                
                if data.get("error"):
                    log_error(f"❌ ScrapingBee API error for {url}: {data.get('message')}")
                    return None
                
                if not scraped_text:
                    log_debug(f"⚠️ Scraped content is empty for {url}")
                    return None
                
                log_debug(f"✅ Async scraping successful, content length: {len(scraped_text)} chars")
                
                # Apply smart filtering if enabled and criterion provided
                if SMART_FILTERING_CONFIG['enable_signals_prioritization'] and criterion is not None:
                    signals_keywords = extract_signals_keywords(criterion)
                    if signals_keywords:
                        # Clean content first
                        cleaned_content = clean_scraped_content(scraped_text)
                        
                        # Apply signals-based prioritization
                        priority_content, structured_content = prioritize_content(cleaned_content, signals_keywords)
                        
                        if priority_content:
                            log_info(f"🎯 Applied async signals filtering for {len(signals_keywords)} keywords")
                            return structured_content
                        else:
                            log_debug("No priority content found, returning cleaned content")
                            return cleaned_content
                    else:
                        log_debug("No signals keywords found, returning cleaned content")
                        return clean_scraped_content(scraped_text)
                else:
                    # Basic cleaning without signals processing
                    return clean_scraped_content(scraped_text)
                
        except Exception as e:
            log_error(f"❌ Async scraping failed for {url}: {e}")
            save_scrapingbee_result(session_id, company_name, url, {
                "status_code": "N/A",
                "error": f"AsyncRequestException: {str(e)}"
            }, serper_query)
            return None
    
    async def scrape_multiple_urls_async(self, search_results: List[Dict], criterion: pd.Series, session_id: str, company_name: str, serper_query: str) -> str:
        """
        Асинхронно скрапит несколько URL с signals-based приоритизацией
        """
        if not search_results:
            return ""
        
        # Extract signals keywords once
        signals_keywords = extract_signals_keywords(criterion)
        urls_to_scrape = search_results[:SCRAPE_TOP_N_RESULTS]
        
        log_info(f"🚀 Starting async scraping of {len(urls_to_scrape)} URLs with {len(signals_keywords)} signals keywords")
        
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def limited_scrape(result):
            url = result.get('link', '')
            if not url:
                return None, result
            async with semaphore:
                content = await self.scrape_single_url_async(url, session_id, company_name, serper_query, criterion)
                return content, result
        
        # Execute all scraping tasks concurrently
        start_time = time.time()
        tasks = [limited_scrape(result) for result in urls_to_scrape]
        scraping_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        all_scraped_content = []
        priority_aggregated = []
        metadata_list = []
        successful_scrapes = 0
        
        for i, result in enumerate(scraping_results):
            if isinstance(result, Exception):
                log_error(f"❌ Async scraping task {i} failed: {result}")
                continue
            
            scraped_content, search_result = result
            if not scraped_content:
                continue
            
            successful_scrapes += 1
            url = search_result.get('link', '')
            
            # Extract metadata
            metadata = extract_content_metadata(url, scraped_content)
            metadata_list.append(metadata)
            
            # Add to aggregated content
            url_header = f"\n=== Content from {url} ({metadata['word_count']} words) ===\n"
            all_scraped_content.append(url_header + scraped_content)
            
            # If this content has priority section, extract it
            if SMART_FILTERING_CONFIG['priority_section_header'] in scraped_content:
                priority_section = scraped_content.split(SMART_FILTERING_CONFIG['priority_section_header'])[1]
                if SMART_FILTERING_CONFIG['full_content_header'] in priority_section:
                    priority_section = priority_section.split(SMART_FILTERING_CONFIG['full_content_header'])[0]
                priority_aggregated.append(f"Priority from {url}:\n{priority_section.strip()}")
        
        elapsed = time.time() - start_time
        log_info(f"🎉 Async scraping completed: {successful_scrapes}/{len(urls_to_scrape)} successful in {elapsed:.2f}s")
        
        if not all_scraped_content:
            log_debug("No content scraped from any URLs")
            return ""
        
        # Aggregate all content
        full_aggregated = "\n\n".join(all_scraped_content)
        
        # Create final structured output
        if priority_aggregated and signals_keywords:
            priority_section = "\n\n".join(priority_aggregated)
            final_content = f"""
{SMART_FILTERING_CONFIG['priority_section_header']}
{priority_section}

{SMART_FILTERING_CONFIG['full_content_header']}
{full_aggregated}

=== Async Scraping Summary ===
Total URLs scraped: {len(metadata_list)}
Total content length: {sum(m['char_count'] for m in metadata_list)} characters
Scraping time: {elapsed:.2f}s
Signals keywords used: {', '.join(signals_keywords[:5])}{'...' if len(signals_keywords) > 5 else ''}
"""
        else:
            final_content = f"""
{SMART_FILTERING_CONFIG['full_content_header']}
{full_aggregated}

=== Async Scraping Summary ===
Total URLs scraped: {len(metadata_list)}
Total content length: {sum(m['char_count'] for m in metadata_list)} characters
Scraping time: {elapsed:.2f}s
"""
        
        log_info(f"✅ Async aggregated content from {len(metadata_list)} URLs, total length: {len(final_content)} chars")
        return final_content


async def async_scrape_multiple_urls_with_signals(search_results: List[Dict], criterion: pd.Series, session_id: str, company_name: str, serper_query: str, max_concurrent=5) -> str:
    """
    Публичная асинхронная функция для скрапинга нескольких URL
    """
    async with AsyncScrapingBeeClient(max_concurrent_requests=max_concurrent) as client:
        return await client.scrape_multiple_urls_async(search_results, criterion, session_id, company_name, serper_query)


def run_async_scrape_sync(search_results: List[Dict], criterion: pd.Series, session_id: str, company_name: str, serper_query: str, max_concurrent=5) -> str:
    """
    Синхронная обертка для асинхронного скрапинга
    """
    async def _run_async_scrape():
        return await async_scrape_multiple_urls_with_signals(
            search_results, criterion, session_id, company_name, serper_query, max_concurrent
        )
    
    # Run async function in new event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an event loop, use thread executor
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _run_async_scrape())
                return future.result()
        else:
            return loop.run_until_complete(_run_async_scrape())
    except RuntimeError:
        # No event loop, create a new one
        return asyncio.run(_run_async_scrape()) 