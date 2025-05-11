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

# 1. Define the strict JSON schema in English
# This schema is based on the user's provided YAML structure.
COMPANY_PROFILE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "company_name": {
            "type": "string",
            "description": "Official legal name of the company."
        },
        "founding_year": {
            "type": ["integer", "null"], # Allow null if not found
            "description": "Year the company was founded."
        },
        "headquarters_city": {
            "type": ["string", "null"],
            "description": "City where the company's headquarters is located."
        },
        "headquarters_country": {
            "type": ["string", "null"],
            "description": "Country where the company's headquarters is located."
        },
        "founders": {
            "type": "array",
            "description": "List of company founders. Can be empty or null if not found.",
            "items": {"type": "string"}
        },
        "ownership_background": {
            "type": ["string", "null"],
            "description": "Information about the owners or parent fund/company."
        },
        "core_products_services": { # Renamed for clarity
            "type": "array",
            "description": "Main products or services offered by the company.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "description": "Name of the product/service."},
                    "launch_year": {"type": ["integer", "null"], "description": "Year the product/service was launched (if specified)."}
                },
                "required": ["name", "launch_year"]
            }
        },
        "underlying_technologies": {
            "type": "array",
            "description": "Key technologies used or developed by the company.",
            "items": {"type": "string"}
        },
        "customer_types": {
            "type": "array",
            "description": "Primary types of customers (e.g., B2B, B2C, B2G).",
            "items": {"type": "string"}
        },
        "industries_served": { # Renamed for clarity
            "type": "array",
            "description": "Industries the company serves.",
            "items": {"type": "string"}
        },
        "geographic_markets": {
            "type": "array",
            "description": "Geographical markets where the company operates.",
            "items": {"type": "string"}
        },
        "financial_details": {
            "type": ["object", "null"],
            "description": "Key financial indicators. All sub-fields should be populated if the financial_details object itself is not null.",
            "additionalProperties": False,
            "properties": {
                "ARR": {
                    "type": ["object", "null"],
                    "description": "Annual Recurring Revenue details.",
                    "additionalProperties": False,
                    "properties": {
                        "amount": {"type": ["number", "null"], "description": "Numerical value of ARR."},
                        "currency": {"type": ["string", "null"], "description": "Currency code (e.g., USD, EUR) or symbol."},
                        "year_reported": {"type": ["integer", "null"], "description": "Year the ARR figure was reported for."},
                        "note": {"type": ["string", "null"], "description": "Original textual representation if non-standard (e.g., 'approx. $10M ARR in 2023')."}
                    },
                    "required": ["amount", "currency", "year_reported", "note"]
                },
                "total_funding": {
                    "type": ["object", "null"],
                    "description": "Total funding amount raised.",
                    "additionalProperties": False,
                    "properties": {
                        "amount": {"type": ["number", "null"], "description": "Numerical value of total funding."},
                        "currency": {"type": ["string", "null"], "description": "Currency code (e.g., USD, EUR) or symbol."},
                        "note": {"type": ["string", "null"], "description": "Original textual representation if non-standard (e.g., 'Series A: $5M USD')."}
                    },
                    "required": ["amount", "currency", "note"]
                },
                "latest_annual_revenue": {
                    "type": ["object", "null"],
                    "description": "Latest reported annual revenue.",
                    "additionalProperties": False,
                    "properties": {
                        "amount": {"type": ["number", "null"], "description": "Numerical value of the revenue."},
                        "currency": {"type": ["string", "null"], "description": "Currency code (e.g., USD, EUR) or symbol."},
                        "year_reported": {"type": ["integer", "null"], "description": "Year the revenue figure was reported for."},
                        "note": {"type": ["string", "null"], "description": "Original textual representation of the revenue figure if it's non-standard (e.g., 'approx. €4.05B in 2023')."}
                    },
                    "required": ["amount", "currency", "year_reported", "note"]
                }
            },
            "required": ["ARR", "total_funding", "latest_annual_revenue"]
        },
        "employee_count": { # Renamed for clarity
            "type": ["integer", "null"],
            "description": "Approximate number of employees."
        },
        "major_clients_or_case_studies": { # Renamed for clarity
            "type": "array",
            "description": "Notable clients or publicly mentioned case studies/implementations.",
            "items": {"type": "string"}
        },
        "strategic_initiatives": { # Renamed for clarity
            "type": "array",
            "description": "Key strategic moves, partnerships, or acquisitions.",
            "items": {"type": "string"}
        },
        "key_competitors_mentioned": { # Renamed for clarity
            "type": "array",
            "description": "Main competitors mentioned in the provided text.",
            "items": {"type": "string"}
        },
        "overall_summary": {
             "type": ["string", "null"],
             "description": "A brief one or two-sentence summary of the company based on the extracted information."
        }
    },
    "required": [
        "company_name",
        "founding_year",
        "headquarters_city",
        "headquarters_country",
        "founders",
        "ownership_background",
        "core_products_services",
        "underlying_technologies",
        "customer_types",
        "industries_served",
        "geographic_markets",
        "financial_details",
        "employee_count",
        "major_clients_or_case_studies",
        "strategic_initiatives",
        "key_competitors_mentioned",
        "overall_summary"
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
            temperature=0.0 # We want a deterministic answer
        )
        answer = response.choices[0].message.content.strip().lower()
        # print(f"  LLM Page Check for '{company_name}': Snippet '{snippet_for_llm[:50]}...', Answer: '{answer}'")
        return answer == "yes"
    except Exception as e:
        print(f"  Error during LLM page check for {company_name}: {type(e).__name__} - {e}")
        return False # Default to false on error to be conservative

