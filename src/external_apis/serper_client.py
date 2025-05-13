import aiohttp
import asyncio
import json
import re
import tldextract # For domain checks in ranking
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
import logging # Added for logging
from urllib.parse import urlparse, unquote # Added for path depth checking and URL decoding
from ..config import SPECIAL_COMPANY_HANDLING # Import the special handling rules
import socket
from typing import Optional, List, Dict, Any

# +++ Интеграция нового поиска homepage +++
from ..homepage_finder import find_company_homepage
# ++++++++++++++++++++++++++++++++++++++++

logger = logging.getLogger(__name__) # Added for logging

# Global list of blacklisted domains (registered domain part)
BLACKLISTED_DOMAINS_FOR_HP = [ # More aggressive blacklist for HP
    "wikipedia.org", "wikimedia.org", "youtube.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "linkedin.com", # LinkedIn is never a homepage
    "leadiq.com", "zoominfo.com", "apollo.io", "crunchbase.com", "owler.com",
    "bloomberg.com", "reuters.com", "forbes.com", "wsj.com", "nytimes.com", "cnn.com",
    "bbc.com", "theguardian.com", "techcrunch.com", "thenextweb.com",
    "github.com", "medium.com", "researchgate.net", "academia.edu",
    "slideshare.net", "scribd.com", "pinterest.com", "reddit.com",
    "amazon.com", "ebay.com", "aliexpress.com", "google.com", "apple.com", "microsoft.com",
    "support.google.com", "play.google.com", "maps.google.com",
    "books.google.com", "patents.google.com", "policies.google.com",
    "developer.apple.com", "support.apple.com", "apps.apple.com",
    "developer.microsoft.com", "support.microsoft.com",
    "gov", "edu", # Gov/edu are usually not company HPs unless specifically part of name/context
    "nic.in", "righttoeducation.in", "rajpsp.nic.in", "tiktok.com",
    "telegram.org", "whatsapp.com", "vimeo.com", "dailymotion.com",
    "yahoo.com", "bing.com", "duckduckgo.com", # Search engines
    "archive.org", # Archive sites
    # Common hosting/blog platforms if they are not the company\'s own
    "wordpress.com", "blogspot.com", "wix.com", "squarespace.com", "godaddy.com",
    # Job boards
    "indeed.com", "glassdoor.com", "monster.com", "careerbuilder.com",
    # App stores not directly linked to company product page (e.g. general store link)
    "play.google.com/store/apps", "apps.apple.com/us/app"
]

NEGATIVE_KEYWORDS_FOR_HP_URL_PATH = [
    "/blog/", "/news/", "/article/", "/story/", "/press/", "/event/", "/support/", "/forum/", "/wiki/",
    "/gallery/", "/shop/", "/store/", "/download/", "/map/", "/directions/", "/manual/", "/login/",
    "/register/", "/apply/", "/admission/", "/student/", "/terms/", "/privacy/", "/jobs/", "/careers/",
    "/login", "/signin", "/auth", # Exact path segments
    "wp-content", "wp-includes", # WordPress specific
    "user=", "session=", "redirect=" # Query parameters
]


# Function to normalize company name for simple comparison (used in LI scoring)
def normalize_name_for_domain_comparison(name: str) -> str:
    # Remove anything in parentheses
    name = re.sub(r'\s*\([^)]*\)', '', name)
    name = name.lower()
    common_suffixes = [
        ', inc.', ' inc.', ', llc', ' llc', ', ltd.', ' ltd.', ' ltd', ', gmbh', ' gmbh',
        ', s.a.', ' s.a.', ' plc', ' se', ' ag', ' oyj', ' ab', ' as', ' nv', ' bv', ' co.', ' co'
        ' corporation', ' company', ' group', ' holding', ' solutions', ' services',
        ' technologies', ' systems', ' international'
    ]
    for suffix in common_suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = re.sub(r'[^\w-]', '', name)
    return name.strip('-')

def check_direct_domain_match(url: str, company_name: str) -> bool:
    """Check if URL directly matches company name pattern (www.companyname.com or companyname.com)"""
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Get clean company name without parentheses
        clean_company_name = normalize_name_for_domain_comparison(company_name)
        
        # Check for exact match
        if domain == f"{clean_company_name}.com":
            return True
            
        # Check for regional TLDs
        if domain.startswith(f"{clean_company_name}."):
            return True
            
        return False
    except Exception:
        return False

