from bs4 import BeautifulSoup
import tldextract
import re # For finding copyright or specific patterns
import time
from urllib.parse import urlparse, urljoin
import json # For parsing JSON-LD
import logging
import os
import asyncio # Added for async function
import aiohttp # Added for async HTTP requests
from scrapingbee import ScrapingBeeClient
# Assuming scrape_page_data_async is correctly imported and handles the client passed from pipeline.py
from .external_apis.scrapingbee_client import scrape_page_data_async 

# Настройка логгера
logger = logging.getLogger(__name__)

def validate_page(company_name: str, title: str | None, domain: str | None, html_content: str | None, original_url: str | None = None) -> bool:
    """Validates if the page content is relevant, checking title, domain, content signals, and basic URL structure."""
    logger.debug(f"Starting validation for '{company_name}'...") # DEBUG
    if not html_content and (not title and not domain):
        logger.debug(f"Validation skipped for '{company_name}': Not enough info (no title, domain, or HTML).") # DEBUG
        return False 

    company_name_lower = company_name.lower()
    # --- Start: Clean company name for validation --- 
    clean_company_name_for_check = re.sub(r'\s*\(.*\)', '', company_name_lower).strip() # Corrected regex
    common_suffixes_to_remove = [
        ', inc.', ' inc.', ', llc', ' llc', ', ltd.', ' ltd.', ' ltd', ', gmbh', ' gmbh',
        ', s.a.', ' s.a.', ' plc', ' se', ' ag', ' oyj', ' ab', ' as', ' nv', ' bv', ' co.', ' co',
        ' corporation', ' company', ' group', ' holding', ' solutions', ' services',
        ' technologies', ' systems', ' international', ' limited' # Add more if needed
    ]
    temp_name = clean_company_name_for_check # Use a temp var for suffix stripping
    for suffix in common_suffixes_to_remove:
        if temp_name.endswith(suffix):
            temp_name = temp_name[:-len(suffix)].strip()
    clean_company_name_for_check = temp_name # Assign back after all suffixes checked
    logger.debug(f"Cleaned company name for validation checks: '{clean_company_name_for_check}'")
    # --- End: Clean company name for validation --- 

    title_lower = title.lower() if title else ""
    normalized_domain_from_tld = tldextract.extract(original_url if original_url else "").registered_domain.lower().replace("-","")
    # Use domain if provided, otherwise derive from original_url for better consistency
    # Fallback to the passed 'domain' if original_url is not available or tldextract fails for it
    normalized_domain = normalized_domain_from_tld if normalized_domain_from_tld else (domain.lower().replace("-", "") if domain else "")

    html_content_lower = html_content.lower() if html_content else ""
    soup = BeautifulSoup(html_content, 'html.parser') if html_content else None

    # 1. Title/Domain basic check (using cleaned name)
    if clean_company_name_for_check and clean_company_name_for_check in title_lower: 
        logger.debug(f"Validation PASSED (Check 1a: cleaned name '{clean_company_name_for_check}' in title '{title_lower[:60]}...') for '{company_name}'")
        return True
    
    # Prepare a version of cleaned name without spaces for domain matching
    cleaned_name_no_spaces = clean_company_name_for_check.replace(" ", "").replace(",", "").replace(".", "")
    if domain and cleaned_name_no_spaces and cleaned_name_no_spaces in normalized_domain: 
        logger.debug(f"Validation PASSED (Check 1b: cleaned name (no spaces) '{cleaned_name_no_spaces}' in normalized domain '{normalized_domain}') for '{company_name}'")
        return True
    logger.debug(f"Validation FAILED (Check 1: Direct cleaned name '{clean_company_name_for_check}' or '{cleaned_name_no_spaces}' not in title/domain) for '{company_name}'")

    # 2. Check for parts of cleaned company name in title/domain
    parts_to_check = []
    if clean_company_name_for_check:
        parts = [p for p in clean_company_name_for_check.split() if len(p) > 2] 
        if parts: parts_to_check = parts
        elif len(clean_company_name_for_check) > 2: parts_to_check = [clean_company_name_for_check]
    
    found_part_match = False
    if parts_to_check:
        for part in parts_to_check:
            if (title and part in title_lower) or (domain and part in normalized_domain): 
                logger.debug(f"Validation PASSED (Check 2: part '{part}' of cleaned name in title/domain) for '{company_name}'")
                found_part_match = True
                return True
    if not found_part_match: logger.debug(f"Validation FAILED (Check 2: Part of cleaned name match for '{company_name}'; Parts checked: {parts_to_check})")

    # 3. Meta Description and Keywords Check (using cleaned name)
    if soup:
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        meta_keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
        meta_desc_content = meta_desc_tag.get('content', '').lower() if meta_desc_tag else ""
        meta_keywords_content = meta_keywords_tag.get('content', '').lower() if meta_keywords_tag else ""
        
        meta_positive_signals = ["about", "company", "official", "corporate", "profile", "headquarters", "founded", "investors", "team"]
        name_in_meta = clean_company_name_for_check and (clean_company_name_for_check in meta_desc_content or clean_company_name_for_check in meta_keywords_content)
        signals_in_meta = any(signal in meta_desc_content for signal in meta_positive_signals) or \
                          any(signal in meta_keywords_content for signal in meta_positive_signals)
                          
        if name_in_meta and signals_in_meta:
            logger.debug(f"Validation PASSED (Check 3: Cleaned name and positive signal found in meta tags) for '{company_name}'")
            return True 
        else:
            logger.debug(f"Validation FAILED (Check 3: Meta tags) for '{company_name}'. Cleaned Name '{clean_company_name_for_check}' in meta: {name_in_meta}, Signals in meta: {signals_in_meta}")
    else:
         logger.debug(f"Validation SKIPPED (Check 3: Meta tags) for '{company_name}': No soup object.")

    # 4. Content-based "Company Signals"
    positive_hits = 0 
    negative_hits = 0 
    if html_content_lower:
        # 4a. Check for presence of *cleaned* company name in body
        if clean_company_name_for_check and clean_company_name_for_check not in html_content_lower:
            # If even the cleaned name isn't there, it's a strong negative signal unless other checks pass
            logger.debug(f"Validation NOTE (Check 4a: cleaned company name '{clean_company_name_for_check}' not in HTML body) for '{company_name}'. Will rely on other signals.")
            # Not returning False immediately, to give other content signals a chance, but this is a weak sign.
        elif clean_company_name_for_check:
             logger.debug(f"Validation Info (Check 4a: cleaned company name '{clean_company_name_for_check}' found in HTML body) for '{company_name}'")
        
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
            name_in_first_paras = clean_company_name_for_check in first_paras_text
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
            simple_company_name_match = re.escape(clean_company_name_for_check.split()[0]) 
            if len(clean_company_name_for_check.split()) > 1 : 
                simple_company_name_match += ".*" + re.escape(clean_company_name_for_check.split()[-1])
            
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
            
    # 4. About section (improved search with multiple languages)
    about_section_keywords = [
        # English
        "about us", "about company", "our company", "who we are", "company profile", "about",
        # German
        "über uns", "unternehmen", "profil", "wir über uns", "firma",
        # French
        "à propos", "a propos", "société", "entreprise", "qui sommes nous", "notre entreprise",
        # Spanish
        "acerca de", "sobre nosotros", "empresa", "compañía", "quienes somos", "perfil",
        # Italian
        "chi siamo", "su di noi", "azienda", "profilo", "la nostra azienda",
        # Portuguese
        "sobre nós", "a empresa", "quem somos", "perfil",
        # Polish
        "o nas", "o firmie", "firma", "profil firmy",
        # Dutch
        "over ons", "bedrijfsprofiel", "ons bedrijf",
        # Nordic (Swedish, Norwegian, Danish)
        "om oss", "om os", "företaget", "virksomheden", "firma profil",
        # Russian
        "о нас", "о компании", "компания", "профиль", "о фирме",
        # Arabic (Common terms - exact match might be tricky)
        "نبذة عنا", "عن الشركة", "معلومات عنا", "من نحن",
        # Chinese (Simplified & Traditional)
        "关于我们", "公司简介", "關於我們", "公司簡介",
        # Japanese
        "会社概要", "私たちについて", "企業情報",
        # Korean
        "회사 소개", "소개", "기업 정보",
        # Hindi
        "हमारे बारे में", "कंपनी प्रोफाइल", "कंपनी के बारे में",
        # Turkish
        "hakkımızda", "şirket profili", "firma hakkında",
        # Indonesian / Malay
        "tentang kami", "profil syarikat", "mengenai kami",
        # Add more languages/variants as needed
    ]
    about_section_keywords = [k.lower() for k in about_section_keywords] # Ensure all are lowercase
    found_about_section = False # Flag to stop searching once a good section is found
    logger.debug(f"[Description Extractor] Searching for About section with {len(about_section_keywords)} keywords...") # DEBUG
    
    # Search in common semantic elements first
    for section_tag_name in ['section', 'article', 'aside', 'div[role="region"]', 'div[class*="about"]' , 'div[id*="about"]', 'div[class*="company"]' , 'div[id*="company"]']:
        for potential_section in soup.select(section_tag_name): 
            section_text_lower = potential_section.get_text(strip=True).lower()
            # Check for keywords in the whole section text OR in specific headers within the section
            header = potential_section.find(['h1', 'h2', 'h3'])
            header_text_lower = header.get_text(strip=True).lower() if header else ""
            
            # Use a flag to avoid redundant logging if keyword found in both header and section text
            keyword_found = False
            if any(keyword in header_text_lower for keyword in about_section_keywords):
                keyword_found = True
            elif any(keyword in section_text_lower for keyword in about_section_keywords):
                 keyword_found = True
                 
            if keyword_found:
                logger.debug(f"[Description Extractor] Found potential About section in <{potential_section.name}> (Header: '{header_text_lower[:50]}...'). Checking content...") # DEBUG
                # Try to get paragraph text from this section
                p_tags = potential_section.find_all('p', limit=5) # Look for paragraphs within the found section
                text_block = " ".join(p.get_text(strip=True) for p in p_tags if p.get_text(strip=True))
                
                if len(text_block) > 50:
                    logger.info(f"[Description Extractor] Found About section text (length {len(text_block)}): '{text_block[:100]}...'")
                    # Set flag to true and break outer loop after returning
                    found_about_section = True 
                    return text_block.strip()
                else:
                    logger.debug(f"[Description Extractor] Potential section found, but paragraph text is too short or missing (Length: {len(text_block)}).") # DEBUG
            
        if found_about_section: break # Break outer loop if a good section was found and processed

    # If no specific section found, fall back to the first paragraph logic (already implemented above)
    if not found_about_section:
      logger.debug("[Description Extractor] No specific About section found or extracted text was too short. Relies on previous first-paragraph check.") # DEBUG
            
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

