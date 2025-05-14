"""
JSON schemas for structured data extraction from company information.
"""

import json
import time
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
import numpy as np # For dot product if not using sklearn
import logging
import traceback
import asyncio
from typing import List, Dict, Any, Optional
# import tenacity # Закомментировано
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log, RetryError # Закомментировано

logger = logging.getLogger(__name__)

# --- Individual Sub-Schemas (MUST BE DEFINED BEFORE COMPANY_PROFILE_SCHEMA) --- 

BASIC_INFO_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "company_name": {"type": "string", "description": "Official legal name of the company."},
        "founding_year": {"type": ["integer", "null"], "description": "Year the company was founded."},
        "headquarters_city": {"type": ["string", "null"], "description": "City of the company's headquarters."},
        "headquarters_country": {"type": ["string", "null"], "description": "Country of the company's headquarters."},
        "founders": {"type": "array", "description": "List of company founders.", "items": {"type": "string"}},
        "ownership_background": {"type": ["string", "null"], "description": "Information about owners or parent fund/company."}
    },
    "required": ["company_name", "founding_year", "headquarters_city", "headquarters_country", "founders", "ownership_background"]
}

PRODUCT_TECH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "core_products_services": {
            "type": "array",
            "description": "Main products or services.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "description": "Name of product/service."},
                    "launch_year": {"type": ["integer", "null"], "description": "Launch year."}
                },
                "required": ["name", "launch_year"]
            }
        },
        "underlying_technologies": {"type": "array", "description": "Key technologies used.", "items": {"type": "string"}}
    },
    "required": ["core_products_services", "underlying_technologies"]
}

MARKET_CUSTOMER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "customer_types": {"type": "array", "description": "Primary customer types (B2B, B2C, B2G).", "items": {"type": "string"}},
        "industries_served": {"type": "array", "description": "Industries served.", "items": {"type": "string"}},
        "geographic_markets": {"type": "array", "description": "Geographical markets.", "items": {"type": "string"}}
    },
    "required": ["customer_types", "industries_served", "geographic_markets"]
}

FINANCIAL_HR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "financial_details": {
            "type": ["object", "null"],
            "description": "Key financial indicators. May include data for multiple recent years if available.",
            "additionalProperties": False,
            "properties": {
                "annual_revenue_history": { 
                    "type": "array",
                    "description": "Array of annual revenue figures for different reported years (could be total revenue or ARR).",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "year_reported": {"type": ["integer", "null"], "description": "The fiscal year the revenue data pertains to."},
                            "amount": {"type": ["number", "null"], "description": "Numerical value of the revenue."},
                            "currency": {"type": ["string", "null"], "description": "Currency code (e.g., USD, EUR) or symbol."},
                            "revenue_type": {"type": ["string", "null"], "description": "Type of revenue (e.g., 'Total Annual Revenue', 'ARR')."},
                            "note": {"type": ["string", "null"], "description": "Original textual representation or context."}
                        },
                        "required": ["year_reported", "amount", "currency", "revenue_type", "note"]
                    }
                },
                "funding_rounds": { 
                    "type": "array",
                    "description": "Array of funding round details.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "round_name": {"type": ["string", "null"], "description": "Name of the funding round."},
                            "year_closed": {"type": ["integer", "null"], "description": "Year funding was closed/reported."},
                            "amount": {"type": ["number", "null"], "description": "Numerical value of funding."},
                            "currency": {"type": ["string", "null"], "description": "Currency code or symbol."},
                            "key_investors": {"type": "array", "items": {"type": "string"}, "description": "List of key investors."},
                            "note": {"type": ["string", "null"], "description": "Other relevant notes."}
                        },
                        "required": ["year_closed", "amount", "currency", "round_name", "key_investors", "note"]
                    }
                }
            },
            "required": ["annual_revenue_history", "funding_rounds"]
        },
        "employee_count_details": {
            "type": ["object", "null"],
            "description": "Details about employee count.",
            "additionalProperties": False,
            "properties": {
                "count": {"type": ["integer", "null"], "description": "Approximate number of employees."},
                "year_reported": {"type": ["integer", "null"], "description": "Year this count was reported for."},
                "note": {"type": ["string", "null"], "description": "Context if employee count is an estimate or specific to a region."}
            },
            "required": ["count", "year_reported", "note"]
        }
    },
    "required": ["financial_details", "employee_count_details"]
}

STRATEGIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "major_clients_or_case_studies": {"type": "array", "description": "Major clients/case studies.", "items": {"type": "string"}},
        "strategic_initiatives": {"type": "array", "description": "Strategic moves (partnerships, M&A).", "items": {"type": "string"}},
        "key_competitors_mentioned": {"type": "array", "description": "Main competitors mentioned.", "items": {"type": "string"}},
        "overall_summary": {"type": ["string", "null"], "description": "Brief company summary based on extracted info."}
    },
    "required": ["major_clients_or_case_studies", "strategic_initiatives", "key_competitors_mentioned", "overall_summary"]
}

