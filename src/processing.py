from bs4 import BeautifulSoup
import tldextract
import re # For finding copyright or specific patterns
import time
from urllib.parse import urlparse, urljoin
import json # For parsing JSON-LD
import logging
import os

# Настройка логгера
logger = logging.getLogger(__name__)

def validate_page(company_name: str, title: str | None, domain: str | None, html_content: str | None, original_url: str | None = None) -> bool:
    """Validates if the page content is relevant, checking title, domain, content signals, and basic URL structure."""
    logger.debug(f"Starting validation for '{company_name}'...") # DEBUG
    if not html_content and (not title and not domain):
        logger.debug(f"Validation skipped for '{company_name}': Not enough info (no title, domain, or HTML).") # DEBUG
        return False 

    company_name_lower = company_name.lower()
    title_lower = title.lower() if title else ""
    normalized_domain = domain.lower().replace("-", "") if domain else ""
    html_content_lower = html_content.lower() if html_content else ""
    soup = BeautifulSoup(html_content, 'html.parser') if html_content else None

    # 1. Title/Domain basic check (as before)
    if company_name_lower in title_lower: 
        logger.debug(f"Validation PASSED (Check 1a: name '{company_name_lower}' in title '{title_lower[:60]}...') for '{company_name}'") # DEBUG
        return True
    if domain and company_name_lower.replace(" ", "").replace(",", "").replace(".", "") in normalized_domain: 
        logger.debug(f"Validation PASSED (Check 1b: cleaned name in normalized domain '{normalized_domain}') for '{company_name}'") # DEBUG
        return True
    logger.debug(f"Validation FAILED (Check 1: Direct name/domain match) for '{company_name}'") # DEBUG

    # 2. Check for parts of company name in title/domain (as before)
    parts_to_check = []
    parts = [p for p in company_name_lower.split() if len(p) > 2] 
    if parts: parts_to_check = parts
    elif len(company_name_lower) > 2: parts_to_check = [company_name_lower]
    found_part_match = False # DEBUG
    if parts_to_check:
        for part in parts_to_check:
            if (title and part in title_lower) or (domain and part in normalized_domain): 
                logger.debug(f"Validation PASSED (Check 2: part '{part}' in title/domain) for '{company_name}'") # DEBUG
                found_part_match = True # DEBUG
                return True
    if not found_part_match: logger.debug(f"Validation FAILED (Check 2: Part of name match) for '{company_name}'") # DEBUG

    # 3. Meta Description and Keywords Check
    meta_check_passed = False # DEBUG
    if soup:
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        meta_keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
        meta_desc_content = meta_desc_tag.get('content', '').lower() if meta_desc_tag else ""
        meta_keywords_content = meta_keywords_tag.get('content', '').lower() if meta_keywords_tag else ""
        
        meta_positive_signals = ["about", "company", "official", "corporate", "profile", "headquarters", "founded", "investors", "team"]
        name_in_meta = company_name_lower in meta_desc_content or company_name_lower in meta_keywords_content
        signals_in_meta = any(signal in meta_desc_content for signal in meta_positive_signals) or \
                          any(signal in meta_keywords_content for signal in meta_positive_signals)
                          
        if name_in_meta and signals_in_meta:
            logger.debug(f"Validation PASSED (Check 3: Name and positive signal found in meta tags) for '{company_name}'") # DEBUG
            meta_check_passed = True # DEBUG
            return True 
        else:
            logger.debug(f"Validation FAILED (Check 3: Meta tags) for '{company_name}'. Name in meta: {name_in_meta}, Signals in meta: {signals_in_meta}") # DEBUG
    else:
         logger.debug(f"Validation SKIPPED (Check 3: Meta tags) for '{company_name}': No soup object.") # DEBUG

    # 4. Content-based "Company Signals"
    positive_hits = 0 # DEBUG: Initialize outside if
    negative_hits = 0 # DEBUG: Initialize outside if
    if html_content_lower:
        # 4a. Check for presence of company name in body as a basic sanity check
        if company_name_lower not in html_content_lower:
            logger.debug(f"Validation FAILED (Check 4a: company name '{company_name_lower}' not in HTML body) for '{company_name}'") # DEBUG
            return False
        else:
             logger.debug(f"Validation PASSED (Check 4a: company name found in HTML body) for '{company_name}'") # DEBUG

        # 4b. Check content signals
        positive_signals = [
            "about us", "about company", "our company", "mission", "vision", "values",
            "contact us", "contact information", "get in touch", "headquarters",
            "investor relations", "investors", "media room",
            "careers", "jobs", "work with us",
            "privacy policy", "terms of service", "legal notice", "imprint", "terms & conditions",
            "corporate information", "company profile", "founded in"
        ]
        negative_signals = [ # Keywords suggesting it's not a primary corporate page
            "add to cart", "checkout", "shopping cart", "my account", "user login",
            "blog post", "news article", "read more", "comments", "forum", 
            "product details", "item specifics", "product id", "review", "rating", "price list"
        ]
        
        positive_hits = sum(1 for signal in positive_signals if signal in html_content_lower)
        negative_hits = sum(1 for signal in negative_signals if signal in html_content_lower)
        logger.debug(f"Validation Check 4b (Content Signals) for '{company_name}': Positive Hits={positive_hits}, Negative Hits={negative_hits}") # DEBUG
        
        # 4c. Check for company name in first few paragraphs if soup is available
        first_para_check_passed = False # DEBUG
        if soup:
            first_paras = soup.find_all('p', limit=5)
            first_paras_text = " ".join(p.get_text(strip=True).lower() for p in first_paras)
            name_in_first_paras = company_name_lower in first_paras_text
            signals_in_first_paras = any(signal in first_paras_text for signal in ["about", "company", "profile", "founded"])
            
            if name_in_first_paras and positive_hits > 0 and signals_in_first_paras:
                logger.debug(f"Validation PASSED (Check 4c: Name & signal in first paras, positive hits > 0) for '{company_name}'") # DEBUG
                first_para_check_passed = True # DEBUG
                return True
            else:
                 logger.debug(f"Validation FAILED (Check 4c: First paras) for '{company_name}'. Name in paras: {name_in_first_paras}, Signals in paras: {signals_in_first_paras}, Positive hits: {positive_hits}") # DEBUG
        else:
             logger.debug(f"Validation SKIPPED (Check 4c: First paras) for '{company_name}': No soup object.") # DEBUG
        
        # 4d. Check signal thresholds
        if positive_hits >= 2 and negative_hits <= 1: 
            logger.debug(f"Validation PASSED (Check 4d.1: positive_hits >= 2 and negative_hits <= 1) for '{company_name}'") # DEBUG
            return True
        if positive_hits >= 1 and negative_hits == 0: 
             logger.debug(f"Validation PASSED (Check 4d.2: positive_hits >= 1 and negative_hits == 0) for '{company_name}'") # DEBUG
             return True
        logger.debug(f"Validation FAILED (Check 4d: Signal Thresholds) for '{company_name}'. Positive={positive_hits}, Negative={negative_hits}") # DEBUG
        
        # 4e. Copyright check 
        copyright_check_passed = False # DEBUG
        try: # Wrap regex in try-except
            current_year = str(time.gmtime().tm_year)
            prev_year = str(int(current_year) - 1)
            simple_company_name_match = re.escape(company_name_lower.split()[0]) 
            if len(company_name_lower.split()) > 1 : 
                simple_company_name_match += ".*" + re.escape(company_name_lower.split()[-1])
            
            copyright_pattern = rf"(©|\(c\)|copyright)\s*(\d{{4}}|{current_year}|{prev_year})?\s*.*{simple_company_name_match}"
            if re.search(copyright_pattern, html_content_lower, re.IGNORECASE):
                logger.debug(f"Validation PASSED (Check 4e: copyright pattern) for '{company_name}'") # DEBUG
                copyright_check_passed = True # DEBUG
                return True
            else:
                 logger.debug(f"Validation FAILED (Check 4e: copyright pattern not found) for '{company_name}'") # DEBUG
        except Exception as e_re:
             logger.warning(f"Validation Check 4e (Copyright Regex) FAILED with error for '{company_name}': {e_re}") # DEBUG
        if not copyright_check_passed: logger.debug(f"Validation FAILED (Check 4e: Copyright Check) for '{company_name}'") # DEBUG
    else:
        logger.debug(f"Validation SKIPPED (Check 4: Content Signals) for '{company_name}': No html_content_lower.") # DEBUG

    # 5. URL Structure (Negative Signals) - only if original_url is provided ---
    url_structure_check_passed = True # DEBUG: Assume passed unless it fails
    if original_url:
        try:
            parsed_original_url = urlparse(original_url.lower())
            path_lower = parsed_original_url.path
            is_bad_path = path_lower and (path_lower.count('/') > 3 or any(seg in path_lower for seg in ["/blog/", "/news/", "/product/", "/category/", "/article/"]))
            
            # Check if content signals were also weak (condition to actually fail based on URL)
            content_signals_weak = not (positive_hits >=1 and negative_hits == 0)
            
            if is_bad_path and content_signals_weak: 
                logger.debug(f"Validation FAILED (Check 5: URL structure '{path_lower}' is bad AND content signals were weak) for '{company_name}'") # DEBUG
                url_structure_check_passed = False # DEBUG
                return False
            else:
                 logger.debug(f"Validation PASSED (Check 5: URL structure '{path_lower}' ok or content signals strong enough) for '{company_name}'. Bad path: {is_bad_path}, Weak signals: {content_signals_weak}") # DEBUG
        except Exception as e_url:
             logger.warning(f"Validation Check 5 (URL Structure) FAILED with error for '{company_name}': {e_url}") # DEBUG
             # Don't fail validation just because URL parsing failed, rely on content checks
    else:
         logger.debug(f"Validation SKIPPED (Check 5: URL Structure) for '{company_name}': No original_url provided.") # DEBUG

    logger.debug(f"Validation FAILED (All checks completed without returning True) for '{company_name}'") # DEBUG
    return False

