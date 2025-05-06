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
from urllib.parse import urlparse # Added for path depth checking
from ..config import SPECIAL_COMPANY_HANDLING # Import the special handling rules

# Global list of blacklisted domains (registered domain part)
BLACKLISTED_DOMAINS = [
    "wikipedia.org", "wikimedia.org", "youtube.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", # "linkedin.com", # LinkedIn is handled by prefer_linkedin_company logic
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
    # "gov", "edu" # Re-evaluating gov/edu, some company-like orgs might use these
    "nic.in", "righttoeducation.in", "rajpsp.nic.in"
]

NEGATIVE_KEYWORDS_FOR_RANKING = [
    "blog", "review", "pdf", "story", "article", "event", "stories", "press", "support", "forum", "wiki", 
    "gallery", "price", "shop", "store", "download", "map", "directions", "manual",
    "login", "register", "apply", "admission", "student", "terms", "privacy" # Added more specific non-core page terms
    # Removed "news", "careers" - they can be on corporate sites
]

PREFERRED_TLDS = ["com", "org", "net", "co", "io", "ai", "biz", "info"] # Added

def normalize_company_name_for_domain_match(name: str) -> str:
    name = name.lower()
    # Remove common suffixes and punctuation
    suffixes_to_remove = [", inc.", " inc.", ", llc", " llc", ", ltd.", " ltd.", ", gmbh", " gmbh", ", s.a.", " s.a.", " co.", " co", " corporation", " company", " group", " holding", " solutions", " services", " technologies", " systems", " international", " se", " ag", " oyj", " plc", " ab", " as", " nv", " bv"]
    for suffix in suffixes_to_remove:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = re.sub(r'[\s,&.-_\(\)\[\]\{\}]', '', name) # Remove spaces and common punctuation
    return name

def extract_location_from_name(name: str) -> str | None:
    """Extracts text from parentheses at the end of the name, assumed to be location."""
    # Regex to find content within the last parentheses in the string
    # It looks for content between ( and ) that are at the end of the string, or followed by spaces and then end.
    match = re.search(r'\(([^)]+)\)\s*$', name)
    if match:
        return match.group(1).strip()
    return None

def parse_context_for_keywords(context_text: str | None, company_name_for_hint: str | None = None) -> dict:
    """Extracts structured keywords like industry and location from context text or company name hint."""
    keywords = {"industry": "", "location": "", "location_tld": "", "generic": ""}
    
    # Attempt to get location hint from company name itself if context_text is initially missing for location
    if company_name_for_hint and (not context_text or not re.search(r"(?:location|region|country|city|area|market)[:\s]*", context_text, re.IGNORECASE)):
        location_hint_from_name = extract_location_from_name(company_name_for_hint)
        if location_hint_from_name:
            keywords["location"] = location_hint_from_name.lower()
            # Try to parse TLD from this hint as well
            tld_match = re.search(r'[\(\[]?\.?([a-zA-Z]{2,3}(?:\.[a-zA-Z]{2,3})?)[\)\]]?$', keywords["location"]) 
            if tld_match:
                potential_tld = tld_match.group(1)
                if not any(char.isdigit() for char in potential_tld) and len(potential_tld.replace(".","")) <=5 : 
                     keywords["location_tld"] = potential_tld.replace(".","")

    if context_text: # Process context_text if provided
        industry_match = re.search(r"(?:industry|sector|field|branch|specialization|focus)[:\s]*(.+?)(?:\n|,|;|\.|and|$)", context_text, re.IGNORECASE)
        if industry_match: keywords["industry"] = industry_match.group(1).strip().lower()
        
        location_match = re.search(r"(?:location|region|country|city|area|market)[:\s]*(.+?)(?:\n|,|;|\.|and|$)", context_text, re.IGNORECASE)
        if location_match: # If context_text explicitly defines location, it overrides hint from name
            location_str = location_match.group(1).strip().lower()
            keywords["location"] = location_str
            tld_match = re.search(r'[\(\[]?\.?([a-zA-Z]{2,3}(?:\.[a-zA-Z]{2,3})?)[\)\]]?$', location_str) 
            if tld_match:
                potential_tld = tld_match.group(1)
                if not any(char.isdigit() for char in potential_tld) and len(potential_tld.replace(".","")) <=5 : 
                     keywords["location_tld"] = potential_tld.replace(".","")
    
    # Generic keywords if others are not found from context_text
    if context_text and not keywords["industry"] and not keywords["location"]:
        words = re.findall(r'\b[a-zA-Z]{3,}\b', context_text.lower())
        common_query_words = ["source", "event", "notes", "looking", "for", "companies"]
        filtered_words = [word for word in words if word.lower() not in common_query_words]
        keywords["generic"] = " ".join(filtered_words[:3])
    # print(f"DEBUG Parsed Context for '{company_name_for_hint}': {keywords}")
    return keywords

