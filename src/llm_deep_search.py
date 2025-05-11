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
    specific_aspects_to_cover: List[str],
    user_context_text: Optional[str] = None # Added user_context_text parameter
) -> str: 
    """
    Asynchronously requests a comprehensive, structured business report for a company
    from OpenAI's gpt-4o-mini-search-preview model using a single, detailed query.
    The query is guided by the provided list of specific aspects and optional user context.
    Sources found by the LLM are logged but not included in the returned report text.

    Args:
        openai_client: The AsyncOpenAI client.
        company_name: The name of the company.
        specific_aspects_to_cover: A list of topics/questions to ensure the report addresses.
        user_context_text: Optional user-provided context to further guide the search.

    Returns:
        A string containing the comprehensive LLM report (TEXT ONLY, without appended sources),
        or an error message string.
    """
    llm_model = "gpt-4o-mini-search-preview"

    safe_company_name = escape_string_for_prompt(company_name)
    
    # Use the passed specific_aspects_to_cover to build the prompt
    additional_aspects_str = ""
    if specific_aspects_to_cover: # Check if the list is not empty
        escaped_additional_aspects = [escape_string_for_prompt(aspect) for aspect in specific_aspects_to_cover]
        additional_aspects_str = "\n\nAdditionally, ensure these specific aspects are thoroughly investigated and included within the relevant sections of your report:\n- " + "\n- ".join(escaped_additional_aspects)
    else:
        logger.warning(f"[DeepSearch] specific_aspects_to_cover list is empty for '{company_name}'. The report might be less targeted.")
        # No specific aspects to add to the prompt if the list is empty

    context_injection_str = ""
    if user_context_text:
        safe_user_context = escape_string_for_prompt(user_context_text)
        context_injection_str = f"\n\nConsider the following user-provided context for your research and report generation: '{safe_user_context}'"
        logger.info(f"[DeepSearch] Using user-provided context for '{company_name}': '{user_context_text[:100]}...'")

    prompt_template = """Please generate a detailed Business Analytics Report for the company: '{company_name_placeholder}'.

Your primary goal is to extract and present factual data, focusing on information from 2024-2025 where available. The report MUST strictly follow the structure outlined below and include the requested details for each section. Use your web search capabilities to find the most current information.

Report Structure:

1.  **Customer Segments:**
    *   Identify and detail main customer categories (e.g., Consumer, Business, Wholesale, Government/Public Sector).
    *   Provide key metrics: wireless retail connections, post-paid vs. prepaid figures, total broadband subscribers (broken down by type like Fios fiber vs. fixed-wireless if applicable), and relevant market share if found.
    *   Note any specialized services for distinct communities (e.g., first-responder networks).

2.  **Geographic Reach:**
    *   Describe core network operational areas and retail footprint (e.g., US-centric, specific states/regions for key services like Fios).
    *   Detail global presence for enterprise services, including owned infrastructure vs. partner Points of Presence (POPs) and countries covered.

3.  **Business Units / Segments (Financials & Activities):**
    *   List main operational business units or segments.
    *   For each: Provide latest reported annual revenue (specify year, e.g., 2024 revenue) and list core activities/offerings.

4.  **Products and Indicative Prices (Latest Available, e.g., May 2025):
    *   Key Products/Services: List flagship offerings (e.g., 5G mobile plans like 'myPlan Unlimited', Fios Internet tiers, 5G Home Internet, Business unlimited mobility, Private 5G solutions).
    *   Indicative Pricing: For major offerings, provide entry-level monthly pricing. Note any conditions: discounts (e.g., Mobile + Home), price lock durations, contract requirements, setup fees, included equipment. Mention any significant promotional offers (e.g., free devices/services with specific plans).

5.  **Core Offers & Promotions (Strategic Summary):**
    *   Summarize key ongoing offers defining their market strategy (e.g., device trade-in credits, bundling discounts, special programs for demographics like low-income households - e.g., Verizon Forward + Lifeline).

6.  **Customer Needs Addressed (Solution Mapping):**
    *   For key customer needs (e.g., ubiquitous reliable mobility, high-speed home/business broadband, mission-critical communications, enterprise digital transformation, low-income connectivity), describe how the company's specific offerings (Verizon responses) meet these needs.

7.  **Solution Portfolio Snapshot (Technical Capabilities & Ecosystem):**
    *   Network Technology: Spectrum bands utilized (e.g., 700 MHz, C-Band, mmWave), backbone type (e.g., 100% fiber), core network features (e.g., SDN-enabled).
    *   5G Details: Specifics of 5G offerings (e.g., Ultra Wideband vs. Nationwide, C-Band coverage, mmWave for hot-zones, support for network slicing, Mobile Edge Compute - MEC).
    *   Fixed Wireless Access (FWA): Technology (5G/LTE), CPE details, typical speeds.
    *   Private Networks: Offerings for enterprises (e.g., Private 5G On-Site, NaaS models), target verticals (e.g., ports, factories, stadiums), integration with AI/edge compute.
    *   IoT Platform: (e.g., ThingSpace), SIM/eSIM capabilities, device management, analytics, global IoT footprint.
    *   Security Services: Portfolio for enterprise/business (e.g., managed firewalls, DDoS protection, SASE/SSE, zero-trust, partner ecosystem for security).
    *   Unified Communications (UCaaS): Current strategy and offerings (e.g., if native solutions like BlueJeans are retired, what partner platforms are promoted).

8.  **Competitive Posture & Market Strategy:**
    *   Summarize the company's competitive strategy, focusing on network strengths (reliability, coverage), customer base (post-paid focus), cross-selling (FWA, fiber), and how they counter price-led competition and retain enterprise clients (e.g., price locks, subsidies, specialization like first-responder networks, private 5G/IoT stickiness).

{additional_aspects_placeholder}{user_context_placeholder}

Provide a concise, data-driven report. Avoid conversational filler, disclaimers, or speculative statements. All factual data, especially figures like revenue, subscriber counts, and pricing, should be cited with sources, either inline or in a concluding 'Sources' list. Respond only in English."""

    user_content = prompt_template.format(
        company_name_placeholder=safe_company_name, 
        additional_aspects_placeholder=additional_aspects_str,
        user_context_placeholder=context_injection_str
    )

    system_prompt = (
        "You are an AI Business Analyst. Your task is to generate a detailed, structured, and factual business report on a given company, in English. "
        "Utilize your web search capabilities to find the most current information (2024-2025 focus). "
        "Adhere strictly to the requested report structure and level of detail. Cite all specific data points (financials, subscriber counts, pricing, etc.) with their sources. "
        "Be concise and data-driven. Do not include conversational intros, outros, or disclaimers. Respond only in English."
    )

    logger.info(f"[DeepSearch] Starting multi-turn comprehensive query for '{company_name}' using model '{llm_model}'. Aspects: {specific_aspects_to_cover}")
    logger.debug(f"[DeepSearch] Compiled user_content for '{company_name}' (first 500 chars): '{user_content[:500]}...'")

    try:
        completion = await openai_client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            # max_tokens=3800, 
            web_search_options={"search_context_size":"high"}
        )

        answer_content = "LLM did not provide a comprehensive answer."
        
        if completion.choices and completion.choices[0].message:
            message = completion.choices[0].message
            if message.content:
                answer_content = message.content.strip()
            
            if message.annotations:
                citations_log_list = []
                for ann_index, ann in enumerate(message.annotations):
                    if ann.type == "url_citation" and ann.url_citation:
                        cited_title = ann.url_citation.title or "N/A"
                        cited_url = ann.url_citation.url or "N/A"
                        citations_log_list.append(f"  [Source {ann_index+1}] Title: {cited_title}, URL: {cited_url}")
                if citations_log_list:
                    logger.info(f"[DeepSearch] Sources found for '{company_name}':\n" + "\n".join(citations_log_list))
            else:
                logger.info(f"[DeepSearch] No annotations/sources provided by LLM for '{company_name}'.")
        
        logger.info(f"[DeepSearch] For '{company_name}', comprehensive LLM report text generated (first 100 chars): '{answer_content[:100]}...'")
        return answer_content 

    except APIError as e:
        logger.error(f"[DeepSearch] OpenAI API error for '{company_name}' (comprehensive query): {e}")
        return f"Deep Search Error: OpenAI API issue - {str(e)}"
    except Timeout as e:
        logger.error(f"[DeepSearch] Timeout error for '{company_name}' (comprehensive query): {e}")
        return f"Deep Search Error: Timeout - {str(e)}"
    except Exception as e:
        logger.error(f"[DeepSearch] Unexpected error for '{company_name}' (comprehensive query): {e}", exc_info=True)
        return f"Deep Search Error: Unexpected issue - {str(e)}"