def extract_text_for_description(html_content: str | None) -> str | None:
    """Extracts relevant text snippet for description (meta-description, first <p>, or 'About' section)."""
    if not html_content: return None
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'): 
        return meta_desc['content'].strip()
    
    # 2. LinkedIn specific selectors
    linkedin_selectors = [
        'div[data-test-id="about-us__description"]',  # Основное описание компании
        'div[data-test-id="about-us__overview"]',     # Обзор компании
        'div[data-test-id="about-us__mission"]',      # Миссия компании
        'div[data-test-id="about-us__specialties"]',  # Специализация
        'div[data-test-id="about-us__company-size"]', # Размер компании
        'div[data-test-id="about-us__industry"]',     # Отрасль
        'div[data-test-id="about-us__founded"]',      # Год основания
        'div[data-test-id="about-us__headquarters"]'  # Штаб-квартира
    ]
    
    # Собираем все тексты из LinkedIn селекторов
    linkedin_texts = []
    for selector in linkedin_selectors:
        element = soup.select_one(selector)
        if element:
            text = element.get_text(strip=True)
            if text and len(text) > 10:  # Минимальная длина для значимого текста
                linkedin_texts.append(text)
    
    if linkedin_texts:
        return " ".join(linkedin_texts)
        
    # 3. First meaningful paragraph (improved search)
    for selector in ['main p', 'article p', 'div[role="main"] p', 'body > div p', 'body > p']: 
        try:
            first_p = soup.select_one(selector)
            if first_p:
                p_text = first_p.get_text(strip=True)
                if len(p_text) > 50: return p_text # Check length
        except Exception: continue # Ignore errors from invalid selectors
            
    # 4. About section (simplified search)
    for keyword_base in ['about']: # Only English keyword
        elements = soup.find_all(lambda tag: tag.name in ['h1','h2','h3','p','div'] and keyword_base in tag.get_text(strip=True).lower())
        for el in elements:
            parent = el.find_parent(['section', 'div'])
            text_block = ""
            if parent:
                p_tags = parent.find_all('p', limit=3)
                text_block = " ".join(p.get_text(strip=True) for p in p_tags)
            elif el.name == 'p': 
                 text_block = el.get_text(strip=True)
                 
            if len(text_block) > 50: return text_block.strip()
            
    return None # Return None if nothing suitable is found

