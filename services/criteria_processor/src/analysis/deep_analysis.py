from typing import List, Dict
from src.external.scrapingbee_client import scrape_website_text
from src.utils.logging import log_info, log_debug

def process_company_deep_analysis(company_name: str, search_results: List[Dict], session_id: str, serper_query: str) -> str:
    """
    Performs deep analysis by scraping text from search result URLs.
    
    Args:
        company_name (str): The name of the company.
        search_results (List[Dict]): A list of search results from Serper.
        session_id (str): The session ID for logging.
        serper_query (str): The original Serper query for context.

    Returns:
        str: A consolidated string of all scraped text.
    """
    if not search_results:
        return ""

    all_scraped_text = []
    log_info(f"Scraping {len(search_results)} URLs for deep analysis of {company_name}...")

    for result in search_results:
        link = result.get('link')
        if not link:
            continue
        
        # Pass the serper_query to the scraping function
        scraped_text = scrape_website_text(link, session_id, company_name, serper_query)
        if scraped_text:
            all_scraped_text.append(scraped_text)

    log_debug(f"Deep analysis for {company_name} finished. Total scraped text length: {sum(len(t) for t in all_scraped_text)}")
    return "\\n\\n".join(all_scraped_text) 