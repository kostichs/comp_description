import asyncio
import aiohttp
import os
import json
import time
import traceback
import tldextract
from urllib.parse import urlparse, unquote
import re # For keyword extraction from context
from bs4 import BeautifulSoup
import logging # Added for logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from scrapingbee import ScrapingBeeClient # Need sync client for thread
from openai import AsyncOpenAI

# Import functions from other modules in the src package
from .config import load_llm_config, load_env_vars
from .data_io import (load_and_prepare_company_names, 
                      load_context_file, 
                      save_context_file, 
                      save_results_csv)
from .external_apis.serper_client import find_urls_with_serper_async
from .external_apis.scrapingbee_client import scrape_page_data_async # Use the async wrapper
from .external_apis.openai_client import (
    extract_data_with_schema, # Renamed/New function
    generate_text_summary_from_json_async, # Added new function
    BASIC_INFO_SCHEMA, 
    PRODUCT_TECH_SCHEMA, 
    MARKET_CUSTOMER_SCHEMA, 
    FINANCIAL_HR_SCHEMA, 
    STRATEGIC_SCHEMA,
    # Keep other imports like get_embedding_async, is_url_company_page_llm if used elsewhere
    get_embedding_async, 
    is_url_company_page_llm
)
from .processing import (validate_page, 
                         extract_text_for_description, 
                         extract_definitive_url_from_html, 
                         parse_linkedin_about_section_flexible,
                         find_and_scrape_about_page_async,
                         get_wikipedia_summary_async) # Added get_wikipedia_summary_async

# ++ Импорт для LLM Deep Search ++
from .llm_deep_search import query_llm_for_deep_info

# --- Setup Logging --- 
# Remove any existing handlers for the root logger
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Configure logging to file and console
# Ensure output directory exists for the log file
if not os.path.exists("output"):
    os.makedirs("output")

# Define logs directory and ensure it exists
logs_base_dir = os.path.join("output", "logs")
if not os.path.exists(logs_base_dir):
    os.makedirs(logs_base_dir)
    logging.info(f"Created logs directory: {logs_base_dir}") # Log this creation via a temporary basicConfig or print

# Generate unique log file names with timestamp inside the logs_base_dir
run_timestamp = time.strftime("%Y%m%d_%H%M%S")
log_file_path = os.path.join(logs_base_dir, f"pipeline_run_{run_timestamp}.log")
scoring_log_file_path = os.path.join(logs_base_dir, f"scoring_details_{run_timestamp}.log")

# Temporarily configure basic logging just to capture the logs_base_dir creation if it happens
# This will be overridden by the main basicConfig below.
# Alternatively, use print() for the very first log message if basicConfig isn't set up yet.
# For simplicity, the main basicConfig will handle subsequent logging.

logging.basicConfig( # This might reconfigure if called after another basicConfig, ensure it's the primary one or handle carefully.
    level=logging.DEBUG, # Main log level for console and general file logging
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, mode='w', encoding='utf-8'), # mode='w' to create new file each run
        logging.StreamHandler() # To console
    ]
)

# Separate logger for detailed scoring, only to a specific file
scoring_logger = logging.getLogger('ScoringLogger')
scoring_logger.setLevel(logging.DEBUG)
scoring_logger.propagate = False 

# Remove existing handlers for scoring_logger if any (to be sure before adding new one)
for handler in scoring_logger.handlers[:]:
    scoring_logger.removeHandler(handler)
    
# Add a specific handler for scoring_logger with the unique file name
fh_scoring = logging.FileHandler(scoring_log_file_path, mode='w', encoding='utf-8') # mode='w'
fh_scoring.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
scoring_logger.addHandler(fh_scoring)
# --- End Logging Setup ---

