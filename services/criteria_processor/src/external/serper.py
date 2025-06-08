"""
Модуль для работы с Serper.dev API
"""

import os
import re
import time
import json
import requests
from src.utils.config import SERPER_API_KEY, SERPER_API_URL, SERPER_MAX_RETRIES, SERPER_RETRY_DELAY, DEBUG_SERPER, OUTPUT_DIR, USE_SCRAPINGBEE_DEEP_ANALYSIS, SCRAPE_TOP_N_RESULTS
from src.utils.logging import log_info, log_error, log_debug
from src.external.scrapingbee_client import scrape_website_text

def save_serper_result(session_id, company_name, query, data):
    """Saves Serper results to a file in the session directory."""
    if not session_id:
        log_debug("No session_id provided, skipping save.")
        return

    try:
        # Sanitize inputs for filename
        sanitized_company_name = re.sub(r'[^a-zA-Z0-9_-]', '', company_name)
        sanitized_query = re.sub(r'[^a-zA-Z0-9_-]', '', query)[:50] # Truncate query part
        timestamp = int(time.time())

        # Define session-specific directory
        session_dir = os.path.join(OUTPUT_DIR, session_id, "serper_results")
        os.makedirs(session_dir, exist_ok=True)

        # Create filename
        filename = f"serper_{sanitized_company_name}_{sanitized_query}_{timestamp}.json"
        filepath = os.path.join(session_dir, filename)

        # Save data
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        log_debug(f"💾 Serper result saved to {filepath}")

    except Exception as e:
        log_error(f"Failed to save Serper result for session {session_id}: {e}")