async def _execute_serper_query(
    session: aiohttp.ClientSession,
    query: str,
    serper_api_key: str,
    headers: dict,
    num_results: int = 30,
    start_offset: int = 0
) -> dict | None:
    """Helper to execute a single Serper query and return JSON response."""
    payload = json.dumps({
        "q": query,
        "num": num_results,
        "start": start_offset,
        "gl": "us", # Consider making this adaptable based on context_keywords_dict location
        "hl": "en", # Consider making this adaptable
        "filter": 0 # Get all results
    })
    
    try:
        async with session.post("https://google.serper.dev/search", headers=headers, data=payload, timeout=20) as resp: # Increased timeout
            if resp.status == 200:
                results = await resp.json()
                logger.info(f"\n{'='*80}")
                logger.info(f"SERPER API RAW RESULTS FOR QUERY: {query}")
                logger.info(f"{'='*80}")
                if results and "organic" in results:
                    logger.info(f"Found {len(results['organic'])} organic results:")
                    for idx, res_item in enumerate(results["organic"], 1):
                        logger.info(f"  Result #{idx}: Link: {res_item.get('link', 'N/A')}, Title: {res_item.get('title', 'N/A')}, Snippet: {res_item.get('snippet', 'N/A')[:100]}...")
                else:
                    logger.info("No organic results found in Serper response.")
                logger.info(f"{'='*80}\n")
                return results
            else:
                error_text = await resp.text()
                logger.error(f"Serper API Error for query '{query}': Status {resp.status}, Response: {error_text[:300]}")
                return None
    except asyncio.TimeoutError:
        logger.error(f"Timeout for Serper query: '{query}'")
        return None
    except aiohttp.ClientError as e:
        logger.error(f"AIOHttp error for Serper query '{query}': {e}")
        return None
    except Exception as e:
        logger.error(f"Generic error for Serper query '{query}': {type(e).__name__} - {str(e)[:100]}")
        return None

def normalize_linkedin_url(url: str) -> str | None:
    """
    Normalizes LinkedIn URL to the format: https://www.linkedin.com/company/company-slug/about/
    Handles /company/, /school/, /showcase/ if they contain a clear slug.
    Decodes URL-encoded characters in the slug.
    """
    if not url or not isinstance(url, str):
        return None

    url_lower = url.lower()
    
    # Try to match /company/, /school/, /showcase/
    # Example: linkedin.com/company/example-inc%C3%A9
    # Example: linkedin.com/school/university-of-example/
    # Example: linkedin.com/showcase/example-product-line/
    match = re.search(r"linkedin\.com/(company|school|showcase)/([^/?#]+)", url_lower)
    
    if not match:
        # Fallback for less common but valid profile URLs if they somehow get here
        # e.g. linkedin.com/in/profile-name (unlikely for company search but as a safeguard)
        # or direct links like linkedin.com/company/example/ (without trailing slash or /about)
        # This regex is broader but we are primarily interested in /company/ structure
        if "linkedin.com/" in url_lower: # Basic check
            # Try to find a slug-like part even without /company/ prefix if it looks like a profile
            # This is less reliable and should ideally be caught by a good /company/ match first
            pass # For now, if no company/school/showcase, don't normalize unless it's a perfect /about already
        return None # If no clear company/school/showcase structure, cannot reliably normalize

    profile_type = match.group(1) # company, school, or showcase
    slug = match.group(2)

    # Decode URL-encoded characters in the slug (e.g., %20 for space, %C3%A9 for é)
    try:
        decoded_slug = unquote(slug)
    except Exception as e:
        logger.warning(f"Error decoding LinkedIn slug '{slug}' from URL '{url}': {e}")
        decoded_slug = slug # Use original slug if decoding fails

    # Clean the slug further: remove extra slashes or query params mistakenly included
    # The regex already handles ? and #, but trailing slashes might be part of slug
    cleaned_slug = decoded_slug.strip('/')

    if not cleaned_slug: # Empty slug after cleaning
        logger.warning(f"Empty slug after cleaning for LinkedIn URL: {url}")
        return None

    # For 'showcase' and 'school', we still normalize to /about/ for consistency,
    # though their actual "about" section might differ or not exist in the same way.
    # The main goal is to have a consistent URL structure for scraping attempts.
    return f"https://www.linkedin.com/{profile_type}/{cleaned_slug}/about/"

async def check_domain_availability(domain: str, timeout: float = 2.0) -> bool:
    """Check if domain is available and returns valid HTTP response"""
    try:
        # First try to resolve DNS
        try:
            socket.gethostbyname(domain)
        except socket.gaierror:
            return False

        # Try HTTPS first
        async with aiohttp.ClientSession() as session:
            try:
                async with session.head(f"https://{domain}", timeout=timeout, allow_redirects=True) as response:
                    if 200 <= response.status < 400:
                        return True
            except:
                pass

            # If HTTPS fails, try HTTP
            try:
                async with session.head(f"http://{domain}", timeout=timeout, allow_redirects=True) as response:
                    if 200 <= response.status < 400:
                        return True
            except:
                pass

        return False
    except Exception:
        return False

