import json
import aiohttp
from urllib.parse import urlparse

async def search_google(company_name: str, session: aiohttp.ClientSession, serper_api_key: str) -> dict | None:
    """
    Performs search through Google Serper API.
    
    Args:
        company_name: Company name
        session: aiohttp.ClientSession for HTTP requests
        serper_api_key: API key for Serper
        
    Returns:
        dict | None: Search results or None in case of error
    """
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    # Clean company name for better search results
    # Remove common juridical suffixes that might confuse search
    clean_name = company_name
    juridical_suffixes = [
        "Co., Ltd.", "Co., LTD.", ", Ltd.", ", LTD.", ", Inc.", ", LLC", 
        ", Corp.", ", Corporation", "GmbH", "S.A.", "UAB", "OOO", 
        "Pty Ltd", "Pvt Ltd", "Limited", "Incorporated"
    ]
    
    for suffix in juridical_suffixes:
        if clean_name.endswith(suffix):
            clean_name = clean_name[:-len(suffix)].strip()
            break
    
    # Use both original and cleaned name in search for better coverage
    search_query = f"company \"{company_name}\" OR \"{clean_name}\" official website homepage"
    
    payload = json.dumps({
        "q": search_query,
        "num": 10,
        "gl": "us",
        "hl": "en"
    })
    
    try:
        async with session.post("https://google.serper.dev/search", headers=headers, data=payload) as response:
            if response.status == 200:
                return await response.json()
            else:
                print(f"Error requesting Serper API: {response.status}")
                return None
    except Exception as e:
        print(f"Error requesting Serper API: {e}")
        return None

def calculate_relevance_score(company_name: str, wiki_url: str) -> float:
    """
    Calculates relevance score of Wikipedia page for company.
    
    Args:
        company_name: Company name
        wiki_url: Wikipedia page URL
        
    Returns:
        float: Relevance score (higher is better)
    """
    from urllib.parse import unquote
    
    # Get page name from URL
    path = urlparse(wiki_url).path
    if '/wiki/' not in path:
        return 0
    page_name = unquote(path.split('/wiki/')[-1])
    
    # Convert to lowercase and normalize separators
    company_name = company_name.lower()
    page_name = page_name.lower().replace('_', ' ')
    
    # Split into words
    company_words = company_name.split()
    page_words = page_name.split()
    
    # If first word doesn't match - return 0 immediately
    if not page_words or company_words[0] != page_words[0]:
        return 0
    
    # Count points for word matches in correct order
    score = 0
    i = 0  # index in company_words
    j = 0  # index in page_words
    
    while i < len(company_words) and j < len(page_words):
        if company_words[i] == page_words[j]:
            score += 1
            i += 1
            j += 1
        else:
            j += 1
    
    # Penalty for extra words
    if j < len(page_words):
        score -= 0.5 * (len(page_words) - j)
    
    return max(0, score)  # Don't allow negative scores

def filter_wikipedia_links(results: list, company_name: str) -> list:
    """
    Filters search results, keeping only Wikipedia links and evaluating their relevance.
    
    Args:
        results: List of search results
        company_name: Company name
        
    Returns:
        list: Filtered results with relevance scores
    """
    wiki_links = []
    for result in results:
        url = result.get('link', '')
        parsed_url = urlparse(url)
        if 'wikipedia.org' in parsed_url.netloc and '/wiki/' in parsed_url.path:
            # Add relevance score to result
            result['relevance_score'] = calculate_relevance_score(company_name, url)
            wiki_links.append(result)
    
    # Sort by relevance score in descending order
    return sorted(wiki_links, key=lambda x: x.get('relevance_score', 0), reverse=True) 