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

PREFERRED_TLDS = ["com", "ru", "ie", "ag", "ua", "uk"] # UPDATED

def normalize_company_name_for_domain_match(name: str) -> str:
    name = name.lower()
    # Remove common suffixes and punctuation
    suffixes_to_remove = [", inc.", " inc.", ", llc", " llc", ", ltd.", " ltd.", ", gmbh", " gmbh", ", s.a.", " s.a.", " co.", " co", " corporation", " company", " group", " holding", " solutions", " services", " technologies", " systems", " international", " se", " ag", " oyj", " plc", " ab", " as", " nv", " bv"]
    for suffix in suffixes_to_remove:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = re.sub(r'[\s,&.-_\(\)\[\]\{\}]', '', name) # Remove spaces and common punctuation
    return name

def _prepare_company_name_for_strict_domain_check(name: str) -> str:
    """Prepares company name for strict domain matching: lowercase, remove spaces/punctuation, remove leading 'www'."""
    name = name.lower()
    # Remove spaces and specific punctuation that typically separates words in a name but not part of a domain
    # Hyphen is placed at the end of the character set to be treated as a literal.
    name = re.sub(r'[\s\.,&\(\)\[\]\{\}-]', '', name) 
    # Remove leading "www" if it exists after the above cleaning
    if name.startswith("www"): #This handles cases where company name itself might be "www.companyname"
        name = name[3:]
    # Example: "R.T.E." -> "rte", "WWW.Company Group" -> "companygroup", "1+1 Media" -> "1+1media"
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
    payload = json.dumps({"q": query, "num": 20}) # MODIFIED: Request more results (e.g., 20)
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
                                  openai_client: AsyncOpenAI, 
                                  context_keywords_dict: dict, 
                                  scoring_logger: logging.Logger, 
                                  prefer_linkedin_company: bool = False) -> str | None:
    if not results or not results.get("organic"):
        scoring_logger.debug(f"-- No organic results for '{company_name}'. Context: {context_keywords_dict} --")
        return None

    prepared_company_name_for_check = _prepare_company_name_for_strict_domain_check(company_name)
    
    scoring_logger.debug(f"-- Strict Ranking Pass 1 for '{company_name}' (Prepared: '{prepared_company_name_for_check}', LinkedIn Pref: {prefer_linkedin_company}) --")

    # Strict Pass 1
    for res in results["organic"]: 
        link = res.get("link")
        title = res.get("title", "").lower()
        if not link: continue

        try:
            extracted_link_parts = tldextract.extract(link)
            # domain_name_part is like 'a1' from 'jobs.a1.com' or 'a1' from 'a1.com'
            domain_name_part = extracted_link_parts.domain.lower() 
            link_suffix = extracted_link_parts.suffix.lower() 
            parsed_url_path = urlparse(link).path
            is_root_path = (not parsed_url_path or parsed_url_path == '/')
            # registered_domain is like 'a1.com' from 'jobs.a1.com'
            current_registered_domain = extracted_link_parts.registered_domain.lower() 
            subdomain = extracted_link_parts.subdomain.lower() # e.g., 'jobs' or 'www' or ''

            if current_registered_domain in BLACKLISTED_DOMAINS:
                scoring_logger.debug(f"  L1 Candidate {link} SKIPPED (Blacklisted: {current_registered_domain})")
                continue
            
            if prefer_linkedin_company:
                match = re.search(r"linkedin\.com/company/([^/?]+)", link.lower())
                if match:
                    linkedin_slug = match.group(1).lower()
                    normalized_company_for_li_slug = normalize_company_name_for_domain_match(company_name)
                    score = 0
                    log_details = []
                    if normalized_company_for_li_slug == linkedin_slug: score += 20; log_details.append(f"li_exact_slug({linkedin_slug}):+20")
                    elif linkedin_slug.startswith(normalized_company_for_li_slug): score += 10; log_details.append(f"li_slug_starts_with({linkedin_slug}):+10")
                    elif normalized_company_for_li_slug in linkedin_slug: score += 7; log_details.append(f"li_slug_contains({linkedin_slug}):+7")
                    else: score +=3; log_details.append(f"li_generic_company_page:+3")
                    if company_name.lower() in title: score += 5; log_details.append(f"li_name_in_title:+5")
                    
                    LINKEDIN_STRICT_THRESHOLD = 10.0 
                    if score >= LINKEDIN_STRICT_THRESHOLD:
                        scoring_logger.info(f"  >> L1 Selected LinkedIn for '{company_name}': {link} (Score: {score}, Title: '{title[:60]}'). Details: {', '.join(log_details)}")
                        return link
                    else:
                        scoring_logger.debug(f"  L1 LinkedIn Candidate {link} for '{company_name}' (Slug: {linkedin_slug}) did not meet LI threshold {LINKEDIN_STRICT_THRESHOLD}. Score: {score}. Details: {', '.join(log_details)}")
                else:
                    scoring_logger.debug(f"  L1 Candidate {link} SKIPPED (Not a LinkedIn company URL format when preferred).")
                continue 

            # Strict Check for Homepage (HP)
            # 1. The `prepared_company_name_for_check` must be the `domain` part (e.g. 'a1' from 'a1.com' or 'a1' from 'jobs.a1.com')
            # 2. Subdomain must be empty or 'www'. This filters out things like 'jobs.a1.com'.
            # 3. TLD must be in the PREFERRED_TLDS list
            # 4. Path must be root
            
            is_correct_domain_name = (domain_name_part == prepared_company_name_for_check)
            is_valid_subdomain = (subdomain == "" or subdomain == "www")
            is_preferred_tld = (link_suffix in PREFERRED_TLDS)
            
            scoring_logger.debug(f"  L1 Checking HP Candidate: {link} (PrepName: '{prepared_company_name_for_check}', DomainPart: '{domain_name_part}', Subdomain: '{subdomain}', Suffix: '{link_suffix}', IsRoot: {is_root_path})")

            if is_correct_domain_name and is_valid_subdomain and is_preferred_tld and is_root_path:
                scoring_logger.info(f"  >> L1 Selected HP (Strict) for '{company_name}': {link}")
                return link
            else:
                log_reasons = []
                if not is_correct_domain_name: log_reasons.append(f"DomainPartMismatch ('{domain_name_part}'!N='{prepared_company_name_for_check}')")
                if not is_valid_subdomain: log_reasons.append(f"InvalidSubdomain ('{subdomain}')")
                if not is_preferred_tld: log_reasons.append(f"SuffixNotInPreferred ('{link_suffix}' vs {PREFERRED_TLDS})")
                if not is_root_path: log_reasons.append(f"NotRootPath ('{parsed_url_path}')")
                if log_reasons: 
                     scoring_logger.debug(f"  L1 Candidate {link} FAILED strict HP. Reasons: {', '.join(log_reasons)}")
        except Exception as e:
            scoring_logger.warning(f"  L1 Error processing link {link} for '{company_name}': {type(e).__name__} - {e}")
            continue
    
    scoring_logger.info(f"  -- Strict Pass 1 for '{company_name}' did not yield a result. Proceeding to Pass 2 (flexible scoring). --")

    # Pass 2: Flexible Scoring (Restoring previous logic with adjustments)
    # This part will be added in the next step. For now, returning None if Pass 1 fails.
    # --- START OF RESTORED FLEXIBLE SCORING (to be completed) ---
    
    # Placeholder for restored logic - for now, we just log and return None if strict pass fails
    # This section will be filled with the previous scoring mechanism.

    old_score_threshold = 7.0 # Default from previous general logic
    non_preferred_tld_score_threshold = 5.0 # Default from previous general logic

    processed_candidates_scores = []
    # We need to re-iterate or store results from the first pass if we don't want to make another API call
    # For now, let's assume we re-iterate for simplicity, though it's less efficient for embeddings.
    # In a real scenario, you might collect all 'organic' results once.
    
    candidate_links_data = []
    if results and results.get("organic"): # Ensure results are still available
        for res in results["organic"]: # Iterate through all fetched results again for Pass 2
            link = res.get("link")
            title = res.get("title", "").lower()
            snippet = res.get("snippet", "").lower() # Snippet is used in flexible scoring
            if not link: continue
            candidate_links_data.append({"link": link, "title": title, "snippet": snippet})

    # Embedding generation (if needed by flexible scoring)
    # This was part of the original flexible scoring
    company_embedding_for_pass2 = None
    if openai_client: # Check if embeddings are generally enabled
         # We need to decide if we re-calculate or pass the original `company_embedding`
         # Assuming `company_embedding` is the embedding of the company_name itself and can be reused.
         company_embedding_for_pass2 = company_embedding

    candidate_embeddings = [None] * len(candidate_links_data)
    if company_embedding_for_pass2 and openai_client and candidate_links_data:
        embedding_tasks = []
        for candidate_data in candidate_links_data:
            text_for_embedding = f"{candidate_data['title']} {candidate_data['snippet']}"
            embedding_tasks.append(get_embedding_async(text_for_embedding, openai_client))
        
        if embedding_tasks:
            gathered_embeddings = await asyncio.gather(*embedding_tasks, return_exceptions=True)
            for i, emb_result in enumerate(gathered_embeddings):
                if not isinstance(emb_result, Exception) and emb_result is not None:
                    candidate_embeddings[i] = emb_result
    
    for i, data in enumerate(candidate_links_data):
        link, title, snippet = data["link"], data["title"], data["snippet"]
        score = 0
        score_log_details = [] 
        current_dynamic_threshold = old_score_threshold
        
        try:
            extracted_link_parts = tldextract.extract(link)
            current_registered_domain = extracted_link_parts.registered_domain.lower()
            domain_name_part_pass2 = extracted_link_parts.domain.lower()
            link_suffix_pass2 = extracted_link_parts.suffix.lower()

            if link_suffix_pass2 not in PREFERRED_TLDS: # Using the updated PREFERRED_TLDS
                current_dynamic_threshold = non_preferred_tld_score_threshold

            if current_registered_domain in BLACKLISTED_DOMAINS or link_suffix_pass2 == "gov": # gov still generally blacklisted for HP
                score = -200; score_log_details.append("BLACKLISTED_DOMAIN/TLD:-200")
            else:
                if prefer_linkedin_company: # If LI was preferred and not found in Pass 1, we don't re-evaluate here for LI
                                        # This pass is primarily for HP fallback if LI preferred search failed.
                                        # Or, if LI was not preferred, this is the main HP flexible search.
                    pass # Handled in L1 for LI, or if not prefer_li, this is for HP
                
                # Flexible scoring for HP
                normalized_company_name_for_domain = normalize_company_name_for_domain_match(company_name) # Old normalizer

                # Exact domain (less strict than L1, considers old PREFERRED_TLDS or broader list if defined)
                if normalized_company_name_for_domain == domain_name_part_pass2 and link_suffix_pass2 in PREFERRED_TLDS: # Check against current PREFERRED_TLDS
                    score += 15; score_log_details.append(f"flex_exact_domain_pref_tld({link_suffix_pass2}):+15")
                elif any(part in domain_name_part_pass2 for part in company_name.lower().split() if len(part)>2 and len(part) < len(domain_name_part_pass2)): 
                    score += 3; score_log_details.append("flex_partial_domain_match:+3")
                
                parsed_url_path_pass2 = urlparse(link).path
                if not parsed_url_path_pass2 or parsed_url_path_pass2 == '/': 
                    score += 7; score_log_details.append("flex_root_path:+7") 
                elif parsed_url_path_pass2.count('/') == 1 and not parsed_url_path_pass2.endswith('/'): 
                     score += 1; score_log_details.append("flex_shallow_path:+1")

                if company_name.lower() in title: score += 5; score_log_details.append("flex_company_in_title:+5")
                if company_name.lower() in snippet: score += 3; score_log_details.append("flex_company_in_snippet:+3")
                
                name_parts = [p for p in company_name.lower().split() if len(p) > 2] 
                if not name_parts and len(company_name.lower()) > 2: name_parts = [company_name.lower()]
                for w in name_parts:
                    if w in title: score += 1; score_log_details.append(f"flex_part({w})_in_title:+1")
                    if w in snippet: score += 0.5; score_log_details.append(f"flex_part({w})_in_snippet:+0.5")
                
                if "official" in title or "official" in snippet: score += 4; score_log_details.append("flex_official_keyword:+4")
                if "homepage" in title: score += 2; score_log_details.append("flex_homepage_keyword:+2")
                
                for neg_kw in NEGATIVE_KEYWORDS_FOR_RANKING:
                    if neg_kw in title: score -= 3; score_log_details.append(f"flex_neg_kw({neg_kw})_in_title:-3") 
                    if f"/{neg_kw}" in link.lower(): score -= 3; score_log_details.append(f"flex_neg_kw({neg_kw})_in_link:-3") 
                    if neg_kw in snippet: score -= 1; score_log_details.append(f"flex_neg_kw({neg_kw})_in_snippet:-1") 
                
                context_tld = context_keywords_dict.get("location_tld", "")
                # Strong context TLD match (using new PREFERRED_TLDS logic if context_tld is there)
                if context_tld and link_suffix_pass2 == context_tld and domain_name_part_pass2.startswith(normalize_company_name_for_domain_match(company_name).split('&')[0]):
                    score += 10; score_log_details.append(f"flex_strong_ctx_tld({context_tld}):+10")
                elif context_tld and link_suffix_pass2 == context_tld:
                    score += 4; score_log_details.append(f"flex_ctx_tld({context_tld}):+4")
                elif link_suffix_pass2 in PREFERRED_TLDS : # General preferred TLD bonus
                    score += 1; score_log_details.append(f"flex_preferred_tld({link_suffix_pass2}):+1")
                # No penalty for non-preferred TLDs here unless current_dynamic_threshold handles it

                for key_type in ["industry", "location", "generic"]:
                    ctx_kw = context_keywords_dict.get(key_type, "")
                    if ctx_kw:
                        for word in ctx_kw.split():
                            if len(word)>2: # Avoid very short context words
                                if word in snippet: score += 0.5; score_log_details.append(f"flex_ctx_snip({word}):+0.5") # Reduced from 1.0
                                if word in title: score += 0.25; score_log_details.append(f"flex_ctx_title({word}):+0.25") # Reduced from 0.5
            
                if company_embedding_for_pass2 and i < len(candidate_embeddings) and candidate_embeddings[i] and not isinstance(candidate_embeddings[i], Exception):
                    snippet_embedding = candidate_embeddings[i]
                    try:
                        similarity = cosine_similarity(np.array(company_embedding_for_pass2).reshape(1, -1), np.array(snippet_embedding).reshape(1, -1))[0][0]
                        if similarity > 0.60: # Slightly lower threshold for flex pass
                             score += similarity * 2.5 # Slightly lower multiplier
                             score_log_details.append(f"flex_embed_sim:{similarity*2.5:.1f}(raw:{similarity:.2f})")
                    except Exception as e_cos: scoring_logger.warning(f"  L2 Cosine sim error for {link}: {e_cos}")
            
            processed_candidates_scores.append((score, link, current_dynamic_threshold, title, score_log_details))

        except Exception as e:
            scoring_logger.warning(f"  L2 Error processing link {link} for '{company_name}': {type(e).__name__} - {e}")
            continue
            
    if processed_candidates_scores:
        processed_candidates_scores.sort(key=lambda x: x[0], reverse=True)
        for score, link, threshold, title, log_details in processed_candidates_scores:
            scoring_logger.debug(f"  L2 Ranked Candidate: {link} | Title: '{title[:60]}...' | FINAL SCORE: {score:.1f} | Threshold: {threshold} | Factors: {', '.join(log_details)}")
            if score >= threshold:
                scoring_logger.info(f"  >> L2 Selected Link (Flexible) for '{company_name}': {link} (Score: {score:.1f}, Threshold: {threshold})")
                return link
        
        best_score_overall = processed_candidates_scores[0][0]
        best_link_overall = processed_candidates_scores[0][1]
        scoring_logger.info(f"  L2 No link met flexible score threshold for '{company_name}'. Best flexible score: {best_score_overall:.1f} for {best_link_overall}")
    else:
        scoring_logger.info(f"  L2 No candidates processed for flexible scoring for '{company_name}'.")

    # --- END OF RESTORED FLEXIBLE SCORING ---
    scoring_logger.info(f"  >> No link met ANY criteria (Strict L1 or Flexible L2) for '{company_name}' (Prepared: '{prepared_company_name_for_check}').")
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