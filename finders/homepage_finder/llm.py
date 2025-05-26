import aiohttp
from openai import AsyncOpenAI

async def choose_best_wiki_link(company_name: str, candidates: list, openai_api_key: str) -> str | None:
    """
    Selects the most relevant Wikipedia page via LLM.
    
    Args:
        company_name: Company name
        candidates: List of candidates with their snippets and relevance
        openai_api_key: OpenAI API key
        
    Returns:
        str | None: Selected URL or None
    """
    try:
        # Format candidates list with their snippets and relevance
        candidates_text = []
        for idx, candidate in enumerate(candidates, 1):
            candidates_text.append(f"{idx}. URL: {candidate['link']}")
            if 'snippet' in candidate:
                candidates_text.append(f"   Snippet: {candidate['snippet']}")
            if 'relevance_score' in candidate:
                candidates_text.append(f"   Relevance: {candidate['relevance_score']:.2f}")
            candidates_text.append("")

        system_prompt = f"""You are an expert assistant that identifies the single most relevant Wikipedia page for a company.
Company Name: {company_name}

Your task is to analyze the provided list of Wikipedia URLs and their snippets.
Select EXACTLY ONE URL that is most likely to be the main Wikipedia page for this company.
Consider:
1. Relevance scores (higher is better)
2. Snippets content (look for official company information)
3. URL patterns (prefer shorter, cleaner URLs)
4. Company name matches in URL and snippet

Output ONLY the selected URL. No explanations, no other text."""

        user_prompt = f"""Here are the candidate Wikipedia pages for {company_name}:

{chr(10).join(candidates_text)}

Which single URL is the main Wikipedia page for this company?
Answer:"""

        openai_client = AsyncOpenAI(api_key=openai_api_key)
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=150,
            top_p=1.0,
            n=1,
            stop=["\n"]
        )

        selected_url = response.choices[0].message.content.strip()
        return selected_url

    except Exception as e:
        print(f"Error analyzing via LLM: {e}")
        return None

async def choose_best_direct_website(company_name: str, candidates: list, openai_api_key: str) -> str | None:
    """
    Selects the most suitable official company website from Google search results via LLM.
    
    Args:
        company_name: Company name
        candidates: List of candidates with their snippets from Google search
        openai_api_key: OpenAI API key
        
    Returns:
        str | None: Selected URL or None
    """
    try:
        # Format candidates list with their snippets for analysis
        candidates_text = []
        for idx, candidate in enumerate(candidates, 1):
            url = candidate.get('link', '')
            title = candidate.get('title', '')
            snippet = candidate.get('snippet', '')
            
            candidates_text.append(f"{idx}. URL: {url}")
            candidates_text.append(f"   Title: {title}")
            candidates_text.append(f"   Snippet: {snippet}")
            candidates_text.append("")

        system_prompt = f"""You are an expert assistant that identifies the official company website from Google search results.
Company Name: {company_name}

Your task is to analyze the provided list of URLs, titles, and snippets from Google search results.
Select EXACTLY ONE URL that is most likely to be the official company website.
Consider:
1. URL domain - prefer official company domains over third-party sites
2. Title and snippet content - look for official company information
3. Avoid news sites, directories, social media, and third-party platforms
4. Prefer the main company homepage over specific product pages

Output ONLY the selected URL. No explanations, no other text."""

        user_prompt = f"""Here are the candidate websites for {company_name}:

{chr(10).join(candidates_text)}

Which single URL is the official company website?
Answer:"""

        openai_client = AsyncOpenAI(api_key=openai_api_key)
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=150,
            top_p=1.0,
            n=1,
            stop=["\n"]
        )

        selected_url = response.choices[0].message.content.strip()
        return selected_url

    except Exception as e:
        print(f"Error analyzing direct website candidates via LLM: {e}")
        return None 