async def generate_description_openai_async(
    company_name: str, 
    # homepage_root: str | None, # No longer directly used in prompt
    # linkedin_url: str | None,  # No longer directly used in prompt
    about_snippet: str | None, # This is the combined text_src_for_llms
    llm_config: dict, # Still useful for model name, temperature, etc.
    openai_client: AsyncOpenAI,
    # context_text: str | None # No longer directly used in prompt
    # Return type is now Dict or None
) -> Optional[Dict[str, Any]]:
    """
    Async: Extracts structured company information into a predefined JSON schema 
    using the provided text snippet (about_snippet) and an LLM.
    """
    if not about_snippet:
        logger.warning(f"No text (about_snippet) provided for LLM input for {company_name}. Cannot generate structured data.")
        return None
    if not llm_config or not isinstance(llm_config, dict):
        logger.error(f"Invalid LLM config for {company_name}. Cannot generate structured data.")
        return None
    
    # Use a model suitable for JSON mode and complex extraction, e.g., gpt-4o-mini or gpt-4-turbo
    # The llm_config.yaml might specify this, or we default.
    # Forcing gpt-4o-mini as per user's example for JSON schema mode.
    model_name = llm_config.get('model', "gpt-4o-mini") 
    if model_name not in ["gpt-4o-mini", "gpt-4-turbo", "gpt-4o", "gpt-3.5-turbo"]: # Add other compatible models
        logger.warning(f"Model {model_name} from config might not be ideal for JSON schema mode. Consider gpt-4o-mini or gpt-4-turbo.")
        # Defaulting to gpt-4o-mini if an incompatible model is specified for this specific task.
        model_name = "gpt-4o-mini"


    system_prompt_content = (
        "You are a highly accurate data extraction and structuring AI. "
        "Your task is to meticulously analyze the provided text snippet about a company and populate a JSON object "
        "according to the given schema. Extract information ONLY from the provided text. "
        "If information for a specific field is not found in the text, use 'null' for that field. "
        "Adhere strictly to the schema's data types and structure. Do not add any fields not present in the schema."
    )
    
    user_prompt_content = (
        f"Please extract information about the company '{company_name}' from the following text snippet and structure it "
        f"according to the 'company_profile' JSON schema provided. "
        f"Ensure all required fields in the schema are addressed. If information is absent for non-required fields, use null.\\n\\n"
        f"Text Snippet to Analyze:\\n```\\n{about_snippet[:120000]} \\n```" # Max context for some models
    )

    messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": user_prompt_content}
    ]

    api_params = {
        "model": model_name,
        "messages": messages,
        "temperature": llm_config.get("temperature", 0.1), # Low temperature for factual extraction
        "top_p": llm_config.get("top_p", 0.9),
        "max_tokens": llm_config.get("max_tokens", 4000), # Ensure enough tokens for JSON
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "company_profile_extraction", # Function/schema name for OpenAI
                "strict": True, # Enforce schema strictly
                "schema": COMPANY_PROFILE_SCHEMA
            }
        }
    }
    
    logger.info(f"Attempting to generate structured JSON for {company_name} using model {model_name}.")
    try:
        response = await openai_client.chat.completions.create(**api_params)
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            response_content = response.choices[0].message.content.strip()
            try: 
                parsed_json = json.loads(response_content)
                logger.info(f"LLM successfully generated structured JSON for {company_name}.")
                # You could add validation against the schema here if desired, using a library like jsonschema
                return parsed_json
            except json.JSONDecodeError: 
                logger.error(f"Error: LLM response for {company_name} was not valid JSON. Response: {response_content[:500]}...")
                return {"error": "LLM response not valid JSON", "raw_response": response_content}
        else: 
            logger.warning(f"OpenAI returned no choices/content for structured JSON for {company_name}.")
            return {"error": "OpenAI returned no choices/content"}
    except APIError as e:
        logger.error(f"OpenAI APIError for structured JSON ({company_name}): {type(e).__name__} - {str(e)}")
        return {"error": f"OpenAI APIError: {str(e)}"}
    except Exception as e: 
        logger.error(f"Unexpected error during structured JSON generation for {company_name}: {type(e).__name__} - {str(e)}", exc_info=True)
        return {"error": f"Unexpected error: {str(e)}"} 