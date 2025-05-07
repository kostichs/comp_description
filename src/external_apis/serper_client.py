import aiohttp
import asyncio
import json
import re
import tldextract # For domain checks in ranking
import numpy as np # For embeddings
from sklearn.metrics.pairwise import cosine_similarity # For embeddings
from openai import AsyncOpenAI # To pass the client for embeddings
import logging # Added for logging
from ..external_apis.openai_client import get_embedding_async, is_url_company_page_llm # Ensure this is imported
from urllib.parse import urlparse, unquote # Added for path depth checking and URL decoding
from ..config import SPECIAL_COMPANY_HANDLING # Import the special handling rules

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
    # Common hosting/blog platforms if they are not the company's own
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
                logging.info(f"\\n{'='*80}")
                logging.info(f"SERPER API RAW RESULTS FOR QUERY: {query}")
                logging.info(f"{'='*80}")
                if results and "organic" in results:
                    logging.info(f"Found {len(results['organic'])} organic results:")
                    for idx, res_item in enumerate(results["organic"], 1):
                        logging.info(f"  Result #{idx}: Link: {res_item.get('link', 'N/A')}, Title: {res_item.get('title', 'N/A')}, Snippet: {res_item.get('snippet', 'N/A')[:100]}...")
                else:
                    logging.info("No organic results found in Serper response.")
                logging.info(f"{'='*80}\\n")
                return results
            else:
                error_text = await resp.text()
                logging.error(f"Serper API Error for query '{query}': Status {resp.status}, Response: {error_text[:300]}")
                return None
    except asyncio.TimeoutError:
        logging.error(f"Timeout for Serper query: '{query}'")
        return None
    except aiohttp.ClientError as e:
        logging.error(f"AIOHttp error for Serper query '{query}': {e}")
        return None
    except Exception as e:
        logging.error(f"Generic error for Serper query '{query}': {type(e).__name__} - {str(e)[:100]}")
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
        logging.warning(f"Error decoding LinkedIn slug '{slug}' from URL '{url}': {e}")
        decoded_slug = slug # Use original slug if decoding fails

    # Clean the slug further: remove extra slashes or query params mistakenly included
    # The regex already handles ? and #, but trailing slashes might be part of slug
    cleaned_slug = decoded_slug.strip('/')

    if not cleaned_slug: # Empty slug after cleaning
        logging.warning(f"Empty slug after cleaning for LinkedIn URL: {url}")
        return None

    # For 'showcase' and 'school', we still normalize to /about/ for consistency,
    # though their actual "about" section might differ or not exist in the same way.
    # The main goal is to have a consistent URL structure for scraping attempts.
    return f"https://www.linkedin.com/{profile_type}/{cleaned_slug}/about/"