def perform_google_search(query, session_id=None, company_name=None, retries=None):
    """
    Perform a Google search using the serper.dev API
    
    Args:
        query (str): The search query to send to serper.dev
        session_id (str, optional): The session ID for saving results.
        company_name (str, optional): The company name for saving results.
        retries (int, optional): Number of retries if API call fails. Defaults to config value.
    
    Returns:
        dict: Search results in JSON format or None if failed
    """
    retries = retries or SERPER_MAX_RETRIES
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "q": query,
        "gl": "us",  # Set geography to US by default
        "hl": "en",  # Set language to English
        "num": 10    # Number of results to return
    }
    
    start_time = time.time()
    for attempt in range(retries):
        try:
            log_debug(f"🔎 Searching: {query}")
            response = requests.post(SERPER_API_URL, headers=headers, json=payload)
            response_time = time.time() - start_time
            
            # Raise an exception for 4XX/5XX responses
            response.raise_for_status()
            
            response_json = response.json()
            log_debug(f"✅ Search successful! Response time: {response_time:.2f} seconds")
            
            if session_id and company_name:
                save_serper_result(session_id, company_name, query, response_json)
            
            # Debug output if enabled
            if DEBUG_SERPER:
                log_debug(f"\n===== SERPER.DEV RESPONSE =====")
                log_debug(f"💡 Search Query: {query}")
                log_debug(f"📊 Response status: {response.status_code}")
                log_debug(f"📄 Response size: {len(response.content)} bytes")
                
                if "organic" in response_json:
                    log_debug(f"📊 Found {len(response_json['organic'])} organic results")
                    for i, result in enumerate(response_json["organic"][:3]):  # Show first 3 results
                        log_debug(f"  {i+1}. {result.get('title', 'No title')}")
                        log_debug(f"     URL: {result.get('link', 'No link')}")
                        snippet = result.get('snippet', 'No snippet')
                        log_debug(f"     Snippet: {snippet[:100]}..." if len(snippet) > 100 else f"     Snippet: {snippet}")
                log_debug(f"=================================\n")
            
            return response_json
        except requests.exceptions.RequestException as e:
            log_error(f"⚠️ Serper API request failed (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                log_debug(f"Retrying in {SERPER_RETRY_DELAY} seconds...")
                time.sleep(SERPER_RETRY_DELAY)
            else:
                log_error("❌ All retries failed. Could not get search results.")
                return None

def extract_website_from_company(company_info):
    """
    Extract a website URL from company information, cleaning it if necessary
    
    Args:
        company_info (dict): Company information dictionary
    
    Returns:
        str: Clean website URL or empty string if not found
    """
    website = company_info.get("Official_Website", "")
    
    # Debug output
    log_debug(f"🔍 Extract website from: {website}")
    
    # Return empty string if website is not available or invalid
    if not website or website.lower() in ["not found", "none", "n/a"]:
        log_debug(f"⚠️ No valid website found in company info")
        return ""
    
    # Basic cleanup of website URL
    website = website.strip().lower()
    
    # If the website is just a domain without a protocol, add https://
    if website and not website.startswith(('http://', 'https://')):
        website = 'https://' + website
        log_debug(f"   Adding https:// prefix: {website}")
    
    # Extract domain for validation
    try:
        domain = website.replace("http://", "").replace("https://", "").split("/")[0]
        if not domain or "." not in domain:
            log_debug(f"⚠️ Invalid domain format: {domain}")
            return ""
        log_debug(f"   Extracted domain: {domain}")
    except Exception as e:
        log_debug(f"⚠️ Error extracting domain from {website}: {e}")
        return ""
    
    log_debug(f"🌐 Using website: {website}")
    return website

def format_search_query(query_template, website):
    """
    Format a search query template by substituting {website} with the actual website domain
    
    Args:
        query_template (str): The search query template from criteria file
        website (str): The website URL to substitute
    
    Returns:
        str: Formatted search query
    """
    if not website:
        log_debug("❌ Cannot format query: website URL is empty")
        return query_template
    
    # Extract domain from website for search
    domain = website.replace("http://", "").replace("https://", "").split("/")[0]
    log_debug(f"   Domain for search query: {domain}")
    
    # Check if template actually contains {website} placeholder
    if "{website}" not in query_template:
        log_debug(f"⚠️ Warning: Search query template does not contain {{website}} placeholder: {query_template}")
        # If no placeholder, just use the template as is
        return query_template
    
    # Replace {website} with domain in query template
    formatted_query = query_template.replace("{website}", domain)
    log_debug(f"📝 Formatted query: {formatted_query}")
    return formatted_query

def get_information_for_criterion(company_info, place, search_query=None, session_id=None, use_deep_analysis=False):
    """
    Get information for evaluating a criterion based on its "Place" value
    
    Args:
        company_info (dict): Company information dictionary
        place (str): The "Place" column value (e.g., "gen_descr", "website")
        search_query (str, optional): The search query template to use if place is "website"
        session_id (str, optional): The session ID for saving results.
        use_deep_analysis (bool, optional): Whether to use deep analysis
    
    Returns:
        tuple: (information_text, source_description)
            - information_text is the text to use for criterion evaluation
            - source_description describes where the information came from
    """
    description = company_info.get("Description", "")
    company_name = company_info.get("Company_Name", "Unknown Company")
    
    # Convert place to string and lowercase for consistent comparison
    place_str = str(place).lower() if place is not None else ""
    
    # If place is empty or gen_descr, use the general description
    if not place_str or place_str == "gen_descr":
        log_debug(f"🔍 Using general description for criterion evaluation")
        return description, "General Description"
    
    # If place is website and we have a search query, do a web search
    elif place_str == "website" and search_query:
        log_debug(f"🔍 Using website search for criterion evaluation")
        
        # Extract website from company info
        website = extract_website_from_company(company_info)
        
        if not website:
            log_debug(f"ℹ️ No valid website found for {company_name}, using general description instead")
            return description, "General Description (website not available)"
        
        # Format the search query
        formatted_query = format_search_query(search_query, website)
        
        # Perform the search
        search_results = perform_google_search(formatted_query, session_id=session_id, company_name=company_name)
        
        if not search_results:
            log_debug(f"ℹ️ Search failed for {company_name}, using general description instead")
            return description, "General Description (search failed)"

        # --- DEEP ANALYSIS LOGIC ---
        if use_deep_analysis:
            log_info(f"🐝 Starting deep analysis for '{formatted_query}'...")
            
            scraped_texts = []
            links_to_scrape = [result['link'] for result in search_results.get('organic', [])[:SCRAPE_TOP_N_RESULTS]]
            
            for link in links_to_scrape:
                scraped_content = scrape_website_text(link, session_id=session_id, company_name=company_name)
                if scraped_content:
                    scraped_texts.append(f"--- CONTENT FROM {link} ---\n\n{scraped_content}")

            if scraped_texts:
                scraped_info = "\n\n".join(scraped_texts)
                combined_information = (
                    f"SCRAPED CONTENT FOR: {formatted_query}\n\n"
                    f"{scraped_info}\n\n"
                    f"GENERAL DESCRIPTION:\n{description}"
                )
                log_info(f"✅ Deep analysis complete. Total scraped length: {len(scraped_info)} chars")
                return combined_information, f"Deep Analysis of top {len(scraped_texts)} search results"
            else:
                log_info(f"⚠️ Deep analysis did not return any content, using search snippets instead.")
        
        # --- SNIPPET ANALYSIS (FALLBACK) ---
        search_snippets = [result.get('snippet', '') for result in search_results.get('organic', [])]
        combined_snippets = "\n".join(search_snippets)
        
        # Если не было глубокого анализа или он не удался, возвращаем сниппеты
        source_description = "Google Search Snippets"
        log_debug(f"🔍 Using {source_description} for criterion evaluation")
        return combined_snippets, source_description
    
    # Fallback for any other case
    return description, "General Description (fallback)" 