async def process_company(
    company_name: str, 
    aiohttp_session: aiohttp.ClientSession, 
    sb_client: ScrapingBeeClient, 
    llm_config: dict, 
    openai_client: AsyncOpenAI,
    context_text: str | None, 
    serper_api_key: str | None,
    run_standard_pipeline: bool = True,
    run_llm_deep_search_pipeline: bool = False,
    llm_deep_search_config: Optional[Dict[str, Any]] = None,
    session_dir_path: Optional[Path] = None 
) -> dict:
    """Async: Processes a single company. Returns a dictionary for the output row."""
    pipeline_logger = logging.getLogger(__name__)
    pipeline_logger.info(f"Starting process for: {company_name} (Std: {run_standard_pipeline}, Deep: {run_llm_deep_search_pipeline}) Context: {bool(context_text)}")
    start_time_processing = time.time()
    
    current_date_iso = datetime.now().strftime("%Y-%m-%d")

    result_data = {
        "name": company_name,
        "homepage": "Not found", 
        "linkedin": "Not found", 
        "description": "Description generation failed or yielded no data.", # Default/fallback
        "timestamp": current_date_iso
    }
    
    hp_url_found_serper: str | None = None
    li_url_found_serper: str | None = None 
    li_snippet_serper: str | None = None 
    wiki_url_found_serper: str | None = None
    hp_html_content: str | None = None
    hp_title: str | None = None
    hp_root: str | None = None
    about_page_text: str | None = None
    wiki_summary: str | None = None
    hp_text_for_llm: str | None = None
    text_src_for_llms: str = "" 
    manual_check_flag: bool = False

    try:
        # --- STEP 0: URL Finding & Standard Text Collection --- 
        # (This section needs your full existing logic for finding URLs and scraping 
        # homepage, about_us, wikipedia to populate text_src_for_llms)
        # For this diff, we'll assume text_src_for_llms is populated by these prior steps.
        # Example of how it might start:
        hp_url_found_serper, li_url_found_serper, li_snippet_serper, wiki_url_found_serper = None, None, None, None
        hp_html_content, about_page_text, wiki_summary, hp_text_for_llm = None, None, None, None

        if run_standard_pipeline or run_llm_deep_search_pipeline: # Serper call if any pipeline part needs URLs
            serper_urls_tuple = await find_urls_with_serper_async(
                aiohttp_session, company_name, context_text, serper_api_key, openai_client, pipeline_logger
            )
            if serper_urls_tuple:
                hp_url_found_serper, li_url_found_serper, li_snippet_serper, wiki_url_found_serper = serper_urls_tuple
        
        # ... [YOUR FULL EXISTING TEXT COLLECTION LOGIC HERE to populate text_src_for_llms
        # using hp_url_found_serper, li_url_found_serper, etc. via scraping and Wikipedia lookups]
        # This logic will form the base `text_src_for_llms`
        # For example, a simplified aggregation:
        temp_texts = []
        # if about_page_text: temp_texts.append(about_page_text)
        # if wiki_summary: temp_texts.append(wiki_summary)
        # if hp_text_for_llm: temp_texts.append(hp_text_for_llm) 
        # text_src_for_llms = "\n\n---\n\n".join(temp_texts) 
        # Placeholder if no specific content found after scraping efforts
        if not text_src_for_llms:
             text_src_for_llms = f"Collected information for {company_name}. Please extract relevant details." 
             pipeline_logger.info(f"  > {company_name}: text_src_for_llms was initially empty, using placeholder.")
        # --- END OF SIMULATED TEXT COLLECTION --- 

        # --- Update homepage/linkedin in result_data based on standard pipeline flag ---
        if run_standard_pipeline:
            # ... (logic to populate result_data["homepage"] and result_data["linkedin"] as before)
            if hp_url_found_serper: result_data["homepage"] = hp_url_found_serper # Simplified, use your existing parsing
            if li_url_found_serper: result_data["linkedin"] = li_url_found_serper # Simplified
        else:
            result_data["homepage"] = "Standard URL fetch not run"
            result_data["linkedin"] = "Standard URL fetch not run"

        # --- LLM DEEP SEARCH (if enabled, augments text_src_for_llms) ---
        if run_llm_deep_search_pipeline:
            pipeline_logger.info(f"  > {company_name}: Running LLM DEEP SEARCH to augment information context...")
            aspects_for_deep_search_report = []
            if llm_deep_search_config and "specific_queries" in llm_deep_search_config:
                aspects_for_deep_search_report = llm_deep_search_config.get("specific_queries", [])
            
            deep_search_result_dict = await query_llm_for_deep_info(
                openai_client=openai_client,
                company_name=company_name,
                specific_aspects_to_cover=aspects_for_deep_search_report,
                user_context_text=context_text
            )

            llm_report_text: Optional[str] = None
            llm_report_sources: List[Dict[str, str]] = []

            if "error" in deep_search_result_dict:
                error_message = deep_search_result_dict["error"]
                pipeline_logger.warning(f"  > {company_name}: LLM Deep Search problem: {error_message}")
                text_src_for_llms += f"\n\n--- LLM Deep Search Status: {error_message} ---"
            else:
                llm_report_text = deep_search_result_dict.get("report_text")
                llm_report_sources = deep_search_result_dict.get("sources", [])
                if llm_report_text:
                    text_src_for_llms += f"\n\n--- LLM Deep Search Report ---\n{llm_report_text}"
                    pipeline_logger.info(f"  > {company_name}: LLM Deep Search report text appended to context for JSON extraction.")
                else:
                    pipeline_logger.warning(f"  > {company_name}: LLM Deep Search returned no report text.")
                    text_src_for_llms += f"\n\n--- LLM Deep Search Status: No report text returned ---"

                # --- SAVE LLM DEEP SEARCH RAW REPORT TO MARKDOWN ---
                if llm_report_text and session_dir_path:
                    try:
                        md_reports_dir = session_dir_path / "md_reports"
                        md_reports_dir.mkdir(parents=True, exist_ok=True)
                        
                        safe_filename = re.sub(r'[^\w\-_\.]', '_', company_name)
                        if not safe_filename: safe_filename = "unnamed_company"
                        md_file_path = md_reports_dir / f"{safe_filename[:100]}_deep_search.md"

                        md_content = f"# LLM Deep Search Report for {company_name}\n\n"
                        md_content += f"## Full Report Text (Context)\n\n{llm_report_text}\n\n"
                        
                        if llm_report_sources:
                            md_content += "## Sources\n\n"
                            for idx, source in enumerate(llm_report_sources):
                                title = source.get("title", "N/A")
                                url = source.get("url", "N/A")
                                md_content += f"*   **Source {idx + 1}:** [{title}]({url})\n"
                        else:
                            md_content += "## Sources\n\nNo sources provided by LLM.\n"
                        
                        with open(md_file_path, 'w', encoding='utf-8') as f_md:
                            f_md.write(md_content)
                        pipeline_logger.info(f"  > {company_name}: Successfully saved LLM Deep Search raw report to {md_file_path}")
                    except Exception as e_save_md:
                        pipeline_logger.error(f"  > {company_name}: Failed to save LLM Deep Search raw report to Markdown: {e_save_md}")

        # --- FINAL STRUCTURED JSON GENERATION (Iterative Schema Extraction) --- 
        pipeline_logger.info(f"  > {company_name}: Starting iterative JSON extraction from combined text (len: {len(text_src_for_llms)})...")
        
        final_structured_json = {}
        extraction_error_occurred = False

        schemas_to_extract = [
            ("BasicInfo", BASIC_INFO_SCHEMA),
            ("ProductTechInfo", PRODUCT_TECH_SCHEMA),
            ("MarketCustomerInfo", MARKET_CUSTOMER_SCHEMA),
            ("FinancialHRInfo", FINANCIAL_HR_SCHEMA),
            ("StrategicInfo", STRATEGIC_SCHEMA)
        ]

        if not text_src_for_llms:
            pipeline_logger.error(f"  > {company_name}: No text available in text_src_for_llms for structured JSON generation. Aborting JSON extraction.")
            result_data["description"] = "Error: No text content available for JSON extraction."
            # return result_data # Early exit or proceed to fill with errors/nulls?
            # For now, we will let it try to generate from empty/placeholder which will likely result in nulls.
            text_src_for_llms = f"No specific information found for {company_name} from scraping or deep search. Attempting to populate schema based on company name only."

        for schema_name_suffix, sub_schema_dict in schemas_to_extract:
            schema_extraction_name = f"company_{schema_name_suffix.lower()}_extraction"
            pipeline_logger.info(f"  > {company_name}: Extracting with schema: {schema_extraction_name}")
            
            extracted_part = await extract_data_with_schema(
                company_name=company_name,
                about_snippet=text_src_for_llms, 
                sub_schema=sub_schema_dict,
                schema_name=schema_extraction_name,
                llm_config=llm_config, 
                openai_client=openai_client
            )

            if extracted_part and not extracted_part.get("error"):
                final_structured_json.update(extracted_part)
                pipeline_logger.info(f"  > {company_name}: Successfully extracted and updated with {schema_extraction_name}.")
            else:
                extraction_error_occurred = True
                error_detail = extracted_part.get("error", "Unknown extraction error") if extracted_part else "No data returned from extraction"
                pipeline_logger.error(f"  > {company_name}: Failed to extract/update with {schema_extraction_name}. Error: {error_detail}")
                # Add placeholder for this part of the schema to indicate failure
                for key in sub_schema_dict.get("properties", {}).keys():
                    if key not in final_structured_json:
                         final_structured_json[key] = f"Error extracting {schema_name_suffix}"
        
        if not final_structured_json or extraction_error_occurred:
            pipeline_logger.error(f"  > {company_name}: Final structured JSON is empty or errors occurred during extraction. Storing error message.")
            result_data["description"] = json.dumps({"error": "Failed to generate complete structured company profile", "details": final_structured_json}, ensure_ascii=False, indent=2)
            manual_check_flag = True
        else:
            try:
                result_data["description"] = json.dumps(final_structured_json, ensure_ascii=False, indent=2)
                pipeline_logger.info(f"  > {company_name}: Successfully generated and stringified final structured JSON description.")
            except TypeError as e:
                pipeline_logger.error(f"  > {company_name}: Failed to serialize final structured JSON to string: {e}. Storing error.")
                result_data["description"] = json.dumps({"error": f"Serialization failed: {str(e)}", "partial_data": "Data may be incomplete or malformed"}, ensure_ascii=False, indent=2)
                manual_check_flag = True

        # --- SAVE THE INDIVIDUAL COMPANY JSON --- 
        if session_dir_path and final_structured_json: # Only save if we have data and a path
            try:
                json_details_dir = session_dir_path / "json_details"
                json_details_dir.mkdir(parents=True, exist_ok=True) # Create subdir if not exists
                
                # Sanitize company name for filename
                safe_filename = re.sub(r'[^\w\-_\.]', '_', company_name) # Replace non-alphanumeric/hyphen/underscore/dot with underscore
                if not safe_filename: safe_filename = "unnamed_company"
                json_file_path = json_details_dir / f"{safe_filename[:100]}.json" # Limit filename length

                with open(json_file_path, 'w', encoding='utf-8') as f_json:
                    json.dump(final_structured_json, f_json, ensure_ascii=False, indent=2)
                pipeline_logger.info(f"  > {company_name}: Successfully saved structured JSON to {json_file_path}")
            except Exception as e_save_json:
                pipeline_logger.error(f"  > {company_name}: Failed to save individual company JSON: {e_save_json}")

        # --- GENERATE TEXT SUMMARY FROM THE ASSEMBLED JSON --- 
        if not final_structured_json or extraction_error_occurred:
            pipeline_logger.error(f"  > {company_name}: Structured JSON is empty or errors occurred. Storing error/partial JSON in description.")
            result_data["description"] = json.dumps(final_structured_json if final_structured_json else {"error": "No data extracted for summary generation"}, ensure_ascii=False, indent=2)
        else:
            pipeline_logger.info(f"  > {company_name}: Successfully assembled structured JSON. Generating final text summary...")
            text_summary = await generate_text_summary_from_json_async(
                company_name=company_name,
                structured_data=final_structured_json,
                openai_client=openai_client,
                llm_config=llm_config 
            )

            if text_summary and not text_summary.startswith("Error:"):
                # Corrected logging for raw summary
                replacement_marker = "[NL]"
                loggable_summary = text_summary.replace('\n', replacement_marker)
                pipeline_logger.info(f"  > {company_name}: Raw text_summary from LLM (newlines as {replacement_marker}): {loggable_summary}")
                
                result_data["description"] = text_summary 
                pipeline_logger.info(f"  > {company_name}: Successfully generated text summary (length: {len(text_summary)}).")
            else:
                pipeline_logger.error(f"  > {company_name}: Failed to generate three-paragraph text summary. Fallback: {text_summary}. Storing structured JSON instead.")
                result_data["description"] = json.dumps(final_structured_json, ensure_ascii=False, indent=2)

    except asyncio.CancelledError:
        pipeline_logger.warning(f"Processing of company '{company_name}' was cancelled.")
        result_data["description"] = result_data.get("description", "Processing cancelled")
        raise
    except Exception as e_outer:
        pipeline_logger.critical(f"CRITICAL OUTER ERROR processing {company_name}: {type(e_outer).__name__} - {e_outer}", exc_info=True)
        result_data["description"] = json.dumps({"error": f"Outer critical error: {type(e_outer).__name__} - {str(e_outer)}"}, ensure_ascii=False, indent=2)

    processing_duration = time.time() - start_time_processing
    pipeline_logger.info(f"Finished processing {company_name} in {processing_duration:.2f}s. Desc type: {type(result_data.get('description'))}")
    return result_data