async def find_domain_by_tld(company_name: str) -> Optional[str]:
    """Try to find company domain by checking common TLDs"""
    # Common TLDs ordered by popularity
    common_tlds = [
        "com", "net", "org", "io", "co", "ai", "app", "dev", "tech", "digital",
        "cloud", "online", "site", "website", "info", "biz", "me", "tv", "studio",
        "agency", "group", "team", "solutions", "services", "systems", "technology"
    ]
    
    # Clean company name
    clean_name = normalize_name_for_domain_comparison(company_name)
    
    # Try each TLD
    for tld in common_tlds:
        domain = f"{clean_name}.{tld}"
        if await check_domain_availability(domain):
            return f"https://{domain}"
    
        return None

async def find_urls_with_serper_async(
    session: aiohttp.ClientSession,
    company_name: str,
    context_text: str | None,
    serper_api_key: str | None,
    openai_client: AsyncOpenAI | None, # openai_client теперь используется для find_company_homepage
    scoring_logger_obj: logging.Logger
) -> tuple[str | None, str | None, str | None, str | None]:
    
    if not serper_api_key:
        scoring_logger_obj.warning(f"SERPER_API_KEY missing for {company_name}. Cannot find URLs.")
        return None, None, None, None

    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}

    normalized_company_name_for_match = normalize_name_for_domain_comparison(company_name)
    scoring_logger_obj.info(f"Normalized name for general matching: '{normalized_company_name_for_match}'")

    # --- Новый поиск Homepage через homepage_finder ---
    selected_homepage_url: str | None = None
    if openai_client and openai_client.api_key: # Убедимся, что ключ есть
        scoring_logger_obj.info(f"Attempting to find homepage for '{company_name}' using homepage_finder module...")
        homepage_info = await find_company_homepage(
            company_name=company_name,
            serper_api_key=serper_api_key,
            openai_api_key=openai_client.api_key # Передаем API ключ напрямую
        )
        selected_homepage_url = homepage_info['url'] if homepage_info else None
        if selected_homepage_url:
            scoring_logger_obj.info(f"Homepage URL selected by homepage_finder for '{company_name}': {selected_homepage_url} (Source: {homepage_info.get('source', 'N/A') if homepage_info else 'N/A'})")
        else:
            scoring_logger_obj.warning(f"Homepage URL not found by homepage_finder for '{company_name}'.")
    else:
        scoring_logger_obj.warning(f"OpenAI client or API key not available, skipping homepage_finder for '{company_name}'.")
    # --- Конец нового поиска Homepage ---

    # Продолжаем поиск LinkedIn и Wikipedia через Serper, если это все еще необходимо
    # Если homepage_finder также может находить их, эту часть можно будет оптимизировать
    search_query = f"{company_name} official website linkedin company profile" # Можно сузить, если HP уже найден
    if selected_homepage_url: # Если homepage уже найден, можно сделать запрос более специфичным для LinkedIn
        search_query = f"{company_name} linkedin company profile"
        scoring_logger_obj.info(f"Homepage found by new module ({selected_homepage_url}). Refining Serper query for LinkedIn: \"{search_query}\"")
    else:
        scoring_logger_obj.info(f"Executing Serper API query for '{company_name}': \"{search_query}\"")
        
    serper_results_json = await _execute_serper_query(session, search_query, serper_api_key, headers, num_results=30)

    if not serper_results_json or not serper_results_json.get("organic"):
        scoring_logger_obj.warning(f"No organic results from Serper for '{company_name}' with query '{search_query}'.")
        # Возвращаем уже найденный selected_homepage_url (если есть) и None для остального
        return selected_homepage_url, None, None, None 
    
    organic_results = serper_results_json["organic"]
    scoring_logger_obj.info(f"Received {len(organic_results)} organic results from Serper for '{company_name}'.")

    selected_linkedin_url: str | None = None
    linkedin_snippet: str | None = None
    wikipedia_url: str | None = None

    scoring_logger_obj.info(f"\n--- Searching for LinkedIn URL for '{company_name}' (Scoring Method from Serper results) ---")
    linkedin_candidates = []
    for res_li in organic_results:
        link_li = res_li.get("link")
        title_li = res_li.get("title", "").lower()
        if not link_li or not isinstance(link_li, str) or "linkedin.com/" not in link_li.lower(): continue
        normalized_li_url = normalize_linkedin_url(link_li)
        if normalized_li_url:
            slug_match_li = re.search(r"linkedin\.com/(?:company|school|showcase)/([^/]+)/about/?", normalized_li_url.lower())
            slug_li = slug_match_li.group(1) if slug_match_li else ""
            score_li = 0
            reason_li = []
            if "/company/" in normalized_li_url.lower(): score_li += 20; reason_li.append("/company/ link:+20")
            elif "/showcase/" in normalized_li_url.lower(): score_li += 5; reason_li.append("/showcase/ link:+5")
            elif "/school/" in normalized_li_url.lower(): score_li += 3; reason_li.append("/school/ link:+3")
            if slug_li and normalized_company_name_for_match in slug_li.replace('-', ''): score_li += 15; reason_li.append(f"Name in slug ({slug_li}):+15")
            elif normalized_company_name_for_match in title_li.replace('-', '').replace(' ', ''): score_li += 10; reason_li.append(f"Name in title ({title_li[:30]}...):+10")
            elif any(part_li in slug_li.replace('-', '') for part_li in normalized_company_name_for_match.split('-') if len(part_li) > 2): score_li += 7; reason_li.append(f"Part of name in slug ({slug_li}):+7")
            elif any(part_li in title_li.replace('-', '').replace(' ', '') for part_li in normalized_company_name_for_match.split('-') if len(part_li) > 2): score_li += 5; reason_li.append(f"Part of name in title ({title_li[:30]}...):+5")
            if "jobs" in title_li or "careers" in title_li or "/jobs" in link_li.lower() or "/careers" in link_li.lower():
                if not ("/company/" in normalized_li_url.lower() and score_li > 20): score_li -= 5; reason_li.append("Jobs/careers term:-5")
            if score_li > 0:
                linkedin_candidates.append({"url": normalized_li_url, "score": score_li, "title": title_li, "slug": slug_li or title_li, "reason": ", ".join(reason_li), "snippet": res_li.get("snippet", "")})
                scoring_logger_obj.debug(f"  LI Candidate: {normalized_li_url}, Score: {score_li}, Slug/Title: '{slug_li or title_li}', Reason: {', '.join(reason_li)}")
        else: scoring_logger_obj.debug(f"  Skipped non-normalizable LinkedIn-like URL: {link_li}")
    if linkedin_candidates:
        linkedin_candidates.sort(key=lambda x: x["score"], reverse=True)
        best_linkedin = linkedin_candidates[0]
        selected_linkedin_url = best_linkedin["url"]
        linkedin_snippet = best_linkedin["snippet"]
        scoring_logger_obj.info(f"Selected LinkedIn URL (by score): {selected_linkedin_url} (Score: {best_linkedin['score']}, Slug/Title: '{best_linkedin['slug'] or best_linkedin['title'][:30]}')")
        if linkedin_snippet:
             scoring_logger_obj.info(f"  Associated LinkedIn Snippet: '{linkedin_snippet[:100]}...'")
    else: scoring_logger_obj.warning(f"No suitable LinkedIn URL found for '{company_name}'.")

    # 4. Find Wikipedia URL (Simple search using organic_results from possibly refined query)
    wikipedia_url = None 
    if organic_results: # organic_results теперь могут быть отфильтрованы или от нового запроса
        scoring_logger_obj.debug(f"  Checking {len(organic_results)} Serper results for Wikipedia link...") 
        for i, result in enumerate(organic_results):
            link = result.get("link", "")
            if not link:
                scoring_logger_obj.debug(f"    Result #{i+1}: Skipping empty link.") 
                continue
            
            try:
                parsed_link = urlparse(link)
                netloc_lower = parsed_link.netloc.lower()
                scoring_logger_obj.debug(f"    Result #{i+1}: Checking link '{link}' -> netloc: '{netloc_lower}'") 
                
                if "wikipedia.org" in netloc_lower:
                    wikipedia_url = link 
                    scoring_logger_obj.info(f"  Found potential Wikipedia URL: {wikipedia_url}") 
                    break 
            except Exception as e:
                 scoring_logger_obj.warning(f"    Result #{i+1}: Error parsing link '{link}': {e}") 

        if not wikipedia_url:
             scoring_logger_obj.warning(f"  No Wikipedia URL found in Serper results for '{company_name}'.") 

    scoring_logger_obj.info(f"\n--- Final URL Selection for '{company_name}' ---")
    scoring_logger_obj.info(f"  > find_urls_with_serper_async is returning HP: '{selected_homepage_url}', LI: '{selected_linkedin_url}', LI Snippet: '{linkedin_snippet[:50] if linkedin_snippet else 'None'}...', Wiki: '{wikipedia_url}' for '{company_name}'")

    return selected_homepage_url, selected_linkedin_url, linkedin_snippet, wikipedia_url 

async def test_serper_query(company_name: str, serper_api_key: str) -> None:
    """Test function to fetch and print 10 Google search results using Serper API."""
    async with aiohttp.ClientSession() as session:
        headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
        search_query = f"{company_name} official website linkedin company profile"
        results = await _execute_serper_query(session, search_query, serper_api_key, headers, num_results=10)
        if results and "organic" in results:
            print("Top 10 Google search results:")
            for idx, res_item in enumerate(results["organic"], 1):
                print(f"{idx}. {res_item.get('link', 'N/A')}")
        else:
            print("No results found.") 