async def find_and_scrape_about_page_async(
    main_page_html: str,
    main_page_url: str,
    session: aiohttp.ClientSession, 
    sb_client: ScrapingBeeClient, # Changed parameter name to match usage in pipeline
    logger_obj: logging.Logger 
) -> str | None:
    """
    Parses the main page HTML to find a link to an "About Us" page,
    then tries to scrape that page first with aiohttp, then with ScrapingBee.
    Returns the extracted text from the "About Us" page, or None.
    """
    logger_obj.info(f"[About Page Finder] Starting to find 'About Us' link on {main_page_url}")
    if not main_page_html or not main_page_url:
        logger_obj.warning("[About Page Finder] Missing main_page_html or main_page_url.")
        return None

    soup = BeautifulSoup(main_page_html, 'html.parser')
    
    about_link_keywords = [
        # English
        "about", "company", "profile", "who we are", "about us", "corporate", "overview", "whois",
        # German
        "über uns", "unternehmen", "profil", "wir über uns", "firma", "ueber uns", "impressum",
        # French
        "à propos", "a propos", "société", "entreprise", "qui sommes nous", "notre entreprise", "mentions légales",
        # Spanish
        "acerca de", "sobre nosotros", "empresa", "compañía", "quienes somos", "perfil", "nosotros", "aviso legal",
        # Italian
        "chi siamo", "su di noi", "azienda", "profilo", "la nostra azienda", "note legali",
        # Portuguese
        "sobre nós", "a empresa", "quem somos", "perfil", "aviso legal",
        # Polish
        "o nas", "o firmie", "firma", "profil firmy", "nota prawna",
        # Dutch
        "over ons", "bedrijfsprofiel", "ons bedrijf", "colofon",
        # Nordic (Swedish, Norwegian, Danish)
        "om oss", "om os", "företaget", "virksomheden", "firma profil",
        # Russian
        "о нас", "о компании", "компания", "профиль", "о фирме", "контакты",
        # Arabic
        "نبذة عنا", "عن الشركة", "معلومات عنا", "من نحن", "لمحة عنا",
        # Chinese (Simplified & Traditional)
        "关于我们", "公司简介", "關於我們", "公司簡介", "公司信息", "联系我们", "聯繫我們",
        # Japanese
        "会社概要", "私たちについて", "企業情報", "お問い合わせ", "会社案内",
        # Korean
        "회사 소개", "소개", "기업 정보", "연락처", "회사 안내",
        # Hindi
        "हमारे बारे में", "कंपनी प्रोफाइल", "कंपनी के बारे में", "संपर्क करें",
        # Turkish
        "hakkımızda", "şirket profili", "firma hakkında", "iletişim",
        # Indonesian / Malay
        "tentang kami", "profil syarikat", "mengenai kami", "hubungi kami"
    ]
    about_link_keywords = [k.lower() for k in about_link_keywords]

    potential_links = []
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href'].strip()
        link_text = a_tag.get_text(strip=True).lower()
        
        if not href or href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:') or href.startswith('javascript:'):
            continue

        for keyword in about_link_keywords:
            if keyword in link_text or keyword in href.lower():
                abs_url = urljoin(main_page_url, href)
                parsed_abs_url = urlparse(abs_url)
                if not parsed_abs_url.scheme or not parsed_abs_url.netloc:
                    continue

                score = 0
                path_lower = parsed_abs_url.path.lower()
                
                if any(k in path_lower for k in ["about", "company", "profil", "ueber", "propos", "acerca", "sobre", "chi-siamo", "o-nas"]):
                     score += 20
                elif any(k in path_lower for k in about_link_keywords):
                     score += 5
                
                if any(k in link_text for k in ["about", "company", "profil", "ueber", "propos", "acerca", "sobre"]): score += 15
                elif any(k in link_text for k in about_link_keywords): score += 5
                    
                if len(path_lower.split('/')) < 4: score += 10
                if not parsed_abs_url.query: score += 5
                if 'contact' in path_lower or 'kontakt' in path_lower: score -= 5
                
                if abs_url.rstrip('/') == main_page_url.rstrip('/') or _is_external_social_media(abs_url):
                    continue
                
                if score > 0:
                    potential_links.append((abs_url, score))
                    logger_obj.debug(f"[About Page Finder] Potential 'About Us' link: {abs_url} (Text: '{link_text[:50]}...', Score: {score})")
                break 

    if not potential_links:
        logger_obj.info(f"[About Page Finder] No potential 'About Us' links found on {main_page_url}.")
        return None

    potential_links.sort(key=lambda x: x[1], reverse=True)
    logger_obj.debug(f"[About Page Finder] Sorted potential links: {potential_links[:5]}")
    
    best_about_url = potential_links[0][0]
    logger_obj.info(f"[About Page Finder] Best 'About Us' link candidate: {best_about_url} (Score: {potential_links[0][1]}) (Used from {len(potential_links)} candidates)")

    about_page_html_content = None
    try:
        logger_obj.info(f"[About Page Finder] Attempting to fetch '{best_about_url}' with aiohttp...")
        aio_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        async with session.get(best_about_url, timeout=aiohttp.ClientTimeout(total=20), headers=aio_headers, ssl=False) as response:
            if response.status == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                if 'html' in content_type:
                    about_page_html_content = await response.text()
                    logger_obj.info(f"[About Page Finder] Successfully fetched HTML from '{best_about_url}' with aiohttp (Length: {len(about_page_html_content)}).")
                else:
                    logger_obj.warning(f"[About Page Finder] Fetched content from '{best_about_url}' with aiohttp, but content-type is not HTML: {content_type}.")
            else:
                logger_obj.warning(f"[About Page Finder] aiohttp GET request for '{best_about_url}' failed with status: {response.status}.")
    except asyncio.TimeoutError:
        logger_obj.warning(f"[About Page Finder] Timeout fetching '{best_about_url}' with aiohttp.")
    except aiohttp.ClientError as e:
        logger_obj.warning(f"[About Page Finder] aiohttp ClientError for '{best_about_url}': {e}")
    except Exception as e:
        logger_obj.error(f"[About Page Finder] Generic error fetching '{best_about_url}' with aiohttp: {type(e).__name__} - {e}")

    if not about_page_html_content and sb_client: # Corrected: use sb_client passed from pipeline
        logger_obj.warning(f"[About Page Finder] aiohttp failed for '{best_about_url}'. Falling back to ScrapingBee.")
        try:
            # Call the imported async wrapper from scrapingbee_client.py
            about_page_sb_data = await scrape_page_data_async(best_about_url, sb_client)
            if about_page_sb_data and about_page_sb_data[2]:
                about_page_html_content = about_page_sb_data[2]
                logger_obj.info(f"[About Page Finder] Successfully fetched HTML from '{best_about_url}' with ScrapingBee (Length: {len(about_page_html_content)}).")
            else:
                 logger_obj.warning(f"[About Page Finder] ScrapingBee fetch for '{best_about_url}' did not return HTML.")
        except Exception as e_sb:
            logger_obj.error(f"[About Page Finder] Error fetching '{best_about_url}' with ScrapingBee: {type(e_sb).__name__} - {e_sb}")
    
    if about_page_html_content:
        extracted_text = extract_text_for_description(about_page_html_content)
        
        if extracted_text and len(extracted_text) > 100:
            logger_obj.info(f"[About Page Finder] Successfully extracted text (length {len(extracted_text)}) from '{best_about_url}' using extract_text_for_description: '{extracted_text[:200]}...'")
            return extracted_text
        else:
            logger_obj.warning(f"[About Page Finder] Extracted text from '{best_about_url}' using extract_text_for_description was too short (length {len(extracted_text) if extracted_text else 0}) or empty. Attempting generic paragraph extraction.")
            about_soup = BeautifulSoup(about_page_html_content, 'html.parser')
            text_elements = []
            for p_tag in about_soup.find_all('p'):
                p_text = p_tag.get_text(separator=' ', strip=True)
                if len(p_text.split()) > 10:
                    text_elements.append(p_text)
            generic_extracted_text = " ".join(text_elements).strip()
            if generic_extracted_text and len(generic_extracted_text) > 100:
                logger_obj.info(f"[About Page Finder] Successfully extracted generic paragraph text (length {len(generic_extracted_text)}) from '{best_about_url}': '{generic_extracted_text[:200]}...'")
                return generic_extracted_text
            else:
                logger_obj.warning(f"[About Page Finder] Generic paragraph extraction from '{best_about_url}' also yielded short/empty text.")
            
    logger_obj.warning(f"[About Page Finder] Could not retrieve and extract meaningful text from 'About Us' page: {best_about_url}")
    return None

def _is_external_social_media(url_string: str) -> bool:
    try:
        domain = tldextract.extract(url_string).registered_domain.lower()
        social_media_domains = [
            "linkedin.com", "facebook.com", "twitter.com", "instagram.com", "youtube.com",
            "pinterest.com", "tumblr.com", "reddit.com", "vk.com", "ok.ru", "medium.com",
            "slideshare.net", "telegram.org", "whatsapp.com", "tiktok.com", "snapchat.com",
            "xing.com", "weibo.com", "qq.com"
        ]
        return domain in social_media_domains
    except Exception:
        return False 