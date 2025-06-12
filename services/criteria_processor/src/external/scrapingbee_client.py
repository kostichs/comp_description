import requests
import json
import os
import re
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import pandas as pd
from src.utils.config import SCRAPINGBEE_API_KEY, OUTPUT_DIR, SCRAPE_TOP_N_RESULTS, SMART_FILTERING_CONFIG
from src.utils.logging import log_debug, log_error, log_info
from src.utils.signals_processor import (
    extract_signals_keywords, 
    prioritize_content, 
    clean_scraped_content,
    extract_content_metadata
)
from urllib.parse import urlparse
from src.data.search_data_saver import save_scrapingbee_data


def _sanitize_filename(name: str) -> str:
    """Sanitizes a string to be used as a valid filename."""
    # Remove invalid characters for Windows filenames
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def save_scrapingbee_result(session_id: str, company_name: str, url: str, result_data: dict, serper_query: str):
    """Saves the ScrapingBee result to a single human-readable session log file."""
    if not session_id:
        return

    try:
        log_dir = os.path.join(OUTPUT_DIR, session_id, "scrapingbee_logs")
        os.makedirs(log_dir, exist_ok=True)
        filepath = os.path.join(log_dir, "scrapingbee_session.log")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_code = result_data.get('status_code', 'N/A')
        error = result_data.get('error')
        
        log_entry = f"--- Request at {timestamp} ---\n"
        log_entry += f"Company: {company_name}\n"
        log_entry += f"Serper Query: {serper_query}\n"
        log_entry += f"URL: {url}\n"
        log_entry += f"Status Code: {status_code}\n"

        scraped_text = None
        if not error:
            response_body = result_data.get('response_body', {})
            if isinstance(response_body, dict):
                scraped_text = response_body.get('text')
                api_error_message = response_body.get('message')
                if api_error_message:
                    log_entry += f"API Error: {api_error_message}\n"
                elif scraped_text:
                    log_entry += f"Content Length: {len(scraped_text)} characters\n"
                else:
                    log_entry += "Content: Empty or not found.\n"
            else: # raw text
                log_entry += f"Raw Response Snippet: {str(response_body)[:200].strip()}...\n"
        
        if error:
            log_entry += f"Error: {error}\n"

        if scraped_text:
            log_entry += "-- Scraped Content (first 2000 chars) --\n"
            log_entry += scraped_text[:2000].strip()
            log_entry += "\n----------------------------------------\n\n"
        else:
            log_entry += "----------------------------------------\n\n"


        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(log_entry)
            
    except Exception as e:
        log_error(f"Failed to save ScrapingBee log for {company_name}: {e}")

