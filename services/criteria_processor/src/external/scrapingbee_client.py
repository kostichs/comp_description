import requests
import json
import os
import re
from datetime import datetime
from src.utils.config import SCRAPINGBEE_API_KEY, OUTPUT_DIR
from src.utils.logging import log_debug, log_error
from urllib.parse import urlparse


def _sanitize_filename(name: str) -> str:
    """Sanitizes a string to be used as a valid filename."""
    # Remove invalid characters for Windows filenames
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def save_scrapingbee_result(session_id: str, company_name: str, url: str, result_data: dict):
    """Saves the ScrapingBee result to a single human-readable session log file."""
    if not session_id:
        return

    try:
        log_dir = os.path.join(OUTPUT_DIR, session_id, "scrapingbee_logs")
        os.makedirs(log_dir, exist_ok=True)
        filepath = os.path.join(log_dir, "scrapingbee_session.log")

        # Create a human-readable, multi-line string with proper newlines
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_code = result_data.get('status_code', 'N/A')
        error = result_data.get('error')
        
        log_entry = f"--- Request at {timestamp} ---\n"
        log_entry += f"Company: {company_name}\n"
        log_entry += f"URL: {url}\n"
        log_entry += f"Status Code: {status_code}\n"

        if error:
            log_entry += f"Error: {error}\n"
        else:
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

        log_entry += "----------------------------------------\n\n"

        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(log_entry)
            
    except Exception as e:
        log_error(f"Failed to save ScrapingBee log for {company_name}: {e}")

def scrape_website_text(url: str, session_id: str, company_name: str) -> str | None:
    """
    Scrapes the text content of a given URL using the ScrapingBee API.

    Args:
        url (str): The URL to scrape.
        session_id (str): The current session ID for logging.
        company_name (str): The company name for logging.


    Returns:
        str | None: The extracted text content of the website, or None if scraping fails.
    """
    if not SCRAPINGBEE_API_KEY:
        log_error("ScrapingBee API key is not configured.")
        save_scrapingbee_result(session_id, company_name, url, {
            "error": "ScrapingBee API key not configured."
        })
        return None

    log_debug(f"🐝 Scraping URL: {url} for {company_name}")
    response = None
    try:
        response = requests.get(
            url="https://app.scrapingbee.com/api/v1/",
            params={
                "api_key": SCRAPINGBEE_API_KEY,
                "url": url,
                "extract_rules": {"text": "body"},
            },
            timeout=120,
        )
        
        response.raise_for_status()
        
        data = response.json()
        
        save_scrapingbee_result(session_id, company_name, url, {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "response_body": data
        })

        scraped_text = data.get('text')

        if data.get("error"):
            log_error(f"❌ ScrapingBee API error for {url}: {data.get('message')}")
            return None

        if not scraped_text:
            log_debug(f"⚠️ Scraped content is empty for {url}")
            return None

        log_debug(f"✅ Scraped successfully, content length: {len(scraped_text)} chars")
        return scraped_text

    except requests.exceptions.RequestException as e:
        log_error(f"❌ Failed to scrape {url}: {e}")
        save_scrapingbee_result(session_id, company_name, url, {
            "status_code": e.response.status_code if e.response is not None else "N/A",
            "error": f"RequestException: {str(e)}"
        })
        return None
    except json.JSONDecodeError:
        log_error(f"❌ Failed to decode JSON response from ScrapingBee for {url}. Response: {response.text if response else 'No response'}")
        save_scrapingbee_result(session_id, company_name, url, {
            "status_code": response.status_code if response is not None else 'N/A',
            "error": "JSONDecodeError",
            "response_body": response.text if response is not None else "N/A"
        })
        return None 