async def run_pipeline():
    """Main asynchronous pipeline orchestration."""
    
    # Log a separator for new run for better readability of appended logs (now less critical as files are unique)
    # run_start_time_str = time.strftime("%Y-%m-%d %H:%M:%S") # Already used for filename
    logging.info(f"\n{'='*30} PIPELINE RUNNING (Log file: {os.path.basename(log_file_path)}) {'='*30}")
    scoring_logger.info(f"\n{'='*30} SCORING SESSION (Log file: {os.path.basename(scoring_log_file_path)}) {'='*30}")

    input_dir = "input"
    output_dir = "output"
    final_output_dir = os.path.join(output_dir, "final_outputs") 
    llm_config_file = "llm_config.yaml" 
    company_col_index = 0 

    # --- Create Directories --- 
    for dir_path in [output_dir, final_output_dir]: 
        if not os.path.exists(dir_path):
            os.makedirs(dir_path); logging.info(f"Created directory: {dir_path}")
            
    # --- Load Configs and Keys --- 
    logging.info("Loading configurations and API keys...")
    scrapingbee_api_key, openai_api_key, serper_api_key = load_env_vars()
    if not all([scrapingbee_api_key, openai_api_key, serper_api_key]):
        logging.critical("Exiting due to missing API keys.") 
        return # Changed from exit() to return for better testability if needed
        
    llm_config = load_llm_config(llm_config_file) 
    if not llm_config: 
        logging.critical(f"Failed to load LLM config from {llm_config_file}. Exiting."); 
        return # Changed from exit()

    # --- Define expected CSV fieldnames --- 
    base_ordered_fields = ["name", "homepage", "linkedin", "description", "timestamp"]
    # llm_error убрано из базовых. Ошибки LLM будут в логах и, возможно, в поле description.
    
    additional_llm_fields = []
    if isinstance(llm_config.get("response_format"), dict) and \
       llm_config["response_format"].get("type") == "json_object":
        try:
            if "expected_json_keys" in llm_config: 
                llm_keys = [f"llm_{k}" for k in llm_config["expected_json_keys"]]
                additional_llm_fields.extend(llm_keys)
            else: 
                if 'messages' in llm_config and isinstance(llm_config['messages'], list) and llm_config['messages']:
                    last_message_content = llm_config['messages'][-1].get('content', '')
                    json_block_match = re.search(r"```json\s*([\s\S]*?)\s*```", last_message_content)
                    if json_block_match:
                        try:
                            example_json = json.loads(json_block_match.group(1))
                            if isinstance(example_json, dict):
                                llm_keys = [f"llm_{k}" for k in example_json.keys()]
                                additional_llm_fields.extend(llm_keys)
                                logging.info(f"Dynamically added LLM keys to CSV header: {llm_keys}")
                        except json.JSONDecodeError:
                            logging.warning("Found JSON block in LLM config, but could not parse it for keys.")
            
            # Add some default llm fields if no specific ones were found and they are not already covered
            # by base_ordered_fields (like 'description' which might be an llm output)
            default_llm_placeholders = ["llm_summary", "llm_key_points", "llm_details"]
            for f_placeholder in default_llm_placeholders:
                if f_placeholder not in base_ordered_fields and f_placeholder not in additional_llm_fields:
                    # Avoid adding if 'description' (a base field) is meant to capture one of these roles
                    # Example: if 'llm_summary' is the primary output and should go into 'description'
                    # This logic assumes 'description' is the main text output. 
                    # If llm_config produces specific fields that *replace* description, this needs adjustment.
                    is_covered_by_description = (f_placeholder == "llm_summary" or f_placeholder == "llm_details") and \
                                                "description" in base_ordered_fields
                    if not is_covered_by_description:
                         additional_llm_fields.append(f_placeholder)

        except Exception as e:
            logging.warning(f"Could not dynamically determine LLM output keys for CSV header from llm_config: {e}")
    
    # Combine base ordered fields with unique, sorted additional fields
    unique_additional_fields = sorted(list(set(additional_llm_fields) - set(base_ordered_fields)))
    expected_csv_fieldnames = base_ordered_fields + unique_additional_fields
    
    # Ensure description is there if somehow removed (it is in base_ordered_fields, so this is a safeguard)
    if "description" not in expected_csv_fieldnames: 
        if "description" in base_ordered_fields: # Should always be true
             # If it was removed from unique_additional_fields because it was in base, ensure it's back if logic was faulty
             # This path should ideally not be hit if base_ordered_fields is handled correctly.
             pass # It's in base_ordered_fields, so it will be included.
        else: # This case should not happen
            expected_csv_fieldnames.append("description")
            expected_csv_fieldnames = base_ordered_fields + sorted(list(set(expected_csv_fieldnames) - set(base_ordered_fields)))

    logging.info(f"Final CSV fieldnames will be: {expected_csv_fieldnames}")
        
    logging.info(f"Starting ASYNC batch company processing. Input: '{input_dir}', Outputs: '{final_output_dir}'")
    
    supported_extensions = ('.xlsx', '.xls', '.csv')
    overall_results = []
    processed_files_count = 0

    if not os.path.exists(input_dir): 
        logging.critical(f"Error: Input directory '{input_dir}' not found. Exiting."); 
        return # Changed from exit()
        
    logging.info("Initializing API clients...")
    sb_client = ScrapingBeeClient(api_key=scrapingbee_api_key) 
    openai_client = AsyncOpenAI(api_key=openai_api_key) 
    
    async def broadcast_update(update_data):
        # This is a placeholder for the broadcast_update function
        # It should be implemented to send updates to clients
        pass

    async with aiohttp.ClientSession() as session:
        for filename in os.listdir(input_dir):
            original_input_path = os.path.join(input_dir, filename)
            if os.path.isfile(original_input_path) and filename.lower().endswith(supported_extensions):
                logging.info(f"\n>>> Found data file: {filename}")
                base_name, _ = os.path.splitext(filename)
                
                # Use the run_timestamp (defined globally in this module where logs are set up) for output CSV names
                # This ensures output CSVs can be correlated with specific run logs.
                output_file_base_with_ts = os.path.join(final_output_dir, f"{base_name}_output_{run_timestamp}")
                output_file_path = f"{output_file_base_with_ts}.csv"
                counter = 1
                # This loop handles the extremely rare case of a filename collision even with the timestamp.
                while os.path.exists(output_file_path):
                    output_file_path = f"{output_file_base_with_ts}_{counter}.csv"
                    counter += 1
                logging.info(f"Output for this file will be: {output_file_path}")
                
                context_file_path = os.path.join(input_dir, f"{base_name}_context.txt")
                existing_context = load_context_file(context_file_path)
                current_run_context = None
                
                try:
                    prompt_message = f"\nEnter context for '{filename}'" 
                    if existing_context:
                        prompt_message += f" (Press Enter to use previous: '{existing_context[:70]}...'): "
                    else:
                        prompt_message += f" (industry, region, source...) or press Enter to skip: "
                    user_input = input(prompt_message)
                    provided_context = user_input.strip()
                    if provided_context: current_run_context = provided_context
                    elif existing_context: current_run_context = existing_context; logging.info(f"Using existing context for {filename}.")
                    else: current_run_context = None; logging.info(f"No context provided or used for {filename}.")
                    if current_run_context and current_run_context != existing_context:
                         if save_context_file(context_file_path, current_run_context): logging.info("Context saved.")
                         else: logging.error("Failed to save context.")
                except EOFError: 
                     logging.warning("\nCannot read input. Proceeding without context.")
                     current_run_context = None
                         
                company_names = load_and_prepare_company_names(original_input_path, company_col_index)
                if not company_names: 
                    logging.warning(f"--- Skipping file {filename}: No valid company names found."); 
                    continue
                
                logging.info(f"Found {len(company_names)} companies for {filename}. Processing each and saving incrementally...")
                
                current_file_successful_results = [] 
                exceptions_in_current_file = 0

                tasks = [
                    asyncio.create_task(
                        process_company(name, session, sb_client, llm_config, openai_client, current_run_context, serper_api_key,
                                        # ++ Передаем фактические значения, а не True/False по умолчанию ++
                                        # Эти значения должны приходить из run_pipeline_for_file, а run_pipeline (консольный) должен решить, какие значения использовать
                                        # Пока для run_pipeline оставим стандартный запуск
                                        run_standard_pipeline=True, # Для консольного run_pipeline всегда стандартный
                                        run_llm_deep_search_pipeline=True, # Для консольного run_pipeline пока без LLM Deep Search
                                        llm_deep_search_config={
                                            "specific_queries": [
                                                "2024 financial results",
                                                "flagship products",
                                                "competitive strategy in EMEA"
                                            ]
                                         }, # Соответственно, конфиг тоже None
                                        session_dir_path=Path(output_file_path).parent # Pass session_dir_path
                                        )
                    ) for name in company_names
                ]

                for future in asyncio.as_completed(tasks):
                    try:
                        result_data = await future
                        if isinstance(result_data, dict):
                            current_file_successful_results.append(result_data)
                            # Save/append this single result immediately
                            save_results_csv(
                                [result_data], # save_results_csv expects a list of dicts
                                output_file_path,
                                append_mode=True, # Critical for incremental saving
                                fieldnames=expected_csv_fieldnames # Provide all expected headers
                            )
                        else:
                            logging.error(f"Unexpected result type for a company in {filename}: {type(result_data)}")
                            exceptions_in_current_file += 1
                            # Optionally save a placeholder or error entry to CSV for this failed task
                            # save_results_csv([{"name": "UNKNOWN_FROM_FAILED_TASK", "description": f"Error: Unexpected type {type(result_data)}"}], 
                            # output_file_path, append_mode=True, fieldnames=expected_csv_fieldnames)

                    except Exception as e:
                        task_exc_company_name = "UnknownCompanyInFailedTask" 
                        # ... (логирование ошибки) ...
                        exceptions_in_current_file += 1
                        
                        # Формируем error_result и добавляем его в current_file_successful_results
                        error_result = {"name": task_exc_company_name, "homepage": "Error", "linkedin": "Error", "description": f"Processing Error: {type(e).__name__}"}
                        if "timestamp" in expected_csv_fieldnames: # Добавляем timestamp, если он ожидается
                            error_result["timestamp"] = datetime.now().strftime("%Y-%m-%d")
                        
                        # Гарантируем, что все ожидаемые поля присутствуют, даже если с заглушкой "ERROR_STATE"
                        for field in expected_csv_fieldnames:
                           if field not in error_result: error_result[field] = "ERROR_STATE"
                        current_file_successful_results.append(error_result) # <--- ИСПРАВЛЕНО ЗДЕСЬ
                        # Записываем строку с ошибкой в CSV немедленно
                        save_results_csv([error_result], output_file_path, append_mode=True, fieldnames=expected_csv_fieldnames)
                
                logging.info(f"<<< Finished incremental processing for {filename}. Successes: {len(current_file_successful_results)}, Failures: {exceptions_in_current_file}")
                if current_file_successful_results:
                    overall_results.extend(current_file_successful_results)
                    processed_files_count += 1
                else: 
                    logging.info(f"No successful results for {filename} to add to overall summary.")
            else: 
                logging.info(f"Skipping non-supported/file item: {filename}")
            
    if processed_files_count > 0:
        logging.info(f"\nSuccessfully processed {processed_files_count} file(s). Total successful results collated: {len(overall_results)}.")
        if overall_results:
            # The consolidated JSON output remains useful for a final overview / debugging
            logging.info("\n--- Consolidated JSON Output (from in-memory list, also in pipeline_run.log) ---")
            logging.info(json.dumps(overall_results, indent=2, ensure_ascii=False))
            print("\n--- Consolidated JSON Output (also in pipeline_run.log) ---")
            print(json.dumps(overall_results, indent=2, ensure_ascii=False))
            print("--- --- --- --- --- --- --- ")
    else: 
        logging.info(f"No supported files processed successfully in '{input_dir}'.")
    
    logging.info("Async batch processing finished.") 

