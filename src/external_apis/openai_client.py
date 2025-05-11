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
                        "note": {"type": ["string", "null"], "description": "Original textual representation with the sentence that contains this information."}
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
                        "note": {"type": ["string", "null"], "description": "Original textual representation with the sentence that contains this information."}
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
                        "note": {"type": ["string", "null"], "description": "Original textual representation with the sentence that contains this information."}
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

# --- Individual Sub-Schemas --- 

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
            "description": "Key financial indicators.",
            "additionalProperties": False,
            "properties": {
                "ARR": {
                    "type": ["object", "null"],
                    "description": "Annual Recurring Revenue.",
                    "additionalProperties": False,
                    "properties": {
                        "amount": {"type": ["number", "null"]},
                        "currency": {"type": ["string", "null"]},
                        "year_reported": {"type": ["integer", "null"]},
                        "note": {"type": ["string", "null"]}
                    },
                    "required": ["amount", "currency", "year_reported", "note"]
                },
                "total_funding": {
                    "type": ["object", "null"],
                    "description": "Total funding raised.",
                    "additionalProperties": False,
                    "properties": {
                        "amount": {"type": ["number", "null"]},
                        "currency": {"type": ["string", "null"]},
                        "note": {"type": ["string", "null"]}
                    },
                    "required": ["amount", "currency", "note"]
                },
                "latest_annual_revenue": {
                    "type": ["object", "null"],
                    "description": "Latest annual revenue.",
                    "additionalProperties": False,
                    "properties": {
                        "amount": {"type": ["number", "null"]},
                        "currency": {"type": ["string", "null"]},
                        "year_reported": {"type": ["integer", "null"]},
                        "note": {"type": ["string", "null"]}
                    },
                    "required": ["amount", "currency", "year_reported", "note"]
                }
            },
            "required": ["ARR", "total_funding", "latest_annual_revenue"]
        },
        "employee_count": {"type": ["integer", "null"], "description": "Number of employees."}
    },
    "required": ["financial_details", "employee_count"]
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