async def _execute_serper_query(session: aiohttp.ClientSession, query: str, serper_api_key: str, headers: dict) -> dict | None:
    """Helper to execute a single Serper query and return JSON response."""
    payload = json.dumps({"q": query, "num": 7}) # MODIFIED: Request more results (e.g., 7)
    # print(f"  DEBUG Serper Query: {query}")
    try:
        async with session.post("https://google.serper.dev/search", headers=headers, data=payload, timeout=15) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                # print(f"  Serper API Error for query '{query}': Status {resp.status}, Response: {await resp.text()[:200]}")
                return None
    except asyncio.TimeoutError: print(f"  Timeout for Serper query: '{query}'"); return None
    except aiohttp.ClientError as e: print(f"  AIOHttp error for Serper query '{query}': {e}"); return None
    except Exception as e: print(f"  Generic error for Serper query '{query}': {type(e).__name__} - {str(e)[:100]}"); return None

async def rank_serper_results_async(results: dict | None, company_name: str, company_embedding: list[float] | None, 
                                  openai_client: AsyncOpenAI, # Still needed for get_embedding_async
                                  context_keywords_dict: dict, 
                                  scoring_logger: logging.Logger, 
                                  prefer_linkedin_company: bool = False) -> str | None:
    if not results or not results.get("organic"): return None
    company_name_lower = company_name.lower()
    normalized_company_name_for_domain = normalize_company_name_for_domain_match(company_name)
    best_link = None
    max_score = -float('inf') 
    
    # Adjusted thresholds for heuristic-only ranking before LLM check in pipeline
    BASE_SCORE_THRESHOLD = 7.0 
    NON_PREFERRED_TLD_SCORE_THRESHOLD = 5.0 

    scoring_logger.debug(f"-- Ranking for '{company_name}' (LinkedIn Pref: {prefer_linkedin_company}) Context: {context_keywords_dict} --")

    candidate_links_data = []
    for res in results["organic"][:5]: # Analyze top 5
        link = res.get("link")
        title = res.get("title", "").lower()
        snippet = res.get("snippet", "").lower()
        if not link: continue
        candidate_links_data.append({"link": link, "title": title, "snippet": snippet})
    
    embedding_tasks = []
    if company_embedding and openai_client: # openai_client is used by get_embedding_async
        for candidate in candidate_links_data:
            text_for_embedding = f"{candidate['title']} {candidate['snippet']}"
            embedding_tasks.append(get_embedding_async(text_for_embedding, openai_client))
    
    candidate_embeddings = [None] * len(candidate_links_data)
    if embedding_tasks:
        gathered_embeddings = await asyncio.gather(*embedding_tasks, return_exceptions=True)
        for i, emb_result in enumerate(gathered_embeddings):
            if not isinstance(emb_result, Exception) and emb_result is not None:
                candidate_embeddings[i] = emb_result

    processed_candidates_scores = []
    for i, data in enumerate(candidate_links_data):
        link, title, snippet = data["link"], data["title"], data["snippet"]
        score = 0
        score_log_details = [] 
        current_dynamic_threshold = BASE_SCORE_THRESHOLD 
        try:
            extracted_link_parts = tldextract.extract(link)
            registered_domain = extracted_link_parts.registered_domain.lower()
            domain_name_part = extracted_link_parts.domain.lower()
            link_suffix = extracted_link_parts.suffix.lower()
            if link_suffix not in PREFERRED_TLDS: current_dynamic_threshold = NON_PREFERRED_TLD_SCORE_THRESHOLD
        except Exception: continue

        if registered_domain in BLACKLISTED_DOMAINS or link_suffix in ["gov"]:
            score = -200; score_log_details.append("BLACKLISTED_DOMAIN/TLD:-200")
        else:
            if prefer_linkedin_company:
                match = re.search(r"linkedin\.com/company/([^/?]+)", link.lower())
                if match:
                    slug = match.group(1)
                    if slug == normalized_company_name_for_domain: score += 20; score_log_details.append(f"linkedin_exact_slug('{slug}'):+20")
                    elif slug.startswith(normalized_company_name_for_domain): score += 10; score_log_details.append(f"linkedin_partial_slug_start('{slug}'):+10")
                    elif normalized_company_name_for_domain in slug: score += 7; score_log_details.append(f"linkedin_slug_contains_name('{slug}'):+7")
                    else: score += 5; score_log_details.append("linkedin_company_url_generic:+5")
                    if company_name_lower in title: score += 3; score_log_details.append("li_company_in_title:+3")
                else: score = -200; score_log_details.append("not_linkedin_company_url_format:-200") 
            else: 
                is_exact_domain_match = False
                if normalized_company_name_for_domain == domain_name_part and link_suffix in PREFERRED_TLDS:
                    score += 20 
                    score_log_details.append(f"exact_domain_preferred_tld({link_suffix}):+20")
                    is_exact_domain_match = True 
                elif any(part in domain_name_part for part in company_name_lower.split() if len(part)>2 and len(part) < len(domain_name_part)): 
                    score += 3; score_log_details.append("partial_domain_match:+3")
                
                parsed_url_path = urlparse(link).path
                is_root_path = False
                if not parsed_url_path or parsed_url_path == '/': 
                    score += 10; score_log_details.append("root_path:+10") 
                    is_root_path = True
                elif parsed_url_path.count('/') == 1 and not parsed_url_path.endswith('/'): 
                     score += 2; score_log_details.append("shallow_path:+2")
                
                # Auto-accept logic for exact domain match on root path for PREFERRED TLDs
                if is_exact_domain_match and is_root_path: 
                    scoring_logger.info(f"  >> Auto-accept (Exact Domain + Root Path Preferred TLD) for '{company_name}': {link} (Score: {score})")
                    # To make this less aggressive, we can simply let this high score pass the threshold naturally later
                    # For now, we keep the auto-accept for this very strong signal.
                    return link 

                if company_name_lower in title: score += 5; score_log_details.append("company_in_title:+5")
                if company_name_lower in snippet: score += 3; score_log_details.append("company_in_snippet:+3")
                name_parts = [p for p in company_name_lower.split() if len(p) > 2] 
                if not name_parts and len(company_name_lower) > 2: name_parts = [company_name_lower]
                for w in name_parts:
                    if w in title: score += 1; score_log_details.append(f"part({w})_in_title:+1")
                    if w in snippet: score += 0.5; score_log_details.append(f"part({w})_in_snippet:+0.5")
                if "official" in title or "official" in snippet: score += 4; score_log_details.append("official_keyword:+4")
                if "homepage" in title: score += 2; score_log_details.append("homepage_keyword:+2")
                for neg_kw in NEGATIVE_KEYWORDS_FOR_RANKING:
                    if neg_kw in title: score -= 3; score_log_details.append(f"neg_kw({neg_kw})_in_title:-3") 
                    if f"/{neg_kw}" in link.lower(): score -= 3; score_log_details.append(f"neg_kw({neg_kw})_in_link:-3") 
                    if neg_kw in snippet: score -= 1; score_log_details.append(f"neg_kw({neg_kw})_in_snippet:-1") 
                context_tld = context_keywords_dict.get("location_tld", "")
                normalized_company_part_for_tld_check = normalized_company_name_for_domain.split('&')[0]
                if context_tld and link_suffix == context_tld and domain_name_part.startswith(normalized_company_part_for_tld_check):
                    score += 20; score_log_details.append(f"strong_context_tld_match({context_tld}_for_{domain_name_part}):+20")
                elif context_tld and link_suffix == context_tld:
                    score += 5; score_log_details.append(f"context_tld_match({context_tld}):+5")
                elif link_suffix in PREFERRED_TLDS and not (is_exact_domain_match and link_suffix in PREFERRED_TLDS) and not (context_tld and link_suffix == context_tld):
                    score += 1; score_log_details.append(f"preferred_tld({link_suffix}):+1")
                elif link_suffix not in PREFERRED_TLDS + ([context_tld] if context_tld else []):
                     if context_keywords_dict.get("location") and link_suffix not in context_keywords_dict.get("location").lower():
                         score -=1; score_log_details.append("cctld_mismatch_location:-1") 
                for key_type in ["industry", "location", "generic"]:
                    ctx_kw = context_keywords_dict.get(key_type, "")
                    if ctx_kw:
                        for word in ctx_kw.split():
                            if len(word)>2:
                                if word in snippet: score += 1.0; score_log_details.append(f"ctx_snip({word}):+1.0")
                                if word in title: score += 0.5; score_log_details.append(f"ctx_title({word}):+0.5")
            
            if company_embedding and i < len(candidate_embeddings) and candidate_embeddings[i] and not isinstance(candidate_embeddings[i], Exception):
                snippet_embedding = candidate_embeddings[i]
                try:
                    similarity = cosine_similarity(np.array(company_embedding).reshape(1, -1), np.array(snippet_embedding).reshape(1, -1))[0][0]
                    if similarity > 0.65: score += similarity * 3; score_log_details.append(f"embed_sim:{similarity*3:.1f}(raw:{similarity:.2f})")
                except Exception as e_cos: scoring_logger.warning(f"Cosine sim error for {link}: {e_cos}")
        
        # LLM VERIFICATION STEP IS REMOVED FROM RANK_SERPER_RESULTS
        # It will be done in process_company AFTER successful scrape of the top candidate from this ranking.
        
        processed_candidates_scores.append((score, link, current_dynamic_threshold, title, snippet, score_log_details)) 

    processed_candidates_scores.sort(key=lambda x: x[0], reverse=True)

    for score, link, threshold, title, snippet, log_details in processed_candidates_scores:
        scoring_logger.debug(f"  Ranked Candidate: {link} | Title: '{title[:60]}...' | FINAL SCORE: {score:.1f} | Threshold: {threshold} | Factors: {', '.join(log_details)}")
        if score >= threshold:
            scoring_logger.info(f"  >> Selected Link by Heuristics for '{company_name}': {link} (Score: {score:.1f}, Threshold: {threshold})")
            return link # Return the first one that meets its dynamic threshold
            
    best_score_overall = processed_candidates_scores[0][0] if processed_candidates_scores else -float('inf')
    best_link_overall = processed_candidates_scores[0][1] if processed_candidates_scores else None
    scoring_logger.info(f"  >> No link met heuristic threshold for '{company_name}'. Best heuristic score: {best_score_overall:.1f} for {best_link_overall}")
    return None

