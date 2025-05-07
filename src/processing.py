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
    if not html_content and (not title and not domain):
        # print(f"Validation skipped for {company_name}: Not enough info (no title, domain, or HTML).")
        return False 

    company_name_lower = company_name.lower()
    title_lower = title.lower() if title else ""
    normalized_domain = domain.lower().replace("-", "") if domain else ""
    html_content_lower = html_content.lower() if html_content else ""
    soup = BeautifulSoup(html_content, 'html.parser') if html_content else None

    # 1. Title/Domain basic check (as before)
    if company_name_lower in title_lower: 
        # print(f"Validation PASSED (name in title) for {company_name}")
        return True
    if domain and company_name_lower.replace(" ", "").replace(",", "").replace(".", "") in normalized_domain: 
        # print(f"Validation PASSED (name in domain) for {company_name}")
        return True

    # 2. Check for parts of company name in title/domain (as before)
    parts_to_check = []
    parts = [p for p in company_name_lower.split() if len(p) > 2] 
    if parts: parts_to_check = parts
    elif len(company_name_lower) > 2: parts_to_check = [company_name_lower]
    if parts_to_check:
        for part in parts_to_check:
            if (title and part in title_lower) or (domain and part in normalized_domain): 
                # print(f"Validation PASSED (part '{part}' in title/domain) for {company_name}")
                return True

    # 2. Meta Description and Keywords Check
    if soup:
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        meta_keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
        meta_desc_content = meta_desc_tag.get('content', '').lower() if meta_desc_tag else ""
        meta_keywords_content = meta_keywords_tag.get('content', '').lower() if meta_keywords_tag else ""
        
        meta_positive_signals = ["about", "company", "official", "corporate", "profile", "headquarters", "founded", "investors", "team"]
        if company_name_lower in meta_desc_content or company_name_lower in meta_keywords_content:
            if any(signal in meta_desc_content for signal in meta_positive_signals) or \
               any(signal in meta_keywords_content for signal in meta_positive_signals):
                return True 

    # 3. Content-based "Company Signals"
    if html_content_lower:
        # Positive signals (more likely to be a corporate/about page)
        positive_signals = [
            "about us", "about company", "our company", "mission", "vision", "values",
            "contact us", "contact information", "get in touch", "headquarters",
            "investor relations", "investors", "media room",
            "careers", "jobs", "work with us",
            "privacy policy", "terms of service", "legal notice", "imprint", "terms & conditions",
            "corporate information", "company profile", "founded in"
        ]
        # Negative signals (more likely to be a product, blog, or irrelevant page)
        negative_signals = [ # Keywords suggesting it's not a primary corporate page
            "add to cart", "checkout", "shopping cart", "my account", "user login",
            "blog post", "news article", "read more", "comments", "forum", 
            "product details", "item specifics", "product id", "review", "rating", "price list"
        ]
        
        # Check for presence of company name in body as a basic sanity check
        if company_name_lower not in html_content_lower:
            # print(f"Validation FAILED (company name not in HTML body) for {company_name}")
            return False

        # Check for at least one strong positive signal
        positive_hits = sum(1 for signal in positive_signals if signal in html_content_lower)
        
        # Check if there are overwhelming negative signals (e.g., multiple e-commerce terms)
        # This is a simple count, could be more sophisticated
        negative_hits = sum(1 for signal in negative_signals if signal in html_content_lower)
        
        # Check for company name in first few paragraphs if soup is available
        if soup:
            first_paras = soup.find_all('p', limit=5)
            first_paras_text = " ".join(p.get_text(strip=True).lower() for p in first_paras)
            if company_name_lower in first_paras_text and positive_hits > 0:
                if any(signal in first_paras_text for signal in ["about", "company", "profile", "founded"]):
                    return True
        
        if positive_hits >= 2 and negative_hits <= 1: # Allow for maybe one negative signal if strong positive exists
            # print(f"Validation PASSED (content signals) for {company_name}")
            return True
        
        if positive_hits >= 1 and negative_hits == 0: return True
        
        # Copyright check (more specific)
        # This regex looks for © or (c) followed by a year (optional) and then the company name (flexible spacing)
        # It's a basic example and might need refinement for different company name formats.
        current_year = str(time.gmtime().tm_year)
        prev_year = str(int(current_year) - 1)
        # Simpler company name for regex to avoid issues with special chars if not escaped properly
        simple_company_name_match = re.escape(company_name_lower.split()[0]) # Match first word of company
        if len(company_name_lower.split()) > 1 : 
            simple_company_name_match += ".*" + re.escape(company_name_lower.split()[-1]) # and last word
        
        copyright_pattern = rf"(©|\(c\)|copyright)\s*(\d{{4}}|{current_year}|{prev_year})?\s*.*{simple_company_name_match}"
        if re.search(copyright_pattern, html_content_lower, re.IGNORECASE):
            # print(f"Validation PASSED (copyright pattern) for {company_name}")
            return True

    # --- URL Structure (Negative Signals) - only if original_url is provided ---
    if original_url:
        parsed_original_url = urlparse(original_url.lower())
        path_lower = parsed_original_url.path
        # Check if path is very long (many segments) or contains typical non-corporate patterns
        if path_lower and (path_lower.count('/') > 3 or any(seg in path_lower for seg in ["/blog/", "/news/", "/product/", "/category/", "/article/"])):
            if not (positive_hits >=1 and negative_hits == 0): # Only fail if content signals are also weak
                # print(f"Validation FAILED (URL structure negative signal: {original_url}) for {company_name}")
                return False

    # print(f"Validation FAILED (all checks) for {company_name}") # Reduce noise for final log
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