async def extract_data_with_schema(
    company_name: str, 
    about_snippet: str | None, 
    sub_schema: Dict[str, Any], # Specific sub-schema for this extraction task
    schema_name: str, # Name for the schema, e.g., "basic_info_extraction"
    llm_config: dict, 
    openai_client: AsyncOpenAI,
) -> Optional[Dict[str, Any]]:
    """
    Async: Extracts structured company information into a *specific sub-schema* 
    using the provided text snippet and an LLM.
    """
    if not about_snippet:
        logger.warning(f"No text (about_snippet) for {company_name} for schema '{schema_name}'. Returning empty dict.")
        return {} # Return empty dict to allow merging, or None if preferred
    if not llm_config or not isinstance(llm_config, dict):
        logger.error(f"Invalid LLM config for {company_name} (schema '{schema_name}'). Returning error dict.")
        return {"error": f"Invalid LLM config for schema {schema_name}"}
    
    model_name = llm_config.get('model', "gpt-4o-mini") 
    if model_name not in ["gpt-4o-mini", "gpt-4-turbo", "gpt-4o", "gpt-3.5-turbo"]:
        logger.warning(f"Model {model_name} from config might not be ideal for JSON schema mode. Defaulting to gpt-4o-mini for {schema_name}.")
        model_name = "gpt-4o-mini"

    system_prompt_content = (
        "You are a highly accurate data extraction AI. Your task is to meticulously analyze the provided text about a company "
       f"and populate a JSON object strictly according to the fields defined in the provided '{schema_name}' schema. "
        "Extract information ONLY from the provided text. If information for a field is not found, use 'null' for that field. "
        "Adhere strictly to the schema's data types. Do not add any fields not present in the schema."
    )
    
    user_prompt_content = (
        f"Please extract information about the company '{company_name}' from the following text snippet and structure it "
       f"according to the '{schema_name}' JSON schema provided. Focus only on the fields defined in this specific schema.\n\n"
        f"Text Snippet to Analyze:\n```\n{about_snippet[:120000]} \n```"
    )

    messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": user_prompt_content}
    ]

    api_params = {
        "model": model_name,
        "messages": messages,
        "temperature": llm_config.get("temperature", 0.05), # Very low temperature for focused extraction
        "top_p": llm_config.get("top_p", 0.5),
        "max_tokens": llm_config.get("max_tokens", 2000), # Max tokens might be lower for smaller sub-schemas
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name, 
                "strict": True, 
                "schema": sub_schema # Use the passed sub_schema
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
    llm_config: dict, # For model, temperature, etc.
    # Removed schema_name and sub_schema as they are not directly used for generation prompt
) -> Optional[str]:
    """
    Async: Generates a readable three-paragraph text summary from structured JSON data about a company.

    Args:
        company_name: The name of the company.
        structured_data: The structured company data (Python dictionary from JSON).
        openai_client: The AsyncOpenAI client.
        llm_config: Configuration for the LLM (model, temperature, etc.).

    Returns:
        A string containing the three-paragraph summary, or None if generation fails.
    """
    if not structured_data:
        logger.warning(f"No structured data provided for {company_name} to generate text summary.")
        return "Error: No structured data to summarize."

    # Model for text synthesis - gpt-4o-mini should be good, or gpt-4-turbo for higher quality
    model_name = llm_config.get('model_for_summary', llm_config.get('model', "gpt-4o-mini")) 
    # Allow specifying a different model for summarization in llm_config, fallback to main model or default

    try:
        # Serialize the structured data to a compact JSON string for the prompt
        # Using ensure_ascii=False and indent=None for a more compact representation in the prompt
        json_input_for_prompt = json.dumps(structured_data, ensure_ascii=False, indent=None)
    except TypeError as e:
        logger.error(f"Failed to serialize structured_data for {company_name}: {e}")
        return f"Error: Could not serialize structured data for {company_name}."

    system_prompt_content = (
        "You are a skilled business writer specializing in synthesizing structured data into concise, professional company profiles. "
        "Your output must be a three-paragraph summary in English, based ONLY on the provided JSON data. "
        "Do not add external information or speculate. Adhere strictly to the three-paragraph format with formal language."
    )

    # Construct user prompt with the JSON data and formatting instructions
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
- Spell out acronyms on first use if their full form is available in the JSON (e.g., if JSON has ARR: \"Annual Recurring Revenue\", use it fully first time).

Paragraph Structure Guide (use the data fields mentioned if available in the JSON):
1.  Paragraph 1: Focus on fundamental company details (e.g., from JSON fields like company_name, founding_year, headquarters_city, headquarters_country, founders, ownership_background).
2.  Paragraph 2: Detail core business aspects (e.g., from JSON fields like core_products_services, underlying_technologies, customer_types, industries_served, geographic_markets).
3.  Paragraph 3: Cover operational and strategic highlights (e.g., from JSON fields like financial_details, employee_count, major_clients_or_case_studies, strategic_initiatives, key_competitors_mentioned, and a concluding sentence perhaps based on overall_summary).
"""

    messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": user_prompt_content}
    ]

    api_params = {
        "model": model_name,
        "messages": messages,
        "temperature": llm_config.get("temperature_for_summary", llm_config.get("temperature", 0.5)), # Allow specific temp for summary
        "top_p": llm_config.get("top_p_for_summary", llm_config.get("top_p", 0.9)),
        "max_tokens": llm_config.get("max_tokens_for_summary", 1000) # Adjust as needed for 3 paragraphs
        # No response_format here, as we want natural text output
    }

    logger.info(f"Attempting to generate three-paragraph summary for {company_name} using model {model_name}.")
    try:
        response = await openai_client.chat.completions.create(**api_params)
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            text_summary = response.choices[0].message.content.strip()
            # Basic check for three paragraphs (count double newlines, or single if paragraphs are tight)
            # This is a simple heuristic.
            paragraph_separators = text_summary.count("\n\n") # Common separation
            if paragraph_separators < 1 and len(text_summary.split('\n')) > 3 : # Heuristic for tightly packed paragraphs
                 paragraph_separators = text_summary.count("\n") - (len(text_summary.split('\n')) -1) // 2 # rough approx
            
            if paragraph_separators >= 2 or (paragraph_separators == 1 and len(text_summary.split('\n')) == 3): # crude check for 3 paragraphs
                logger.info(f"Successfully generated three-paragraph summary for {company_name} (Length: {len(text_summary)}).")
            else:
                logger.warning(f"Generated summary for {company_name} might not be exactly three paragraphs (Found ~{paragraph_separators + 1} blocks). Length: {len(text_summary)}. Review output.")
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

# Make sure the previous schemas and extract_data_with_schema are defined above this.
# COMPANY_PROFILE_SCHEMA and sub-schemas should be defined above.
# async def get_embedding_async ...
# async def is_url_company_page_llm ...
# async def extract_data_with_schema ... 