async def find_urls_with_serper_async(
    session: aiohttp.ClientSession,
    company_name: str,
    context_text: str | None,
    serper_api_key: str | None,
    openai_client: AsyncOpenAI | None, 
    scoring_logger_obj: logging.Logger
) -> tuple[str | None, str | None]:
    
    if not serper_api_key:
        scoring_logger_obj.warning(f"SERPER_API_KEY missing for {company_name}. Cannot find URLs.")
        return None, None

    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    
    # 0. Prepare company name for LI matching (still needed for LI scoring)
    normalized_company_name_for_li_match = normalize_name_for_domain_comparison(company_name)
    scoring_logger_obj.info(f"Normalized name for LI scoring: '{normalized_company_name_for_li_match}'")

    # 1. Serper Query (Simplified as requested)
    search_query = f"company {company_name}" # Keep it simple
    scoring_logger_obj.info(f"Executing Serper API query for '{company_name}': \"{search_query}\"")
    # Request more results to have a better pool for selection, even with simpler query
    serper_results_json = await _execute_serper_query(session, search_query, serper_api_key, headers, num_results=30)

    if not serper_results_json or not serper_results_json.get("organic"):
        scoring_logger_obj.warning(f"No organic results from Serper for '{company_name}' with query '{search_query}'.")
        return None, None
    
    organic_results = serper_results_json["organic"]
    scoring_logger_obj.info(f"Received {len(organic_results)} organic results from Serper for '{company_name}'.")

    # --- Variables to store selected URLs ---
    selected_linkedin_url: str | None = None
    selected_homepage_url: str | None = None
    
    # --- 2. Find LinkedIn URL (Using the scoring logic - unchanged) ---
    scoring_logger_obj.info(f"\n--- Searching for LinkedIn URL for '{company_name}' (Scoring Method) ---")
    linkedin_candidates: list[tuple[str, str, int]] = []
    for res in organic_results:
        link = res.get("link")
        title = res.get("title", "").lower()
        if not link or not isinstance(link, str) or "linkedin.com/" not in link.lower(): continue
        normalized_li_url = normalize_linkedin_url(link)
        if normalized_li_url:
            slug_match = re.search(r"linkedin\.com/(?:company|school|showcase)/([^/]+)/about/?", normalized_li_url.lower())
            slug = slug_match.group(1) if slug_match else ""
            score = 0
            reason = []
            if "/company/" in normalized_li_url.lower(): score += 20; reason.append("/company/ link:+20")
            elif "/showcase/" in normalized_li_url.lower(): score += 5; reason.append("/showcase/ link:+5")
            elif "/school/" in normalized_li_url.lower(): score += 3; reason.append("/school/ link:+3")
            if slug and normalized_company_name_for_li_match in slug.replace('-', ''): score += 15; reason.append(f"Name in slug ({slug}):+15")
            elif normalized_company_name_for_li_match in title.replace('-', '').replace(' ', ''): score += 10; reason.append(f"Name in title ({title[:30]}...):+10")
            elif any(part in slug.replace('-', '') for part in normalized_company_name_for_li_match.split('-') if len(part) > 2): score += 7; reason.append(f"Part of name in slug ({slug}):+7")
            elif any(part in title.replace('-', '').replace(' ', '') for part in normalized_company_name_for_li_match.split('-') if len(part) > 2): score += 5; reason.append(f"Part of name in title ({title[:30]}...):+5")
            if "jobs" in title or "careers" in title or "/jobs" in link.lower() or "/careers" in link.lower():
                if not ("/company/" in normalized_li_url.lower() and score > 20): score -= 5; reason.append("Jobs/careers term:-5")
            if score > 0:
                linkedin_candidates.append((normalized_li_url, slug or title, score))
                scoring_logger_obj.debug(f"  LI Candidate: {normalized_li_url}, Score: {score}, Slug/Title: '{slug or title}', Reason: {', '.join(reason)}")
        else: scoring_logger_obj.debug(f"  Skipped non-normalizable LinkedIn-like URL: {link}")
    if linkedin_candidates:
        linkedin_candidates.sort(key=lambda x: x[2], reverse=True)
        selected_linkedin_url = linkedin_candidates[0][0]
        scoring_logger_obj.info(f"Selected LinkedIn URL (by score): {selected_linkedin_url} (Score: {linkedin_candidates[0][2]}, Slug/Title: '{linkedin_candidates[0][1]}')")
    else: scoring_logger_obj.warning(f"No suitable LinkedIn URL found for '{company_name}'.")

    # --- 3. Find Homepage URL (Using LLM with LESS strict pre-filtering) ---
    scoring_logger_obj.info(f"\n--- Searching for Homepage URL for '{company_name}' (LLM Method with relaxed pre-filtering) ---")
    
    homepage_candidates_for_llm: list[dict] = []
    # Define a smaller, core blacklist for pre-filtering - LLM should handle the rest based on prompt
    CORE_BLACKLIST = [
        "linkedin.com", "youtube.com", "facebook.com", "twitter.com", "x.com",
        "instagram.com", "pinterest.com", "reddit.com", "tiktok.com",
        "wikipedia.org", "wikimedia.org" # Keep the most obvious non-HP sites out
    ]
    
    for res in organic_results:
        link = res.get("link")
        title = res.get("title", "")
        snippet = res.get("snippet", "")
        
        if not link or not isinstance(link, str):
            continue 
        
        try:
            parsed_url = urlparse(link)
            if not parsed_url.scheme or parsed_url.scheme not in ["http", "https"]:
                 scoring_logger_obj.debug(f"  Skipping LLM HP candidate {link}: Invalid scheme")
                 continue
            if not parsed_url.netloc:
                 scoring_logger_obj.debug(f"  Skipping LLM HP candidate {link}: Missing domain")
                 continue
                 
            # Simplified pre-filtering: only check core blacklist
            extracted_parts = tldextract.extract(link)
            registered_domain = extracted_parts.registered_domain.lower()
            is_core_blacklisted = False
            for blacklisted in CORE_BLACKLIST:
                if blacklisted in registered_domain:
                     is_core_blacklisted = True
                     break
            
            if is_core_blacklisted:
                scoring_logger_obj.debug(f"  Skipping LLM HP candidate {link}: Domain '{registered_domain}' is in CORE blacklist.")
                continue
            
            # REMOVED check for NEGATIVE_KEYWORDS_FOR_HP_URL_PATH before LLM call
            # Trust LLM to evaluate path relevance based on prompt
                 
            # If passed basic scheme/domain checks and CORE blacklist, add to list for LLM
            homepage_candidates_for_llm.append({
                "link": link,
                "title": title,
                "snippet": snippet
            })
            
        except Exception as e:
            scoring_logger_obj.warning(f"Error filtering HP candidate link {link} for LLM: {type(e).__name__} - {e}")
            continue

    if not homepage_candidates_for_llm:
        scoring_logger_obj.warning(f"No suitable homepage candidates found to send to LLM for '{company_name}' after relaxed pre-filtering.")
    elif not openai_client:
        scoring_logger_obj.warning(f"OpenAI client not available, cannot use LLM to select homepage for '{company_name}'.")
    else:
        # Prepare context for LLM prompt (limit candidate list size if needed)
        MAX_CANDIDATES_FOR_LLM = 15 
        if len(homepage_candidates_for_llm) > MAX_CANDIDATES_FOR_LLM:
             scoring_logger_obj.debug(f"Trimming homepage candidates for LLM from {len(homepage_candidates_for_llm)} to {MAX_CANDIDATES_FOR_LLM}")
             homepage_candidates_for_llm = homepage_candidates_for_llm[:MAX_CANDIDATES_FOR_LLM]
             
        candidates_str = "\n".join([f"- URL: {c['link']}\n  Title: {c['title']}\n  Snippet: {c['snippet']}" for c in homepage_candidates_for_llm])
        
        # Using the same robust prompt as before
        prompt = f"""
Analyze the list of URLs below for the company named '{company_name}'. 
Company context: {context_text or 'Not provided'}

Your task is to identify the single, most likely *official homepage URL* for this specific company. 

Consider these criteria:
- It must be the main corporate website, not a specific product page (unless it's the only site), blog, news article, login page, or profile on another platform.
- Avoid parent companies or subsidiaries if they seem distinct from '{company_name}', unless the context suggests otherwise.
- Prefer root domains (e.g., example.com) or primary regional domains (e.g., example.co.uk).
- Critically evaluate sites like Crunchbase, ZoomInfo, Bloomberg, Forbes, news sites, PDF links, general directories - these are almost never the official homepage.

Candidate URLs:
{candidates_str}

Based on your analysis, return ONLY the single best official homepage URL from the list above. If absolutely none of the candidates seem suitable as the official homepage according to the criteria, return the exact word 'None'.
"""
        
        scoring_logger_obj.info(f"Calling LLM to select homepage from {len(homepage_candidates_for_llm)} candidates (using relaxed pre-filtering) for '{company_name}'.")
        try:
            response = await openai_client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200, 
                temperature=0.1, 
                n=1,
                stop=None
            )
            llm_choice = response.choices[0].message.content.strip()
            scoring_logger_obj.info(f"LLM choice for homepage: '{llm_choice}'")
            
            if llm_choice and llm_choice.lower() != 'none' and (llm_choice.startswith('http://') or llm_choice.startswith('https://')):
                is_candidate = False
                for candidate in homepage_candidates_for_llm:
                     if candidate['link'] == llm_choice:
                         is_candidate = True
                         break
                if is_candidate:
                    selected_homepage_url = llm_choice
                    scoring_logger_obj.info(f"Selected Homepage URL (LLM Choice): {selected_homepage_url}")
                else:
                     scoring_logger_obj.warning(f"LLM returned a URL '{llm_choice}' which was not in the candidate list for '{company_name}'. Ignoring.")
            elif llm_choice.lower() == 'none':
                 scoring_logger_obj.info(f"LLM indicated no suitable homepage found for '{company_name}'.")
            else:
                 scoring_logger_obj.warning(f"LLM returned unexpected response for homepage selection for '{company_name}': '{llm_choice}'. Treating as no selection.")
                 
        except Exception as e:
            scoring_logger_obj.error(f"Error calling LLM for homepage selection for '{company_name}': {type(e).__name__} - {e}")
            # selected_homepage_url remains None

    # --- 4. Final Logging ---
    scoring_logger_obj.info(f"\n{'='*50}")
    scoring_logger_obj.info(f"FINAL URLs determined for '{company_name}':")
    scoring_logger_obj.info(f"  Homepage: {selected_homepage_url}")
    scoring_logger_obj.info(f"  LinkedIn: {selected_linkedin_url}")
    scoring_logger_obj.info(f"{'='*50}\n")

    return selected_homepage_url, selected_linkedin_url 