# COMPANY_PROFILE_SCHEMA now correctly references the above sub-schemas
COMPANY_PROFILE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "company_name": BASIC_INFO_SCHEMA["properties"]["company_name"],
        "founding_year": BASIC_INFO_SCHEMA["properties"]["founding_year"],
        "headquarters_city": BASIC_INFO_SCHEMA["properties"]["headquarters_city"],
        "headquarters_country": BASIC_INFO_SCHEMA["properties"]["headquarters_country"],
        "founders": BASIC_INFO_SCHEMA["properties"]["founders"],
        "ownership_background": BASIC_INFO_SCHEMA["properties"]["ownership_background"],
        "core_products_services": PRODUCT_TECH_SCHEMA["properties"]["core_products_services"],
        "underlying_technologies": PRODUCT_TECH_SCHEMA["properties"]["underlying_technologies"],
        "customer_types": MARKET_CUSTOMER_SCHEMA["properties"]["customer_types"],
        "industries_served": MARKET_CUSTOMER_SCHEMA["properties"]["industries_served"],
        "geographic_markets": MARKET_CUSTOMER_SCHEMA["properties"]["geographic_markets"],
        "financial_details": FINANCIAL_HR_SCHEMA["properties"]["financial_details"], 
        "employee_count_details": FINANCIAL_HR_SCHEMA["properties"]["employee_count_details"],
        "major_clients_or_case_studies": STRATEGIC_SCHEMA["properties"]["major_clients_or_case_studies"],
        "strategic_initiatives": STRATEGIC_SCHEMA["properties"]["strategic_initiatives"],
        "key_competitors_mentioned": STRATEGIC_SCHEMA["properties"]["key_competitors_mentioned"],
        "overall_summary": STRATEGIC_SCHEMA["properties"]["overall_summary"]
    },
    "required": [
        "company_name", "founding_year", "headquarters_city", "headquarters_country",
        "founders", "ownership_background", "core_products_services", "underlying_technologies",
        "customer_types", "industries_served", "geographic_markets", "financial_details",
        "employee_count_details", "major_clients_or_case_studies", "strategic_initiatives",
        "key_competitors_mentioned", "overall_summary"
    ]
}

# Упрощенная схема для структурированного вывода
SIMPLIFIED_COMPANY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "company_name": {"type": "string", "description": "Official name of the company."},
        "founding_year": {"type": ["string", "null"], "description": "Year the company was founded."},
        "headquarters_location": {"type": ["string", "null"], "description": "Location of the company's headquarters."},
        "industry": {"type": ["string", "null"], "description": "Industry or sector in which the company operates."},
        "main_products_services": {"type": ["string", "null"], "description": "Brief description of main products/services."},
        "employees_count": {"type": ["string", "null"], "description": "Number of employees (can be a range)."},
        "description": {"type": "string", "description": "3-paragraph company description."}
    },
    "required": [
        "company_name", "founding_year", "headquarters_location", "industry", 
        "main_products_services", "employees_count", "description"
    ]
} 

async def get_embedding_async(text: str, openai_client: AsyncOpenAI, model: str = "text-embedding-3-small") -> list[float] | None:
    """Generates an embedding for the given text using OpenAI."""
    if not text or not openai_client: return None
    text = text.replace("\n", " ").strip()
    if not text: return None
    try:
        response = await openai_client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e: print(f"Embed Error '{text[:30]}..': {e}"); return None

async def is_url_company_page_llm(company_name: str, page_snippet: str, openai_client: AsyncOpenAI, model_for_check: str = "gpt-4o-mini") -> bool:
    """Uses LLM to verify if a page snippet is primarily about the given company."""
    if not page_snippet or not company_name:
        return False
    
    # Keep the snippet reasonably short for this check to save tokens and time
    snippet_for_llm = page_snippet[:1500] 

    prompt_messages = [
        {"role": "system", "content": "You are a precise web page classifier. Your sole task is to determine if the provided text snippet indicates the page is primarily about the company itself (e.g., an 'About Us' page, homepage, or corporate profile), not just a product page, news article, or unrelated content. Answer ONLY with 'yes' or 'no'."},
        {"role": "user", "content": f"Company Name: \"{company_name}\"\n\nText Snippet from webpage:\n```\n{snippet_for_llm}\n```\n\nIs this page snippet primarily about the company '{company_name}' or a general corporate page for it? Answer 'yes' or 'no'."}
    ]
    
    try:
        response = await openai_client.chat.completions.create(
            model=model_for_check, # Allow using a specific (possibly cheaper/faster) model for this check
            messages=prompt_messages,
            max_tokens=10, # Expecting a very short answer
            web_search_options={"search_context_size": "high"} 
        )
        answer = response.choices[0].message.content.strip().lower()
        # print(f"  LLM Page Check for '{company_name}': Snippet '{snippet_for_llm[:50]}...', Answer: '{answer}'")
        return answer == "yes"
    except Exception as e:
        print(f"  Error during LLM page check for {company_name}: {type(e).__name__} - {e}")
        return False # Default to false on error to be conservative

