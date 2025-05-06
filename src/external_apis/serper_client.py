import aiohttp
import asyncio
import json

async def find_urls_with_serper_async(session: aiohttp.ClientSession, company_name: str, context_text: str | None, serper_api_key: str | None) -> tuple[str | None, str | None]:
    """Async: Finds homepage and LinkedIn URL using Serper.dev via aiohttp."""
    if not serper_api_key: 
        print(f"SERPER_API_KEY missing for {company_name}, skipping Serper search.")
        return None, None
        
    homepage_url, linkedin_url = None, None
    serper_search_url = "https://google.serper.dev/search"
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    
    context_query_part = f" {context_text}" if context_text else ""
    if len(context_query_part) > 100: context_query_part = context_query_part[:100] + "..."

    try:
        # Find homepage
        search_query_homepage = f'{company_name}{context_query_part} official website'
        payload_homepage = json.dumps({"q": search_query_homepage, "num": 3})
        async with session.post(serper_search_url, headers=headers, data=payload_homepage, timeout=15) as resp_hp:
            if resp_hp.status == 200:
                results = await resp_hp.json()
                if results.get("organic"): homepage_url = results["organic"][0].get("link")
            # else: print(f"Serper HP failed {company_name}: {resp_hp.status}") # Reduce noise

        await asyncio.sleep(0.3) # Short sleep between calls
        
        # Find LinkedIn URL
        search_query_linkedin = f'{company_name}{context_query_part} site:linkedin.com/company'
        payload_linkedin = json.dumps({"q": search_query_linkedin, "num": 3})
        async with session.post(serper_search_url, headers=headers, data=payload_linkedin, timeout=15) as resp_li:
             if resp_li.status == 200:
                results = await resp_li.json()
                if results.get("organic"):
                    for res in results["organic"]:
                        link = res.get("link")
                        if link and "linkedin.com/company/" in link: linkedin_url = link; break
             # else: print(f"Serper LI failed {company_name}: {resp_li.status}") # Reduce noise
             
    except asyncio.TimeoutError: print(f"Timeout Serper search {company_name}")
    except aiohttp.ClientError as e: print(f"AIOHttp Serper error {company_name}: {e}")
    except Exception as e: print(f"Generic Serper error {company_name}: {type(e).__name__}")
    
    # print(f"Serper results for {company_name}: HP={homepage_url}, LI={linkedin_url}") # Optional debug
    return homepage_url, linkedin_url 