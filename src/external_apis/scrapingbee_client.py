import asyncio
from scrapingbee import ScrapingBeeClient
from bs4 import BeautifulSoup
import tldextract
import logging

# Настройка логгера для этого модуля
logger = logging.getLogger(__name__)

def scrape_page_data(url: str, client: ScrapingBeeClient) -> tuple[str | None, str | None, str | None]:
    """Scrapes a page using ScrapingBee, trying simple fetch first, then fallback to JS rendering."""
    if not url or not client:
        logger.warning(f"[ScrapingBee] Invalid arguments: URL='{url}', client provided='{bool(client)}'")
        return None, None, None
        
    title, root_domain, html_content = None, None, None
    
    logger.info(f"[ScrapingBee] Attempting to scrape URL: {url}")

    try:
        # Attempt 1: Simple Fetch (render_js=False)
        logger.info(f"[ScrapingBee] Attempt 1: Simple fetch for {url} (render_js=False)")
        response_simple = client.get(url, params={'render_js': False, 'timeout': 15000, 'premium_proxy': True, 'country_code': 'us'})
        logger.info(f"[ScrapingBee] Simple fetch for {url} - Status: {response_simple.status_code}, Headers: {response_simple.headers.get('Spb-Resolved-Url', 'N/A')}, Content length: {len(response_simple.content)}")

        if response_simple.status_code == 200:
            html_simple = response_simple.text
            soup_simple = BeautifulSoup(html_simple, 'html.parser')
            title_tag_simple = soup_simple.find('title')
            title_simple = title_tag_simple.string.strip() if title_tag_simple else None
            
            if title_simple: # Check if title was found
                logger.info(f"[ScrapingBee] Simple fetch for {url} SUCCESSFUL. Title: '{title_simple[:100]}'")
                html_content, title = html_simple, title_simple
                extracted_domain = tldextract.extract(url)
                root_domain = f"{extracted_domain.domain}.{extracted_domain.suffix}"
                return title, root_domain, html_content
            else:
                logger.warning(f"[ScrapingBee] Simple fetch for {url} OK (status 200), but NO TITLE found. HTML length: {len(html_simple)}. Falling back to JS render.")
        else:
            logger.warning(f"[ScrapingBee] Simple fetch for {url} FAILED with status {response_simple.status_code}. Response text (first 200 chars): {response_simple.text[:200]}")
            # Fall through to JS rendering attempt
            
    except Exception as e:
        logger.error(f"[ScrapingBee] Error during simple fetch for {url}: {type(e).__name__} - {e}. Falling back to JS render.")
    
    # Attempt 2: JS Rendering Fetch (Fallback or if simple fetch had no title)
    try:
        logger.info(f"[ScrapingBee] Attempt 2: JS rendering fetch for {url} (render_js=True)")
        response_js = client.get(url, params={'render_js': True, 'timeout': 35000, 'wait': 3000, 'premium_proxy': True, 'country_code': 'us'})
        logger.info(f"[ScrapingBee] JS render fetch for {url} - Status: {response_js.status_code}, Headers: {response_js.headers.get('Spb-Resolved-Url', 'N/A')}, Content length: {len(response_js.content)}")

        if response_js.status_code == 200:
            html_content_js = response_js.text
            soup_js = BeautifulSoup(html_content_js, 'html.parser')
            title_tag_js = soup_js.find('title')
            title_js = title_tag_js.string.strip() if title_tag_js else None

            if title_js: # Title is primary success indicator
                logger.info(f"[ScrapingBee] JS render fetch for {url} SUCCESSFUL. Title: '{title_js[:100]}'")
            else: # Still no title, but content might be there
                logger.warning(f"[ScrapingBee] JS render fetch for {url} OK (status 200), but NO TITLE found. HTML length: {len(html_content_js)}.")
            
            # Always return content if status is 200 from JS render, even if no title
            extracted_domain = tldextract.extract(url)
            root_domain = f"{extracted_domain.domain}.{extracted_domain.suffix}"
            return title_js, root_domain, html_content_js
        else:
            logger.error(f"[ScrapingBee] JS render fetch for {url} FAILED with status {response_js.status_code}. Response text (first 200 chars): {response_js.text[:200]}")
            return None, None, None
            
    except Exception as e:
        logger.error(f"[ScrapingBee] Error during JS render fetch for {url}: {type(e).__name__} - {e}")
        return None, None, None

async def scrape_page_data_async(url: str, sb_client: ScrapingBeeClient) -> tuple[str | None, str | None, str | None]:
    """Async wrapper for the blocking scrape_page_data function."""
    if not url or not sb_client:
        # No need to log here, scrape_page_data will handle it
        return None, None, None
    try:
        # Run the synchronous function in a separate thread
        logger.debug(f"[ScrapingBee] Scheduling sync scrape_page_data for {url} in thread.")
        result = await asyncio.to_thread(scrape_page_data, url, sb_client)
        logger.debug(f"[ScrapingBee] Sync scrape_page_data for {url} finished in thread.")
        return result
    except Exception as e:
        logger.error(f"[ScrapingBee] Error running scrape_page_data in thread for {url}: {type(e).__name__} - {e}")
        return None, None, None 