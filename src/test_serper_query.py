import aiohttp
import asyncio
from external_apis.serper_client import _execute_serper_query

async def test_serper_query(company_name: str, serper_api_key: str) -> None:
    """Test function to fetch and print 10 Google search results using Serper API."""
    async with aiohttp.ClientSession() as session:
        headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
        search_query = f"{company_name} official website linkedin company profile"
        results = await _execute_serper_query(session, search_query, serper_api_key, headers, num_results=10)
        if results and "organic" in results:
            print("Top 10 Google search results:")
            for idx, res_item in enumerate(results["organic"], 1):
                print(f"{idx}. {res_item.get('link', 'N/A')}")
        else:
            print("No results found.")

if __name__ == "__main__":
    company_name = "Your Company Name Here"  # Замените на нужное название компании
    serper_api_key = "Your Serper API Key Here"  # Замените на ваш API ключ
    asyncio.run(test_serper_query(company_name, serper_api_key)) 