async def main_test():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger.info("Starting main_test for llm_deep_search.py (single comprehensive English prompt)")

    class MockChatCompletionsMessage:
        content: Optional[str] = None
        annotations: Optional[List[Any]] = None
        def __init__(self, content=None, annotations=None):
            self.content = content
            self.annotations = annotations if annotations else []

    class MockChatCompletionsChoice:
        message: MockChatCompletionsMessage
        def __init__(self, message_content, message_annotations=None):
            self.message = MockChatCompletionsMessage(content=message_content, annotations=message_annotations)
            
    class MockChatCompletionsResponse:
        choices: List[MockChatCompletionsChoice]
        def __init__(self, choices):
            self.choices = choices

    class MockAsyncOpenAI:
        async def chat_completions_create(self, model, messages, max_tokens, web_search_options=None):
            # Simulate response based on the multi-turn message structure
            user_context_sim = "No specific user context provided in mock."
            final_instruction_sim = "No final instruction provided in mock."
            for m in messages:
                if m["role"] == "user":
                    if "user-provided context" in m["content"]:
                        user_context_sim = m["content"]
                    elif "Report Structure:" in m["content"]:
                        final_instruction_sim = m["content"]
            
            report_content = (
                f"Mock report considering multi-turn. User context hint: '{user_context_sim[:100]}...'. Final instruction hint: '{final_instruction_sim[:100]}...'"
            )
            annotations_data = [] 
            choice = MockChatCompletionsChoice(message_content=report_content, message_annotations=annotations_data)
            return MockChatCompletionsResponse(choices=[choice])
        
        chat = type('MockChat', (object,), {})
        chat.completions = type('MockCompletions', (object,), {'create': chat_completions_create})

    mock_client = MockAsyncOpenAI()

    test_company = "ExampleTech Inc."
    test_aspects_list = ["2024 financial results", "new product lines"]
    test_user_context = "Focus on their expansion into the European market and any AI-related products."

    logger.info(f"Running mock deep search for company: {test_company} WITH user context (multi-turn sim).")
    report_text_with_context = await query_llm_for_deep_info(
        openai_client=mock_client, 
        company_name=test_company,
        specific_aspects_to_cover=test_aspects_list,
        user_context_text=test_user_context
    )
    print("\n--- Mock Report (WITH User Context, Multi-Turn Sim) ---")
    print(report_text_with_context)

    logger.info(f"Running mock deep search for company: {test_company} WITHOUT user context (multi-turn sim).")
    report_text_no_context = await query_llm_for_deep_info(
        openai_client=mock_client, 
        company_name=test_company,
        specific_aspects_to_cover=test_aspects_list
    )
    print("\n--- Mock Report (WITHOUT User Context, Multi-Turn Sim) ---")
    print(report_text_no_context)

    logger.info("Finished main_test for llm_deep_search.py")

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
        sample_aspects_list = ["latest AI platform enhancements", "growth in public sector contracts in 2024"]
        sample_context = "Please emphasize their go-to-market strategy for the financial services industry."
        
        async def actual_run():
            print(f"--- REAL OpenAI API Report for {sample_company} (WITH context, Multi-Turn) ---")
            report_with_ctx = await query_llm_for_deep_info(actual_client, sample_company, specific_aspects_to_cover=sample_aspects_list, user_context_text=sample_context)
            print(report_with_ctx)

            print(f"\n--- REAL OpenAI API Report for {sample_company} (WITHOUT context, Multi-Turn) ---")
            report_no_ctx = await query_llm_for_deep_info(actual_client, sample_company, specific_aspects_to_cover=sample_aspects_list)
            print(report_no_ctx)

        asyncio.run(actual_run())
    else:
        asyncio.run(main_test())