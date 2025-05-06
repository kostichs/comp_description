import asyncio
from scrapingbee import ScrapingBeeClient
from bs4 import BeautifulSoup
import tldextract

def scrape_page_data(url: str, client: ScrapingBeeClient) -> tuple[str | None, str | None, str | None]:
    """Scrapes a page using ScrapingBee, trying simple fetch first, then fallback to JS rendering."""
    if not url or not client: return None, None, None
    title, root_domain, html_content = None, None, None
    try:
        # Attempt 1: Simple Fetch
        response_simple = client.get(url, params={'render_js': False, 'timeout': 15000})
        if response_simple.status_code == 200:
            html_simple = response_simple.text
            soup_simple = BeautifulSoup(html_simple, 'html.parser')
            title_tag_simple = soup_simple.find('title')
            title_simple = title_tag_simple.string.strip() if title_tag_simple else None
            if title_simple:
                html_content, title = html_simple, title_simple
                extracted_domain = tldextract.extract(url)
                root_domain = f"{extracted_domain.domain}.{extracted_domain.suffix}"
                return title, root_domain, html_content
            else: pass # Simple fetch ok, but no title
        else: pass # Simple fetch failed status
    except Exception as e: print(f"Error during sync simple fetch for {url}: {e}. Falling back.")
    
    # Attempt 2: JS Rendering Fetch (Fallback)
    try:
        response_js = client.get(url, params={'render_js': True, 'timeout': 25000, 'wait': 2000})
        if response_js.status_code == 200:
            html_content = response_js.text
            soup_js = BeautifulSoup(html_content, 'html.parser')
            title_tag_js = soup_js.find('title')
            title = title_tag_js.string.strip() if title_tag_js else None
            extracted_domain = tldextract.extract(url)
            root_domain = f"{extracted_domain.domain}.{extracted_domain.suffix}"
            return title, root_domain, html_content 
        else: return None, None, None
    except Exception as e: print(f"Error during sync JS render fetch for {url}: {e}"); return None, None, None

async def scrape_page_data_async(url: str, sb_client: ScrapingBeeClient) -> tuple[str | None, str | None, str | None]:
    """Async wrapper for the blocking scrape_page_data function."""
    if not url or not sb_client: return None, None, None
    try:
        # Run the synchronous function in a separate thread
        result = await asyncio.to_thread(scrape_page_data, url, sb_client)
        return result
    except Exception as e: print(f"Error running scrape_page_data in thread for {url}: {e}"); return None, None, None 