def extract_definitive_url_from_html(html_content: str, original_url: str) -> str | None:
    """Extracts a definitive (canonical, og:url, or JSON-LD organization) URL from HTML content.
       Validates that the found URL belongs to the same registered domain as the original_url.
    """
    if not html_content or not original_url: return None
    soup = BeautifulSoup(html_content, 'html.parser')
    
    try:
        original_domain_info = tldextract.extract(original_url)
        original_registered_domain = original_domain_info.registered_domain.lower()
    except Exception as e:
        # print(f"Could not parse original_url domain: {original_url} - {e}")
        return None # Cannot validate without original domain

    candidate_urls = []

    # 1. Canonical URL
    canonical_tag = soup.select_one('link[rel=canonical]')
    if canonical_tag and canonical_tag.get('href'):
        candidate_urls.append(canonical_tag.get('href'))

    # 2. OpenGraph URL
    og_url_tag = soup.select_one('meta[property="og:url"]')
    if og_url_tag and og_url_tag.get('content'):
        candidate_urls.append(og_url_tag.get('content'))

    # 3. JSON-LD Organization URL
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            # Handle cases where data is a list of objects or a single object
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get('@type') in ["Organization", "Corporation"] and item.get('url'):
                        candidate_urls.append(item.get('url'))
                        break # Found one, likely the main one
                else: # If inner loop didn't break
                    continue
                break # Broke from inner loop
            elif isinstance(data, dict) and data.get('@type') in ["Organization", "Corporation"] and data.get('url'):
                candidate_urls.append(data.get('url'))
        except json.JSONDecodeError:
            continue # Ignore malformed JSON-LD
        except Exception: # Other potential errors during JSON-LD processing
            continue

    # Validate candidate URLs
    for raw_url in candidate_urls:
        if not raw_url or not isinstance(raw_url, str): continue
        
        # Resolve relative URLs using the original_url as base
        abs_url = urljoin(original_url, raw_url.strip())
        
        try:
            parsed_candidate = urlparse(abs_url)
            candidate_domain_info = tldextract.extract(abs_url)
            candidate_registered_domain = candidate_domain_info.registered_domain.lower()

            # Check if it's a valid HTTP/HTTPS URL and belongs to the same registered domain
            if parsed_candidate.scheme in ['http', 'https'] and candidate_registered_domain == original_registered_domain:
                # print(f"  Definitive URL found and validated: {abs_url} (Original: {original_url})")
                return f"{parsed_candidate.scheme}://{parsed_candidate.netloc}" # Return base URL
        except Exception as e:
            # print(f"  Error validating candidate definitive URL {abs_url}: {e}")
            continue
           
    return None 