def scrape_website_text(url: str, session_id: str, company_name: str, serper_query: str, criterion: pd.Series = None) -> str | None:
    """
    Scrapes the text content of a given URL using the ScrapingBee API with Signals-based smart filtering.
    
    Args:
        url (str): The URL to scrape.
        session_id (str): The current session ID for logging.
        company_name (str): The company name for logging.
        serper_query (str): The original Serper query for context.
        criterion (pd.Series, optional): The criteria row for signals extraction.

    Returns:
        str | None: The processed content (with signals prioritization if enabled), or None if scraping fails.
    """
    if not SCRAPINGBEE_API_KEY:
        log_error("ScrapingBee API key is not configured.")
        save_scrapingbee_result(session_id, company_name, url, {
            "error": "ScrapingBee API key not configured."
        }, serper_query)
        return None

    log_debug(f"🐝 Scraping URL: {url} for {company_name}")
    response = None
    try:
        # The 'extract_rules' parameter must be a JSON-encoded string.
        # Previously, passing a dict caused requests to serialize it incorrectly.
        extract_rules_json = json.dumps({"text": "body"})

        response = requests.get(
            url="https://app.scrapingbee.com/api/v1/",
            params={
                "api_key": SCRAPINGBEE_API_KEY,
                "url": url,
                "extract_rules": extract_rules_json,
            },
            timeout=120,
        )
        
        response.raise_for_status()
        
        data = response.json()
        
        save_scrapingbee_result(session_id, company_name, url, {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "response_body": data
        }, serper_query)

        scraped_text = data.get('text')
        
        # Также сохраняем в markdown через SearchDataSaver
        save_scrapingbee_data(company_name, url, scraped_text or "", serper_query, response.status_code)

        if data.get("error"):
            log_error(f"❌ ScrapingBee API error for {url}: {data.get('message')}")
            return None

        if not scraped_text:
            log_debug(f"⚠️ Scraped content is empty for {url}")
            return None

        log_debug(f"✅ Raw scraping successful, content length: {len(scraped_text)} chars")
        
        # Apply smart filtering if enabled and criterion provided
        if SMART_FILTERING_CONFIG['enable_signals_prioritization'] and criterion is not None:
            signals_keywords = extract_signals_keywords(criterion)
            if signals_keywords:
                # Clean content first
                cleaned_content = clean_scraped_content(scraped_text)
                
                # Apply signals-based prioritization
                priority_content, structured_content = prioritize_content(cleaned_content, signals_keywords)
                
                if priority_content:
                    log_info(f"🎯 Applied signals filtering for {len(signals_keywords)} keywords")
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

    except requests.exceptions.RequestException as e:
        log_error(f"❌ Failed to scrape {url}: {e}")
        error_msg = f"RequestException: {str(e)}"
        save_scrapingbee_result(session_id, company_name, url, {
            "status_code": e.response.status_code if e.response is not None else "N/A",
            "error": error_msg
        }, serper_query)
        # Также сохраняем ошибку в markdown
        save_scrapingbee_data(company_name, url, "", serper_query, 
                             e.response.status_code if e.response is not None else 0, error_msg)
        return None
    except json.JSONDecodeError:
        log_error(f"❌ Failed to decode JSON response from ScrapingBee for {url}. Response: {response.text if response else 'No response'}")
        error_msg = "JSONDecodeError"
        save_scrapingbee_result(session_id, company_name, url, {
            "status_code": response.status_code if response is not None else 'N/A',
            "error": error_msg,
            "response_body": response.text if response is not None else "N/A"
        }, serper_query)
        # Также сохраняем ошибку в markdown
        save_scrapingbee_data(company_name, url, "", serper_query, 
                             response.status_code if response is not None else 0, error_msg)
        return None 

def scrape_multiple_urls_with_signals(search_results: List[Dict], criterion: pd.Series, session_id: str, company_name: str, serper_query: str) -> str:
    """
    Scrape multiple URLs from search results and aggregate with signals-based prioritization.
    
    Args:
        search_results (List[Dict]): List of search results from Serper
        criterion (pd.Series): The criteria row for signals extraction
        session_id (str): Session ID for logging
        company_name (str): Company name for logging
        serper_query (str): Original search query
        
    Returns:
        str: Aggregated content with signals prioritization
    """
    if not search_results:
        return ""
    
    # Extract signals keywords once
    signals_keywords = extract_signals_keywords(criterion)
    log_info(f"🔍 Processing {len(search_results[:SCRAPE_TOP_N_RESULTS])} URLs with {len(signals_keywords)} signals keywords")
    
    all_scraped_content = []
    priority_aggregated = []
    metadata_list = []
    
    for i, result in enumerate(search_results[:SCRAPE_TOP_N_RESULTS]):
        url = result.get('link', '')
        if not url:
            continue
            
        log_debug(f"🐝 Scraping URL {i+1}/{SCRAPE_TOP_N_RESULTS}: {url}")
        
        # Scrape individual URL (this will apply signals processing)
        scraped_content = scrape_website_text(url, session_id, company_name, serper_query, criterion)
        
        if scraped_content:
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

=== Scraping Summary ===
Total URLs scraped: {len(metadata_list)}
Total content length: {sum(m['char_count'] for m in metadata_list)} characters
Signals keywords used: {', '.join(signals_keywords[:5])}{'...' if len(signals_keywords) > 5 else ''}
"""
    else:
        final_content = f"""
{SMART_FILTERING_CONFIG['full_content_header']}
{full_aggregated}

=== Scraping Summary ===
Total URLs scraped: {len(metadata_list)}
Total content length: {sum(m['char_count'] for m in metadata_list)} characters
"""
    
    log_info(f"✅ Aggregated content from {len(metadata_list)} URLs, total length: {len(final_content)} chars")
    return final_content 