async def run_pipeline_for_file(
    input_file_path: str | Path,
    output_csv_path: str | Path,
    pipeline_log_path: str,
    scoring_log_path: str,
    session_dir_path: Path,
    context_text: str | None,
    company_col_index: int,
    aiohttp_session: aiohttp.ClientSession,
    sb_client: ScrapingBeeClient,
    llm_config: dict,
    openai_client: AsyncOpenAI,
    serper_api_key: str,
    expected_csv_fieldnames: list[str],
    broadcast_update: callable = None,
    main_batch_size: int = 10,
    run_standard_pipeline: bool = True,
    run_llm_deep_search_pipeline: bool = False,
    llm_deep_search_config: Optional[Dict[str, Any]] = None
) -> tuple[int, int, list[dict]]:
    
    file_specific_logger = logging.getLogger(f"pipeline.session.{Path(input_file_path).stem}") 
    file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Initializing for file: {input_file_path}")
    file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Output CSV: {output_csv_path}")
    file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Received expected_csv_fieldnames AS PARAMETER: {expected_csv_fieldnames}")
    file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Main batch size: {main_batch_size}")

    overall_success_count = 0
    overall_failure_count = 0
    overall_results_list = [] 

    try:
        file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Loading company names from: {input_file_path}")
        all_company_names = load_and_prepare_company_names(input_file_path, company_col_index)
        if not all_company_names:
            file_specific_logger.warning(f"[RUN_PIPELINE_FOR_FILE] No valid company names found in {input_file_path}. Exiting.")
            return 0, 0, []
        file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Loaded {len(all_company_names)} company names.")

        total_companies_to_process = len(all_company_names)
        
        file_specific_logger.info(f"DEBUG: expected_csv_fieldnames for header in run_pipeline_for_file: {expected_csv_fieldnames}") 
        if not Path(output_csv_path).exists() or Path(output_csv_path).stat().st_size == 0:
            file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Output CSV file {output_csv_path} does not exist or is empty. Creating with headers.")
            save_results_csv([], output_csv_path, append_mode=False, fieldnames=expected_csv_fieldnames) # Используем переданный expected_csv_fieldnames
            file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Initialized CSV file with headers: {output_csv_path}")
        else:
            file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Output CSV file {output_csv_path} already exists and is not empty. Will append.")

        processed_companies_count = 0
        for i in range(0, total_companies_to_process, main_batch_size):
            company_names_batch = all_company_names[i:i + main_batch_size]
            batch_number = (i // main_batch_size) + 1
            total_batches = (total_companies_to_process + main_batch_size - 1) // main_batch_size
            file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Processing batch {batch_number}/{total_batches} ({len(company_names_batch)} companies)... ")

            tasks = [
                asyncio.create_task(
                    process_company(
                        company_name=name,
                        aiohttp_session=aiohttp_session,
                        sb_client=sb_client,
                        llm_config=llm_config,
                        openai_client=openai_client,
                        context_text=context_text,
                        serper_api_key=serper_api_key,
                        run_standard_pipeline=run_standard_pipeline,
                        run_llm_deep_search_pipeline=run_llm_deep_search_pipeline,
                        llm_deep_search_config=llm_deep_search_config,
                        session_dir_path=session_dir_path
                    )
                ) for name in company_names_batch
            ]

            batch_results_temp = []
            for future_index, future in enumerate(asyncio.as_completed(tasks)):
                current_overall_processed = processed_companies_count + future_index + 1
                if asyncio.current_task().cancelled(): # type: ignore[attr-defined]
                    file_specific_logger.warning(f"[RUN_PIPELINE_FOR_FILE] Task for run_pipeline_for_file was cancelled during batch {batch_number}. Stopping further processing of companies for {input_file_path}.")
                    for task_to_cancel in tasks:
                        if not task_to_cancel.done():
                            task_to_cancel.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    raise asyncio.CancelledError 
                
                company_name_for_log = company_names_batch[future_index] 
                try:
                    result_data = await future
                    if isinstance(result_data, dict):
                        batch_results_temp.append(result_data) 
                        file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] DEBUG: fieldnames for row in run_pipeline_for_file: {expected_csv_fieldnames}") 
                        file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] DEBUG: result_data keys for row: {list(result_data.keys())}") 
                        save_results_csv([result_data], output_csv_path, append_mode=True, fieldnames=expected_csv_fieldnames) # Используем переданный expected_csv_fieldnames
                        overall_success_count += 1
                        if broadcast_update:
                            progress_data = {
                                "type": "progress", 
                                "current_company_name": result_data.get("name"),
                                "processed_count": current_overall_processed,
                                "total_companies": total_companies_to_process
                            }
                            await broadcast_update(progress_data)
                            await broadcast_update({"type": "update", "data": result_data})
                    else:
                        file_specific_logger.error(f"[RUN_PIPELINE_FOR_FILE] Unexpected result type: {type(result_data)} for company '{company_name_for_log}' in batch {batch_number} of {input_file_path}")
                        overall_failure_count += 1
                except asyncio.CancelledError:
                    file_specific_logger.warning(f"[RUN_PIPELINE_FOR_FILE] Processing for company '{company_name_for_log}' in batch {batch_number} was cancelled.")
                    overall_failure_count += 1
                except Exception as e_task:
                    file_specific_logger.error(f"[RUN_PIPELINE_FOR_FILE] Task for company '{company_name_for_log}' in batch {batch_number} of {input_file_path} failed: {type(e_task).__name__} - {e_task}", exc_info=True)
                    overall_failure_count += 1
                    error_result = {"name": company_name_for_log, "homepage": "Error", "linkedin": "Error", "description": f"Processing Error: {type(e_task).__name__}"}
                    # Добавляем timestamp и для ошибочных записей, если он есть в expected_csv_fieldnames
                    if "timestamp" in expected_csv_fieldnames:
                        error_result["timestamp"] = datetime.now().strftime("%Y-%m-%d")
                    for field in expected_csv_fieldnames:
                        if field not in error_result: error_result[field] = "ERROR_STATE"
                    save_results_csv([error_result], output_csv_path, append_mode=True, fieldnames=expected_csv_fieldnames) # Используем переданный expected_csv_fieldnames
                    batch_results_temp.append(error_result) 
            
            overall_results_list.extend(batch_results_temp)
            processed_companies_count += len(company_names_batch)
            file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Finished batch {batch_number}/{total_batches}. Total processed so far: {processed_companies_count}/{total_companies_to_process}")
        
        file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Finished all batches for {input_file_path}. Overall Successes: {overall_success_count}, Failures: {overall_failure_count}")
        if broadcast_update:
            await broadcast_update({"type": "complete", "data": {"message": f"Processing of {Path(input_file_path).name} completed.", "success_count": overall_success_count, "failure_count": overall_failure_count, "total_companies": total_companies_to_process}})
        
        return overall_success_count, overall_failure_count, overall_results_list

    except asyncio.CancelledError: 
        file_specific_logger.info(f"[RUN_PIPELINE_FOR_FILE] Processing of file {input_file_path} was cancelled externally.")
        return overall_success_count, overall_failure_count, overall_results_list
    except Exception as e_main:
        file_specific_logger.error(f"[RUN_PIPELINE_FOR_FILE] Critical error processing file {input_file_path}: {type(e_main).__name__} - {e_main}", exc_info=True)
        if broadcast_update:
             await broadcast_update({"type": "error", "data": {"message": f"Critical error processing file {Path(input_file_path).name}: {str(e_main)}"}})
        return overall_success_count, overall_failure_count, overall_results_list