async def extract_data_with_schema(
    company_name: str, 
    about_snippet: str | None, 
    sub_schema: Dict[str, Any],
    schema_name: str, 
    llm_config: dict, 
    openai_client: AsyncOpenAI,
) -> Optional[Dict[str, Any]]:
    """
    Async: Extracts structured company information into a *specific sub-schema* 
    using the provided text snippet and an LLM.
    """
    if not about_snippet:
        logger.warning(f"No text (about_snippet) for {company_name} for schema '{schema_name}'. Returning empty dict.")
        return {}
    if not llm_config or not isinstance(llm_config, dict):
        logger.error(f"Invalid LLM config for {company_name} (schema '{schema_name}'). Returning error dict.")
        return {"error": f"Invalid LLM config for schema {schema_name}"}
    
    model_name = llm_config.get('model', "gpt-4o-mini") 
    if model_name not in ["gpt-4o-mini", "gpt-4-turbo", "gpt-4o", "gpt-3.5-turbo"]:
        logger.warning(f"Model {model_name} from config might not be ideal for JSON schema mode. Defaulting to gpt-4o-mini for {schema_name}.")
        model_name = "gpt-4o-mini"

    # Updated System Prompt for schema extraction
    system_prompt_content = (
        "You are a meticulous data extraction AI. Your task is to analyze the provided text about a company and populate a JSON object "
       f"strictly according to the fields and structure defined in the provided JSON schema named '{schema_name}'. "
        "Extract information ONLY from the provided text. "
        "If information for a specific field (especially optional or array/object sub-fields) is not found in the text, you MUST use 'null' for that field or an empty array [] for array types, as appropriate, to ensure all keys defined in the schema's 'properties' are present in your output if they are also in the schema's 'required' list, or if the schema implies their presence due to 'additionalProperties: false'."
        "For array fields (e.g., annual_revenue_history, funding_rounds, core_products_services), extract all distinct relevant items found in the text that fit the item's sub-schema. If no items are found for an array, return an empty array []."
        "Pay close attention to nested structures and ensure all required fields within nested objects are populated (using null if data is absent)."
        "Adhere strictly to the schema's data types. Do not add any fields not defined in the schema."
    )
    
    # Updated User Prompt for schema extraction
    user_prompt_content = (
        f"Please extract information about the company '{company_name}' from the following text snippet. "
        f"Structure your response strictly according to the JSON schema named '{schema_name}' which will be provided to you via the function calling mechanism. "
        f"Focus ONLY on the fields defined in this specific schema. "
        f"For any fields where information cannot be found in the text, use a JSON 'null' value. For array fields, if no items are found, use an empty array [].\n\n"
        f"Text Snippet to Analyze:\n```\n{about_snippet[:120000]} \n```"
    )

    messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": user_prompt_content}
    ]

    api_params = {
        "model": model_name,
        "messages": messages,
        "temperature": llm_config.get("temperature_json_extract", llm_config.get("temperature", 0.05)), 
        "top_p": llm_config.get("top_p_json_extract", llm_config.get("top_p", 0.5)),
        "max_tokens": llm_config.get("max_tokens_json_extract", 4500), # Max tokens for sub-schema extraction
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name, 
                "strict": True, 
                "schema": sub_schema 
            }
        }
    }
    
    logger.info(f"Attempting to extract for schema '{schema_name}' for {company_name} using model {model_name}.")
    try:
        response = await openai_client.chat.completions.create(**api_params)
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            response_content = response.choices[0].message.content.strip()
            try: 
                parsed_json = json.loads(response_content)
                logger.info(f"LLM successfully generated JSON for schema '{schema_name}' for {company_name}.")
                return parsed_json
            except json.JSONDecodeError: 
                logger.error(f"Error: LLM response for {company_name} (schema '{schema_name}') not valid JSON. Response: {response_content[:500]}...")
                return {"error": f"LLM response not valid JSON for schema {schema_name}", "raw_response": response_content}
        else: 
            logger.warning(f"OpenAI returned no choices/content for schema '{schema_name}' for {company_name}.")
            return {"error": f"OpenAI returned no choices/content for schema {schema_name}"}
    except APIError as e:
        logger.error(f"OpenAI APIError for {company_name} (schema '{schema_name}'): {type(e).__name__} - {str(e)}")
        return {"error": f"OpenAI APIError for schema {schema_name}: {str(e)}"}
    except Exception as e: 
        logger.error(f"Unexpected error for {company_name} (schema '{schema_name}'): {type(e).__name__} - {str(e)}", exc_info=True)
        return {"error": f"Unexpected error for schema {schema_name}: {str(e)}"}

