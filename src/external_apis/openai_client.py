import json
import time
from openai import AsyncOpenAI

async def generate_description_openai_async(company_name: str, homepage_root: str | None, linkedin_url: str | None, about_snippet: str | None, llm_config: dict, openai_client: AsyncOpenAI, context_text: str | None) -> dict | str | None:
    """Async: Generates LLM output using the structure and params from ONE llm_config file."""
    if not about_snippet: print(f"No text for LLM input ({company_name})."); return None
    if not llm_config or not isinstance(llm_config, dict): print(f"Invalid LLM config ({company_name})."); return None
    model_name = llm_config.get('model')
    if not model_name: print(f"LLM model missing in config ({company_name})."); return None

    # --- Prepare Messages --- 
    messages_template = llm_config.get('messages')
    if not isinstance(messages_template, list):
        print(f"LLM config missing/invalid 'messages' list ({company_name})."); return None
        
    formatted_messages = []
    format_data = {
        "company": company_name, 
        "website_url": homepage_root or "N/A", 
        "linkedin_url": linkedin_url or "N/A", 
        "about_snippet": about_snippet[:4000],
        "user_provided_context": context_text or "Not provided"
    }
    try:
        for msg_template in messages_template:
            if isinstance(msg_template, dict) and 'role' in msg_template and 'content' in msg_template:
                formatted_content = msg_template['content'].format(**format_data)
                formatted_messages.append({"role": msg_template['role'], "content": formatted_content})
            else: print(f"Warning: Invalid message template item in llm_config ({company_name})")
    except KeyError as e: print(f"Msg template formatting error ({company_name}): Missing key {e}"); return None
    except Exception as fmt_err: print(f"Msg template formatting error ({company_name}): {fmt_err}"); return None

    # --- Prepare API Parameters --- 
    api_params = {k: v for k, v in llm_config.items() if k != 'messages'}
    api_params['model'] = model_name
    api_params['messages'] = formatted_messages
    
    # --- Call OpenAI API --- 
    try:
        response = await openai_client.chat.completions.create(**api_params)
        if response.choices:
            response_content = response.choices[0].message.content.strip()
            response_format = api_params.get("response_format")
            if isinstance(response_format, dict) and response_format.get("type") == "json_object":
                try: parsed_json = json.loads(response_content); return parsed_json
                except json.JSONDecodeError: print(f"Error: OpenAI response not valid JSON ({company_name})."); return None 
            else: return response_content 
        else: print(f"OpenAI no choices ({company_name})."); return None 
    except Exception as e: print(f"OpenAI API error ({company_name}): {type(e).__name__}"); return None 