async def find_urls_with_serper_async(session: aiohttp.ClientSession, company_name: str, context_text: str | None, serper_api_key: str | None, openai_client: AsyncOpenAI | None, scoring_logger_obj: logging.Logger) -> tuple[str | None, str | None]:
    if not serper_api_key: scoring_logger_obj.warning(f"SERPER_API_KEY missing for {company_name}"); return None, None
    homepage_url, linkedin_url = None, None
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    context_keywords_dict = parse_context_for_keywords(context_text, company_name_for_hint=company_name)
    industry_ctx = context_keywords_dict.get("industry", "")
    location_ctx = context_keywords_dict.get("location", "")
    generic_ctx = context_keywords_dict.get("generic", "")
    company_name_embedding = None
    if openai_client: company_name_embedding = await get_embedding_async(company_name, openai_client) # For ranker

    queries_hp = [
        f'{company_name} {industry_ctx} {location_ctx} official website'.strip().replace("  ", " "),
        f'{company_name} official site {generic_ctx}'.strip().replace("  ", " "),
        f'{company_name} homepage'.strip()
    ]
    for query in queries_hp:
        if homepage_url: break 
        results = await _execute_serper_query(session, query, serper_api_key, headers)
        # Pass openai_client to ranker for embeddings, not for LLM check on snippet
        homepage_url = await rank_serper_results_async(results, company_name, company_name_embedding, openai_client, context_keywords_dict, scoring_logger_obj)
    
    await asyncio.sleep(0.2) 
    queries_li = [
        f'{company_name} {industry_ctx} {location_ctx} site:linkedin.com/company'.strip().replace("  ", " "),
        f'{company_name} site:linkedin.com/company {generic_ctx}'.strip().replace("  ", " "),
        f'{company_name} LinkedIn company profile'.strip()
    ]
    for query in queries_li:
        if linkedin_url: break
        results = await _execute_serper_query(session, query, serper_api_key, headers)
        linkedin_url = await rank_serper_results_async(results, company_name, company_name_embedding, openai_client, context_keywords_dict, scoring_logger_obj, prefer_linkedin_company=True)
    
    if not homepage_url and linkedin_url:
        homepage_url = linkedin_url 
        scoring_logger_obj.info(f"  >> Fallback: Using LinkedIn URL as homepage for '{company_name}': {linkedin_url}")
    elif not homepage_url:
        scoring_logger_obj.info(f"  > Serper: HP not found for {company_name} and no LI fallback.")
    if not linkedin_url: 
        scoring_logger_obj.info(f"  > Serper: LI not found for {company_name} after {len(queries_li)} attempts.")
    return homepage_url, linkedin_url 