def setup_session_logging(pipeline_log_path: str, scoring_log_path: str):
    """Configures logging handlers for a specific session run."""
    # Remove existing handlers for the root logger
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
            handler.close()
    
    # Configure root logger for pipeline logs
    root_logger.setLevel(logging.DEBUG)
    pipeline_handler = logging.FileHandler(pipeline_log_path, mode='w', encoding='utf-8')
    pipeline_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'))
    root_logger.addHandler(pipeline_handler)
    
    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(console_handler)
    
    # Configure scoring logger
    scoring_logger = logging.getLogger('ScoringLogger')
    scoring_logger.setLevel(logging.DEBUG)
    scoring_logger.propagate = False
    
    # Remove existing handlers for scoring_logger
    for handler in scoring_logger.handlers[:]:
        scoring_logger.removeHandler(handler)
        handler.close()
    
    # Add scoring file handler
    scoring_handler = logging.FileHandler(scoring_log_path, mode='w', encoding='utf-8')
    scoring_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    scoring_logger.addHandler(scoring_handler)
    
    logging.info(f"Logging configured. Pipeline log: {pipeline_log_path}, Scoring log: {scoring_log_path}")

async def process_companies(file_path: str, session_dir: str, broadcast_update: callable):
    """Process all companies from a file and broadcast updates."""
    try:
        # Load company names from file
        company_names = load_and_prepare_company_names(file_path, 0)  # Assuming company name is in first column
        if not company_names:
            logging.warning("No valid company names found in file")
            return

        # Initialize API clients
        scrapingbee_api_key, openai_api_key, serper_api_key = load_env_vars()
        if not all([scrapingbee_api_key, openai_api_key, serper_api_key]):
            logging.error("Missing API keys")
            return

        sb_client = ScrapingBeeClient(api_key=scrapingbee_api_key)
        openai_client = AsyncOpenAI(api_key=openai_api_key)
        llm_config = load_llm_config("llm_config.yaml")

        # Create output CSV path
        output_csv_path = os.path.join(session_dir, "results.csv")
        
        # Process each company
        async with aiohttp.ClientSession() as session:
            for company_name in company_names:
                try:
                    # Process company
                    result = await process_company(
                        company_name=company_name,
                        aiohttp_session=session,
                        sb_client=sb_client,
                        llm_config=llm_config,
                        openai_client=openai_client,
                        context_text=None,  # No context for now
                        serper_api_key=serper_api_key,
                        # ++ Параметры для process_companies - пока стандартный запуск ++
                        run_standard_pipeline=True, 
                        run_llm_deep_search_pipeline=False,
                        llm_deep_search_config=None,
                        session_dir_path=Path(output_csv_path).parent  # Pass session_dir_path
                    )
                    
                    # Save result to CSV
                    save_results_csv([result], output_csv_path, append_mode=True)
                    
                    # Broadcast update
                    await broadcast_update({
                        "type": "update",
                        "data": result
                    })
                    
                except Exception as e:
                    logging.error(f"Error processing company {company_name}: {e}")
                    # Broadcast error
                    await broadcast_update({
                        "type": "update",
                        "data": {
                            "name": company_name,
                            "homepage": "Error",
                            "linkedin": "Error",
                            "description": f"Error in processing: {str(e)}"
                        }
                    })

        # Broadcast completion
        await broadcast_update({
            "type": "complete",
            "data": {"message": "Processing completed"}
        })

    except Exception as e:
        logging.error(f"Error in process_companies: {e}")
        # Broadcast error
        await broadcast_update({
            "type": "error",
            "data": {"message": f"Error in processing: {str(e)}"}
        })

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try: asyncio.run(run_pipeline())
    except KeyboardInterrupt: logging.warning("\nProcessing interrupted.")
    except Exception as e: logging.error(f"\nUnexpected error in main async exec: {e}"); traceback.print_exc() 