async def generate_text_summary_from_json_async(
    company_name: str,
    structured_data: Dict[str, Any],
    openai_client: AsyncOpenAI,
    llm_config: dict,
) -> Optional[str]:
    """
    Async: Generates a readable three-paragraph text summary from structured JSON data about a company.
    Handles new array structures for financial data.
    """
    if not structured_data:
        logger.warning(f"No structured data provided for {company_name} to generate text summary.")
        return "Error: No structured data to summarize."
    model_name = llm_config.get('model_for_summary', llm_config.get('model', "gpt-4o"))
    try:
        json_input_for_prompt = json.dumps(structured_data, ensure_ascii=False, indent=None)
    except TypeError as e:
        logger.error(f"Failed to serialize structured_data for {company_name}: {e}")
        return f"Error: Could not serialize structured data for {company_name}."

    system_prompt_content = (
        "You are a skilled business writer specializing in synthesizing structured data into concise, professional company profiles. "
        "Your output must be a three-paragraph summary in English, based ONLY on the provided JSON data. "
        "Do not add external information or speculate. Adhere strictly to the three-paragraph format with formal language. "
        "When summarizing financial history arrays (like revenue or funding), typically focus on the most recent and significant single data point unless multiple distinct years are particularly noteworthy for a narrative. Clearly state years and currencies."
    )
    
    # Updated User Prompt to guide handling of financial arrays
    user_prompt_content = f"""Company Name: {company_name}

Structured Company Data (JSON):
```json
{json_input_for_prompt}
```

Task: Based SOLELY on the structured JSON data provided above, generate a concise three-paragraph company profile in English.

Strict formatting rules:
- The output must be exactly three paragraphs.
- Each paragraph should be a dense, well-written block of text.
- Separate paragraphs with a single blank line.
- Do not use markdown formatting (like bolding or bullet points) or section headers in your output text.
- Write in a formal, third-person perspective.
- Ensure all information comes directly from the provided JSON data. Do not infer or add external knowledge.
- Spell out acronyms on first use if their full form is available in the JSON.

Paragraph Structure Guide (use the data fields mentioned if available in the JSON):
1.  Paragraph 1 (Foundational Details): company_name, founding_year, headquarters_city, headquarters_country, founders, ownership_background.
2.  Paragraph 2 (Core Business): core_products_services, underlying_technologies, customer_types, industries_served, geographic_markets.
3.  Paragraph 3 (Operational & Strategic Highlights): 
    - For `financial_details.annual_revenue_history`: Mention the revenue for the most recent `year_reported`. If multiple distinct years are present and significant, you can briefly note a trend or the most recent two. Always state the year and currency. Example: "The company reported an annual revenue of €X million in 2024."
    - For `financial_details.funding_rounds`: Mention significant or recent funding. Example: "It recently secured $Y million in a Series B round in 2023 led by InvestorZ."
    - Incorporate `employee_count_details` (e.g., "with Z employees as of 2023").
    - Weave in `major_clients_or_case_studies`, `strategic_initiatives`, `key_competitors_mentioned`.
    - Conclude with a sentence based on `overall_summary`.
"""

    messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": user_prompt_content}
    ]

    api_params = {
        "model": model_name,
        "messages": messages,
        "temperature": llm_config.get("temperature_for_summary", llm_config.get("temperature", 0.7)), 
        "top_p": llm_config.get("top_p_for_summary", llm_config.get("top_p", 0.9)),
        "max_tokens": llm_config.get("max_tokens_for_summary", 1500) 
    }

    logger.info(f"Attempting to generate three-paragraph summary for {company_name} using model {model_name}.")
    try:
        response = await openai_client.chat.completions.create(**api_params)
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            text_summary = response.choices[0].message.content.strip()
            paragraph_count = text_summary.count("\n\n") + 1
            logger.info(f"Successfully generated {paragraph_count}-paragraph profile for {company_name} (Length: {len(text_summary)}).")
            return text_summary
        else:
            logger.warning(f"OpenAI returned no choices/content for text summary for {company_name}.")
            return f"Error: LLM returned no content for summary."
    except APIError as e:
        logger.error(f"OpenAI APIError during text summary generation for {company_name}: {type(e).__name__} - {str(e)}")
        return f"Error generating summary (APIError): {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error during text summary generation for {company_name}: {type(e).__name__} - {str(e)}", exc_info=True)
        return f"Error generating summary (Exception): {str(e)}" 