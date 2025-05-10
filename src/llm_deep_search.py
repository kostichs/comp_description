# src/llm_deep_search.py
import asyncio
import logging
import os # For test run
import sys # For test run
from pathlib import Path # For test run
from openai import AsyncOpenAI, APIError, Timeout
from typing import Any, Dict, List, Optional
import json # For escaping strings

logger = logging.getLogger(__name__)

def escape_string_for_prompt(text: str) -> str:
    """Escapes characters in a string to be safely embedded in a JSON-like or f-string context."""
    return json.dumps(text)[1:-1] # Use json.dumps and strip an extra pair of quotes



async def query_llm_for_deep_info(
    openai_client: AsyncOpenAI,
    company_name: str,
) -> str:
    """
    Uses gpt-4o-mini-search-preview to fetch marketing-relevant insights about a company.
    Optimized for maximum signal extraction using search tools.
    """
    specific_queries = [
        "1. Industry and primary business activities",
        "2. Key customer segments (B2B or B2C)",
        "3. IT stack and infrastructure scale",
        "4. Use of AI, cloud, automation, or data tools",
        "5. Digital transformation initiatives",
        "6. Recent technology partnerships or vendors",
        "7. Key decision makers (CIO, CTO, etc.)",
        "8. Openness to new vendor solutions",
        "9. Current operational or IT pain points",
        "10. Estimated budget or revenue scale"
    ]

    formatted_query = (
        f"Evaluate the company: {company_name}. For each of the following aspects, provide factual, recent, structured insights:\n\n"
        + "\n".join(specific_queries) +
        "\n\nUse content from 2023–2025 if possible. Be concise but specific. Mention concrete examples or vendors when available."
    )

    llm_model = "gpt-4o-mini-search-preview"

    system_prompt = (
    "You are a senior B2B go-to-market analyst. Your task is to extract strategic, actionable insights about a company "
    "to help a technology vendor evaluate partnership or sales potential. Focus on: industry focus, business lines, infrastructure scale, "
    "digital maturity, openness to third-party vendors, existing partnerships, and signs of investment in cloud, AI, automation, "
    "or data platforms. Identify buyer personas (e.g., CTO, CIO, CDO), typical deal sizes if available, and pain points in tech operations. "
    "Prefer recent (2023–2025) verifiable data. Include sources when possible."
    )

    user_query = formatted_query

    try:
        completion = await openai_client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            web_search_options={"search_context_size": "high"},
            max_tokens=3800,
        )
        
        message = completion.choices[0].message
        response_text = message.content.strip() if message and message.content else "No response."

        if message and message.annotations:
            citations_list = []
            for i, ann in enumerate(message.annotations):
                if ann.type == "url_citation" and ann.url_citation:
                    title = ann.url_citation.title or "N/A"
                    url = ann.url_citation.url or "N/A"
                    citations_list.append(f"[Source {i + 1}: {title} ({url})]")
            if citations_list:
                response_text += "\n\n--- Sources ---\n" + "\n".join(citations_list)

        return response_text

    except Exception as e:
        logger.error(f"[MarketingSearch] Failed for '{company_name}': {e}", exc_info=True)
        return f"Marketing Search Error: {str(e)}"


if __name__ == '__main__':
    is_real_run = False

    if is_real_run:
        if not os.getenv("OPENAI_API_KEY"):
            print("ERROR: OPENAI_API_KEY environment variable is not set for a real run.")
            sys.exit(1)

        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        logger.info("Attempting REAL OpenAI API call for testing query_llm_for_deep_info with structured prompt.")

        actual_client = AsyncOpenAI()
        sample_company = "ServiceNow"

        async def actual_run():
            report = await query_llm_for_deep_info(actual_client, sample_company)
            print("\n--- REAL OpenAI API Report (Structured English) ---")
            print(report)

        asyncio.run(actual_run())
    else:
        print("Dry run mode. No test function defined.")