def parse_linkedin_about_section_flexible(html_content: str) -> tuple[str | None, str | None]:
    """
    Flexible parsing of LinkedIn about section: works for different languages and structures.
    Returns (description, homepage_url).
    """
    if not html_content:
        logger.info("[LinkedIn Parser] Empty HTML content received")
        return None, None
        
    # Сохраняем HTML в файл для анализа
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    debug_file = f"output/debug/linkedin_html_{timestamp}.html"
    os.makedirs("output/debug", exist_ok=True)
    
    with open(debug_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    logger.info(f"[LinkedIn Parser] Saved raw HTML to {debug_file}")
    
    soup = BeautifulSoup(html_content, 'html.parser')

    # Проверка на страницу логина
    login_indicators = [
        "Sign in to LinkedIn",
        "Войти в LinkedIn",
        "Sign in",
        "Log in",
        "Войти",
        "login-form",
        "sign-in-form",
        "auth-wall"
    ]
    
    for indicator in login_indicators:
        if indicator.lower() in html_content.lower():
            logger.error(f"[LinkedIn Parser] Detected LinkedIn login page! Indicator found: {indicator}")
            logger.error("[LinkedIn Parser] Cannot parse company page - authentication required")
            return None, None

    # 1. Попытка взять данные из JSON-LD
    script_tag = soup.find('script', type='application/ld+json')
    if script_tag:
        try:
            data = json.loads(script_tag.string)
            logger.info(f"[LinkedIn Parser] Found JSON-LD data structure: {list(data.keys()) if isinstance(data, dict) else 'List of objects'}")
            homepage_url = data.get('url')
            if homepage_url and 'linkedin.com' in homepage_url:
                logger.info(f"[LinkedIn Parser] Skipping LinkedIn URL: {homepage_url}")
                homepage_url = None
            description = data.get('description')
            if description or homepage_url:
                logger.info(f"[LinkedIn Parser] Successfully extracted from JSON-LD - Description length: {len(description) if description else 0}, Homepage: {homepage_url}")
                return description, homepage_url
        except Exception as e:
            logger.error(f"[LinkedIn Parser] Failed to parse JSON-LD: {str(e)}")
            pass

    # 2. Многоязычные ключевые слова для about
    about_keywords = [
        "about", "обзор", "présentation", "a propos", "über", "acerca", "会社概要", "informazioni", "tietoja", "om", "소개", "소개글", "소개란"
    ]
    about_keywords = [k.lower() for k in about_keywords]
    logger.debug(f"[LinkedIn Parser] Searching for about sections with keywords: {about_keywords}")

    # 3. Найти секцию, где есть <h2>/<h3> с любым из ключевых слов, либо <dl> с Website/Веб-сайт
    about_section = None
    for section in soup.find_all('section'):
        header = section.find(['h2', 'h3'])
        header_text = header.get_text(strip=True).lower() if header else ""
        if any(kw in header_text for kw in about_keywords):
            logger.info(f"[LinkedIn Parser] Found about section with header: {header_text}")
            about_section = section
            break
        # Структурная эвристика: ищем <dl> с Website
        if section.find('dl'):
            dt_texts = [dt.get_text(strip=True).lower() for dt in section.find_all('dt')]
            if any("website" in t or "веб-сайт" in t for t in dt_texts):
                logger.info(f"[LinkedIn Parser] Found about section with website in dt: {dt_texts}")
                about_section = section
                break

    description = None
    homepage_url = None

    if about_section:
        logger.info("[LinkedIn Parser] Processing found about section...")
        # Описание — первый длинный <p>
        desc_p = None
        for p in about_section.find_all('p'):
            text = p.get_text(strip=True)
            if len(text) > 80:
                desc_p = p
                logger.info(f"[LinkedIn Parser] Found description paragraph (first 100 chars): {text[:100]}...")
                break
        if desc_p:
            description = desc_p.get_text(strip=True)

        # Сайт — ищем <dt>/<dd> с Website/Веб-сайт
        for dt in about_section.find_all('dt'):
            dt_text = dt.get_text(strip=True).lower()
            if "website" in dt_text or "веб-сайт" in dt_text:
                dd = dt.find_next_sibling('dd')
                if dd:
                    a = dd.find('a', href=True)
                    if a and a['href'].startswith('http') and 'linkedin.com' not in a['href']:
                        homepage_url = a['href']
                        logger.info(f"[LinkedIn Parser] Found homepage URL in dt/dd: {homepage_url}")
                        break
        # Fallback: ищем первую внешнюю ссылку в about_section
        if not homepage_url:
            for a in about_section.find_all('a', href=True):
                href = a['href']
                if href.startswith('http') and 'linkedin.com' not in href:
                    homepage_url = href
                    logger.info(f"[LinkedIn Parser] Found homepage URL in fallback: {homepage_url}")
                    break

    # Fallback: если не нашли секцию, ищем первый длинный <p> на странице
    if not description:
        logger.info("[LinkedIn Parser] No about section found, trying to find first long paragraph...")
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            if len(text) > 100:
                description = text
                logger.info(f"[LinkedIn Parser] Found description in fallback paragraph (first 100 chars): {text[:100]}...")
                break

    # Last fallback: если ничего не нашли, возвращаем весь текст страницы
    if not description:
        logger.info("[LinkedIn Parser] No suitable paragraphs found, using full page text as fallback...")
        all_text = soup.get_text(separator=' ', strip=True)
        if all_text:
            description = all_text[:4000]
            logger.info(f"[LinkedIn Parser] Using full page text as fallback (length: {len(description)})")

    logger.info(f"[LinkedIn Parser] Final result - Description length: {len(description) if description else 0}, Homepage: {homepage_url}")
    return description, homepage_url 