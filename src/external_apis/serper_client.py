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
) -> tuple[str | None, str | None, str | None, str | None]:
    
    if not serper_api_key:
        scoring_logger_obj.warning(f"SERPER_API_KEY missing for {company_name}. Cannot find URLs.")
        return None, None, None, None

    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    
    normalized_company_name_for_li_match = normalize_name_for_domain_comparison(company_name)
    scoring_logger_obj.info(f"Normalized name for LI scoring: '{normalized_company_name_for_li_match}'")

    search_query = f"{company_name} official website"
    scoring_logger_obj.info(f"Executing Serper API query for '{company_name}': \"{search_query}\"")
    serper_results_json = await _execute_serper_query(session, search_query, serper_api_key, headers, num_results=30)

    if not serper_results_json or not serper_results_json.get("organic"):
        scoring_logger_obj.warning(f"No organic results from Serper for '{company_name}' with query '{search_query}'.")
        return None, None, None, None
    
    organic_results = serper_results_json["organic"]
    scoring_logger_obj.info(f"Received {len(organic_results)} organic results from Serper for '{company_name}'.")

    selected_homepage_url: str | None = None
    selected_linkedin_url: str | None = None
    linkedin_snippet: str | None = None
    wikipedia_url: str | None = None
    
    scoring_logger_obj.info(f"\n--- Searching for LinkedIn URL for '{company_name}' (Scoring Method) ---")
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
            if slug_li and normalized_company_name_for_li_match in slug_li.replace('-', ''): score_li += 15; reason_li.append(f"Name in slug ({slug_li}):+15")
            elif normalized_company_name_for_li_match in title_li.replace('-', '').replace(' ', ''): score_li += 10; reason_li.append(f"Name in title ({title_li[:30]}...):+10")
            elif any(part_li in slug_li.replace('-', '') for part_li in normalized_company_name_for_li_match.split('-') if len(part_li) > 2): score_li += 7; reason_li.append(f"Part of name in slug ({slug_li}):+7")
            elif any(part_li in title_li.replace('-', '').replace(' ', '') for part_li in normalized_company_name_for_li_match.split('-') if len(part_li) > 2): score_li += 5; reason_li.append(f"Part of name in title ({title_li[:30]}...):+5")
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

    scoring_logger_obj.info(f"\n--- Searching for Homepage URL for '{company_name}' (LLM Method with Few-Shot) ---")
    
    homepage_candidates_for_llm: list[dict] = []
    CORE_BLACKLIST = [
        "linkedin.com", "youtube.com", "facebook.com", "twitter.com", "x.com",
        "instagram.com", "pinterest.com", "reddit.com", "tiktok.com",
        "wikipedia.org", "wikimedia.org" 
    ]
    for res in organic_results:
        link = res.get("link")
        title = res.get("title", "")
        snippet = res.get("snippet", "")
        if not link or not isinstance(link, str): continue 
        try:
            parsed_url = urlparse(link)
            if not parsed_url.scheme or parsed_url.scheme not in ["http", "https"]:
                 scoring_logger_obj.debug(f"  Skipping LLM HP candidate {link}: Invalid scheme")
                 continue
            if not parsed_url.netloc:
                 scoring_logger_obj.debug(f"  Skipping LLM HP candidate {link}: Missing domain")
                 continue
            extracted_parts = tldextract.extract(link)
            registered_domain = extracted_parts.registered_domain.lower()
            is_core_blacklisted = any(blacklisted in registered_domain for blacklisted in CORE_BLACKLIST)
            if is_core_blacklisted:
                scoring_logger_obj.debug(f"  Skipping LLM HP candidate {link}: Domain '{registered_domain}' is in CORE blacklist.")
                continue
            homepage_candidates_for_llm.append({"link": link, "title": title, "snippet": snippet})
        except Exception as e:
            scoring_logger_obj.warning(f"Error pre-filtering HP candidate link {link} for LLM: {type(e).__name__} - {e}")
            continue

    if not homepage_candidates_for_llm:
        scoring_logger_obj.warning(f"No suitable homepage candidates found to send to LLM for '{company_name}' after pre-filtering.")
    elif not openai_client:
        scoring_logger_obj.warning(f"OpenAI client not available, cannot use LLM to select homepage for '{company_name}'.")
    else:
        MAX_CANDIDATES_FOR_LLM = 15 
        if len(homepage_candidates_for_llm) > MAX_CANDIDATES_FOR_LLM:
             scoring_logger_obj.debug(f"Trimming homepage candidates for LLM from {len(homepage_candidates_for_llm)} to {MAX_CANDIDATES_FOR_LLM}")
             homepage_candidates_for_llm = homepage_candidates_for_llm[:MAX_CANDIDATES_FOR_LLM]
        
        scoring_logger_obj.info(f"Homepage candidates for LLM for '{company_name}' ({len(homepage_candidates_for_llm)} total):")
        for idx, cand_item in enumerate(homepage_candidates_for_llm):
            scoring_logger_obj.info(f"  #{idx+1}: URL: {cand_item['link']}, Title: {cand_item['title'][:70]}..., Snippet: {cand_item['snippet'][:100]}...")
             
        candidates_str = "\n".join([f"- {c['link']}\n  Title: {c['title']}\n  Snippet: {c['snippet']}" for c in homepage_candidates_for_llm])
        
        # --- Prepare context for LLM Homepage Selection (including Wiki URL if found) ---
        llm_context_info = context_text or "General Business"
        if wikipedia_url:
            llm_context_info += f". Wikipedia page found: {wikipedia_url}"
            scoring_logger_obj.info(f"  Adding found Wikipedia URL to context for LLM Homepage selection.")

        system_prompt_content = f"""You are a reliable assistant that, given a list of URLs for a single company, name the one official homepage for the company {company_name}. 
Always output EXACTLY the URL on a single line, without any extra commentary."""
        
        few_shot_user_content = f"""
Example 1:
Company: Acme Corp
Context: Technology solutions provider
Candidates:
- https://acme.com
  Title: Acme Corp - Innovative Solutions
  Snippet: Acme Corp provides cutting-edge technology solutions for businesses全球.
- https://acme.blog.com
  Title: Acme Blog
  Snippet: Latest news and updates from Acme Corp.
- https://linkedin.com/company/acme/about/
  Title: Acme Corp | LinkedIn
  Snippet: About Acme Corp on LinkedIn.
Answer: https://acme.com

Example 2:
Company: Foo Bar Inc.
Context: Local bakery. Wikipedia page found: https://en.wikipedia.org/wiki/Foo_Bar_Inc
Candidates:
- https://linkedin.com/company/foo-bar-inc/about/
  Title: Foo Bar Inc. | LinkedIn
  Snippet: Foo Bar Inc. LinkedIn page.
- https://en.wikipedia.org/wiki/Foo_Bar_Inc
  Title: Foo Bar Inc. - Wikipedia
  Snippet: Wikipedia article about Foo Bar Inc.
- https://www.some_directory.com/foo-bar-inc
  Title: Foo Bar Inc. - Business Directory
  Snippet: Foo Bar Inc. listed in Some Directory.
Answer: None

Now:
Company: {company_name}
Context: {llm_context_info} 
Candidates:
{candidates_str}
Answer:
"""
        
        messages_for_llm = [
            {"role": "system", "content": system_prompt_content},
            {"role": "user", "content": few_shot_user_content}
        ]
        
        scoring_logger_obj.info(f"Calling LLM with few-shot prompt to select homepage from {len(homepage_candidates_for_llm)} candidates for '{company_name}'.")
        scoring_logger_obj.debug(f"LLM User Prompt for '{company_name}':\n{few_shot_user_content}")

        try:
            response = await openai_client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=messages_for_llm,
                max_tokens=150,
                temperature=0.0,
                top_p=1.0,
                n=1,
                stop=None
            )
            
            llm_choice_content = ""
            finish_reason = "unknown"
            full_message_object_str = "N/A"

            if response.choices and len(response.choices) > 0:
                choice = response.choices[0]
                llm_choice_content = choice.message.content.strip() if choice.message and choice.message.content else ""
                finish_reason = choice.finish_reason
                full_message_object_str = str(choice.message) 
                scoring_logger_obj.info(f"LLM raw choice for '{company_name}': '{llm_choice_content}', Finish Reason: {finish_reason}")
                scoring_logger_obj.debug(f"LLM full message object for '{company_name}': {full_message_object_str}")
            else:
                scoring_logger_obj.warning(f"LLM response for '{company_name}' had no choices or empty choice.")

            # Validate LLM's choice (Relaxed validation)
            if llm_choice_content and llm_choice_content.lower() != 'none':
                # Check if it's a valid URL format
                if re.match(r'^https?://', llm_choice_content):
                    # Check if it was one of the candidates (case-insensitive, whitespace stripped)
                    normalized_llm_choice = llm_choice_content.strip().lower()
                    is_candidate = False
                    matching_candidate_url = None
                    for candidate in homepage_candidates_for_llm:
                         if candidate['link'].strip().lower() == normalized_llm_choice:
                             is_candidate = True
                             matching_candidate_url = candidate['link'] # Use the original candidate URL
                             break # Found a match

                    if is_candidate and matching_candidate_url:
                        selected_homepage_url = matching_candidate_url # Assign the original candidate URL
                        scoring_logger_obj.info(f"Selected Homepage URL (LLM Attempt 1, Validated): {selected_homepage_url}")
                    else:
                        scoring_logger_obj.warning(f"LLM Attempt 1 returned URL '{llm_choice_content}' which did NOT EXACTLY match (after normalization) any candidate link for '{company_name}'. Ignoring. Full LLM Message: {full_message_object_str}")
                else:
                    scoring_logger_obj.warning(f"LLM Attempt 1 returned NON-URL choice '{llm_choice_content}' for '{company_name}'. Ignoring. Full LLM Message: {full_message_object_str}")
            elif llm_choice_content.lower() == 'none':
                 scoring_logger_obj.info(f"LLM Attempt 1 explicitly returned 'None' - no suitable homepage found for '{company_name}'. Full LLM Message: {full_message_object_str}")
            elif not llm_choice_content: 
                 scoring_logger_obj.warning(f"LLM Attempt 1 returned an EMPTY string response for '{company_name}'. Finish Reason: {finish_reason}. Full LLM Message: {full_message_object_str}. Treating as no selection.")
            else: # Other unexpected content
                 scoring_logger_obj.warning(f"LLM Attempt 1 returned UNEXPECTED response for '{company_name}': '{llm_choice_content}'. Finish Reason: {finish_reason}. Full LLM Message: {full_message_object_str}. Treating as no selection.")
                 
        except Exception as e:
            scoring_logger_obj.error(f"Error during LLM Attempt 1 for homepage selection for '{company_name}': {type(e).__name__} - {str(e)}")

        # --- LLM Retry Logic --- 
        if not selected_homepage_url and homepage_candidates_for_llm:
            scoring_logger_obj.warning(f"LLM Attempt 1 failed to select a valid homepage for '{company_name}'. Trying LLM Attempt 2 with a more direct prompt.")
            
            # New, more forceful prompt
            retry_system_prompt_content = f"""You are an assistant that MUST select the single most likely official homepage URL for the company {company_name} from the provided list. 
Output ONLY the URL itself, nothing else. Do NOT output 'None'."""
            
            # Re-use the same few-shot examples structure but without the option for 'None' in the final answer instruction
            retry_user_content = f"""
Example 1:
Company: Acme Corp
Context: Technology solutions provider
Candidates:
- https://acme.com
  Title: Acme Corp - Innovative Solutions
  Snippet: Acme Corp provides cutting-edge technology solutions for businesses全球.
- https://acme.blog.com
  Title: Acme Blog
  Snippet: Latest news and updates from Acme Corp.
- https://linkedin.com/company/acme/about/
  Title: Acme Corp | LinkedIn
  Snippet: About Acme Corp on LinkedIn.
Answer: https://acme.com

Example 2:
Company: Foo Bar Inc.
Context: Local bakery. Wikipedia page found: https://en.wikipedia.org/wiki/Foo_Bar_Inc
Candidates:
- https://linkedin.com/company/foo-bar-inc/about/
  Title: Foo Bar Inc. | LinkedIn
  Snippet: Foo Bar Inc. LinkedIn page.
- https://en.wikipedia.org/wiki/Foo_Bar_Inc
  Title: Foo Bar Inc. - Wikipedia
  Snippet: Wikipedia article about Foo Bar Inc.
- https://www.some_directory.com/foo-bar-inc
  Title: Foo Bar Inc. - Business Directory
  Snippet: Foo Bar Inc. listed in Some Directory.
Answer: https://www.some_directory.com/foo-bar-inc # Example adjustment: Force a choice even if weak

Now:
Company: {company_name}
Context: {llm_context_info}
Candidates:
{candidates_str}
Instruction: Select the single most likely official homepage from the list above.
Answer:""" # Removed the final Answer: prompt to let model complete
            
            retry_messages = [
                 {"role": "system", "content": retry_system_prompt_content},
                 {"role": "user", "content": retry_user_content}
            ]
            
            scoring_logger_obj.info(f"Calling LLM Attempt 2 with forceful prompt for '{company_name}'.")
            scoring_logger_obj.debug(f"LLM Retry User Prompt for '{company_name}':\n{retry_user_content}")
            
            try:
                retry_response = await openai_client.chat.completions.create(
                    model="gpt-4o-mini", 
                    messages=retry_messages,
                    max_tokens=150, 
                    temperature=0.0, # Keep deterministic
                    top_p=1.0,
                    n=1,
                    stop=None
                )
                
                retry_choice_content = ""
                retry_finish_reason = "unknown"
                retry_full_message_object_str = "N/A"

                if retry_response.choices and len(retry_response.choices) > 0:
                    retry_choice = retry_response.choices[0]
                    retry_choice_content = retry_choice.message.content.strip() if retry_choice.message and retry_choice.message.content else ""
                    retry_finish_reason = retry_choice.finish_reason
                    retry_full_message_object_str = str(retry_choice.message)
                    scoring_logger_obj.info(f"LLM Attempt 2 raw choice for '{company_name}': '{retry_choice_content}', Finish Reason: {retry_finish_reason}")
                    scoring_logger_obj.debug(f"LLM Attempt 2 full message object for '{company_name}': {retry_full_message_object_str}")
                else:
                    scoring_logger_obj.warning(f"LLM Attempt 2 response for '{company_name}' had no choices or empty choice.")

                # Validate Retry LLM's choice (still needs validation)
                if retry_choice_content and retry_choice_content.lower() != 'none': # Should ideally not output None, but check anyway
                    if re.match(r'^https?://', retry_choice_content):
                        normalized_retry_choice = retry_choice_content.strip().lower()
                        is_retry_candidate = False
                        matching_retry_candidate_url = None
                        for candidate in homepage_candidates_for_llm:
                            if candidate['link'].strip().lower() == normalized_retry_choice:
                                is_retry_candidate = True
                                matching_retry_candidate_url = candidate['link']
                                break
                        
                        if is_retry_candidate and matching_retry_candidate_url:
                            selected_homepage_url = matching_retry_candidate_url # Assign the validated URL
                            scoring_logger_obj.info(f"Selected Homepage URL (LLM Attempt 2, Validated): {selected_homepage_url}")
                        else:
                             scoring_logger_obj.error(f"LLM Attempt 2 returned URL '{retry_choice_content}' which was NOT in candidate list for '{company_name}'. Cannot use. Full LLM Message: {retry_full_message_object_str}")
                    else:
                        scoring_logger_obj.error(f"LLM Attempt 2 returned NON-URL choice '{retry_choice_content}' for '{company_name}'. Cannot use. Full LLM Message: {retry_full_message_object_str}")
                else: # Includes None or empty string
                    scoring_logger_obj.error(f"LLM Attempt 2 FAILED to provide a usable URL choice for '{company_name}', despite forceful prompt. Response: '{retry_choice_content}'. Full LLM Message: {retry_full_message_object_str}")

            except Exception as e_retry:
                scoring_logger_obj.error(f"Error during LLM Attempt 2 for homepage selection for '{company_name}': {type(e_retry).__name__} - {str(e_retry)}")

    # 4. Find Wikipedia URL (Simple search)
    wikipedia_url = None # <<< MOVED INITIALIZATION HERE
    if organic_results:
        scoring_logger_obj.debug(f"  Checking {len(organic_results)} Serper results for Wikipedia link...") # DEBUG
        for i, result in enumerate(organic_results):
            link = result.get("link", "")
            if not link:
                scoring_logger_obj.debug(f"    Result #{i+1}: Skipping empty link.") # DEBUG
                continue
            
            try:
                parsed_link = urlparse(link)
                netloc_lower = parsed_link.netloc.lower()
                scoring_logger_obj.debug(f"    Result #{i+1}: Checking link '{link}' -> netloc: '{netloc_lower}'") # DEBUG
                
                # Basic check for wikipedia.org domain 
                if "wikipedia.org" in netloc_lower:
                    wikipedia_url = link # Assign the found URL
                    scoring_logger_obj.info(f"  Found potential Wikipedia URL: {wikipedia_url}") 
                    break # Take the first one found
            except Exception as e:
                 scoring_logger_obj.warning(f"    Result #{i+1}: Error parsing link '{link}': {e}") # DEBUG

        if not wikipedia_url:
             scoring_logger_obj.warning(f"  No Wikipedia URL found in Serper results for '{company_name}'.") # DEBUG

    scoring_logger_obj.info(f"\\n--- Final URL Selection for '{company_name}' ---")
    scoring_logger_obj.info(f"  > find_urls_with_serper_async is returning HP: '{selected_homepage_url}', LI: '{selected_linkedin_url}', LI Snippet: '{linkedin_snippet[:50] if linkedin_snippet else 'None'}...', Wiki: '{wikipedia_url}' for '{company_name}'")

    return selected_homepage_url, selected_linkedin_url, linkedin_snippet, wikipedia_url 