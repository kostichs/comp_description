from bs4 import BeautifulSoup
import tldextract

def validate_page(company_name: str, title: str | None, domain: str | None) -> bool:
    """Validates if the page content (title or domain) is relevant to the company."""
    if not title and not domain: return False
    company_name_lower = company_name.lower()
    normalized_domain = domain.lower().replace("-", "") if domain else ""
    title_lower = title.lower() if title else ""
    
    # Simple checks first
    if company_name_lower in title_lower: return True
    if domain and company_name_lower.replace(" ", "").replace(",", "").replace(".", "") in normalized_domain: return True
    
    # Prepare parts for check if simple checks failed
    parts_to_check = []
    parts = [p for p in company_name_lower.split() if len(p) > 2] 
    if parts: parts_to_check = parts
    elif len(company_name_lower) > 2: parts_to_check = [company_name_lower]
        
    # Iterate through parts if we have any valid ones
    if parts_to_check:
        for part in parts_to_check:
            title_match = title and part in title_lower
            domain_match = domain and part in normalized_domain
            if title_match or domain_match: return True
            
    # If no checks passed
    return False

def extract_text_for_description(html_content: str | None) -> str | None:
    """Extracts relevant text snippet for description (meta-description, first <p>, or 'About' section)."""
    if not html_content: return None
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'): 
        # Basic check to avoid short/generic meta descriptions if needed
        # if len(meta_desc['content'].strip()) > 30: 
        return meta_desc['content'].strip()
        
    # 2. First meaningful paragraph (improved search)
    for selector in ['main p', 'article p', 'div[role="main"] p', 'body > div p', 'body > p']: 
        try:
            first_p = soup.select_one(selector)
            if first_p:
                p_text = first_p.get_text(strip=True)
                if len(p_text) > 50: return p_text # Check length
        except Exception: continue # Ignore errors from invalid selectors
            
    # 3. About section (simplified search)
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