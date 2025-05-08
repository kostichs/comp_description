import asyncio
import aiohttp
import os
import json
import time
import traceback
import tldextract
from urllib.parse import urlparse
import re # For keyword extraction from context
from bs4 import BeautifulSoup
import logging # Added for logging

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
from .external_apis.openai_client import generate_description_openai_async, get_embedding_async, is_url_company_page_llm # Added is_url_company_page_llm
from .processing import (validate_page, 
                         extract_text_for_description, 
                         extract_definitive_url_from_html, 
                         parse_linkedin_about_section_flexible,
                         find_and_scrape_about_page_async) # Added find_and_scrape_about_page_async

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

async def process_company(company_name: str, 
                          aiohttp_session: aiohttp.ClientSession, 
                          sb_client: ScrapingBeeClient, 
                          llm_config: dict, 
                          openai_client: AsyncOpenAI,
                          context_text: str | None, 
                          serper_api_key: str | None) -> dict:
    """Async: Processes a single company. Returns a dictionary for the output row."""
    logging.info(f"Starting async process for: {company_name} (Context: {bool(context_text)})")
    start_time = time.time()
    result_data = {"name": company_name, "homepage": "Not found", "linkedin": "Not found", "description": ""}
    text_src = None
    manual_check_flag = False 
    hp_url_found_serper = None # Store URL from Serper separately
    li_url_found_serper = None
    definitive_hp_url_from_meta = None
    page_validated_for_text_extraction = False
    hp_data = None # To store (title, root_domain, html_content) from homepage scrape
    hp_root = None

    try:
        # --- 1. Find URLs using Serper API ---
        hp_url_found_serper, li_url_found_serper = await find_urls_with_serper_async(
            aiohttp_session, company_name, context_text, serper_api_key, openai_client, logging.getLogger(__name__)
        )
        result_data["homepage"] = hp_url_found_serper if hp_url_found_serper else "Not found"
        result_data["linkedin"] = li_url_found_serper if li_url_found_serper else "Not found"

        if not hp_url_found_serper:
            logging.warning(f"  > {company_name}: No homepage URL found by Serper. Cannot proceed with scraping.")
            manual_check_flag = True
        else:
            logging.info(f"  > {company_name}: Homepage URL from Serper: {hp_url_found_serper}")
            
            # --- 2. Scrape Homepage (if URL found) ---
            try:
                logging.info(f"  > {company_name}: Attempting to scrape homepage: {hp_url_found_serper}")
                # Use the async wrapper for ScrapingBee
                hp_data = await scrape_page_data_async(hp_url_found_serper, sb_client)
                if hp_data and hp_data[2]: # Check if HTML content exists
                    hp_root = hp_data[1]
                    logging.info(f"  > {company_name}: Homepage scraped successfully. Title: '{hp_data[0]}', Root: {hp_root}, HTML length: {len(hp_data[2]) if hp_data[2] else 0}")
                    
                    # --- 2b. Attempt to find and scrape 'About Us' page --- 
                    logging.info(f"  > {company_name}: Attempting to find and scrape 'About Us' page from homepage content...")
                    about_page_text = await find_and_scrape_about_page_async(
                        main_page_html=hp_data[2], 
                        main_page_url=hp_url_found_serper, 
                        session=aiohttp_session, 
                        sb_client=sb_client, 
                        logger_obj=logging.getLogger(__name__)
                    )

                    if about_page_text and len(about_page_text) > 100: # Basic check for meaningful text
                        logging.info(f"  > {company_name}: Successfully extracted text from 'About Us' page (length: {len(about_page_text)}). Using this for description.")
                        text_src = about_page_text
                        page_validated_for_text_extraction = True # Assume about page is valid if text is good
                    else:
                        logging.warning(f"  > {company_name}: Could not get meaningful text from 'About Us' page (or page not found). Falling back to homepage content.")
                        # Fallback to extracting from homepage if 'About Us' page failed
                        text_src = extract_text_for_description(hp_data[2])
                        if text_src:
                            logging.info(f"  > {company_name}: Text extracted from homepage (length: {len(text_src)}). Validating page...")
                            page_validated_for_text_extraction = validate_page(company_name, hp_data[0], hp_root, hp_data[2], original_url=hp_url_found_serper)
                            if page_validated_for_text_extraction:
                                logging.info(f"  > {company_name}: Homepage validated successfully for text extraction.")
                            else:
                                logging.warning(f"  > {company_name}: Homepage validation FAILED. Text from homepage might not be relevant: '{text_src[:200]}...'")
                                text_src = None # Discard text if page not validated
                        else:
                            logging.warning(f"  > {company_name}: No text could be extracted from homepage for description.")

                else:
                    logging.warning(f"  > {company_name}: Failed to scrape homepage or no HTML content found.")
                    manual_check_flag = True
            except Exception as e_scrape:
                logging.error(f"  > {company_name}: CRITICAL - Error during homepage scraping or 'About Us' processing for {hp_url_found_serper}: {type(e_scrape).__name__} - {e_scrape}")
                logging.debug(traceback.format_exc())
                manual_check_flag = True

        # --- 3. Generate Description using LLM (if validated text source exists) ---
        llm_generated_output = None
        if text_src and page_validated_for_text_extraction:
            logging.info(f"  > {company_name}: Validated text source found (length: {len(text_src)}), generating LLM description...")
            try:
                 llm_generated_output = await generate_description_openai_async(
                     openai_client=openai_client, 
                     llm_config=llm_config, 
                     company_name=company_name, 
                     about_snippet=text_src, # The extracted text (either from About page or fallback Homepage)
                     homepage_root=hp_root, # Pass the root domain if homepage was scraped
                     linkedin_url=li_url_found_serper, # Pass the LinkedIn URL found by Serper
                     context_text=context_text # Pass the context text
                 )
                 if llm_generated_output:
                     result_data["description"] = llm_generated_output
                     logging.info(f"  > {company_name}: LLM description generated successfully (length {len(result_data['description'])}).")
                 else:
                     logging.warning(f"  > {company_name}: LLM description generation returned empty or None.")
                     manual_check_flag = True # If LLM fails, might need manual check
            except Exception as e_llm:
                logging.error(f"  > {company_name}: CRITICAL - Error during LLM description generation: {type(e_llm).__name__} - {e_llm}")
                logging.debug(traceback.format_exc())
                manual_check_flag = True
        elif text_src and not page_validated_for_text_extraction:
            logging.warning(f"  > {company_name}: Text source was available but page was NOT validated. LLM description will not be generated. Text preview: '{text_src[:200]}...'")
            manual_check_flag = True
        else: # No text_src
            logging.warning(f"  > {company_name}: No usable text source found. LLM description cannot be generated.")
            manual_check_flag = True
            
        if manual_check_flag:
            result_data["description"] = result_data.get("description") or "Manual check required"

    except Exception as e_outer:
        logging.critical(f"CRITICAL ERROR processing {company_name}: {type(e_outer).__name__} - {e_outer}")
        logging.debug(traceback.format_exc())
        result_data["description"] = "Error in processing - check logs"
        # Ensure homepage/linkedin are not overwritten if found before this outer error
        result_data["homepage"] = hp_url_found_serper if hp_url_found_serper else result_data.get("homepage", "Error")
        result_data["linkedin"] = li_url_found_serper if li_url_found_serper else result_data.get("linkedin", "Error")
    
    processing_time = time.time() - start_time
    logging.info(f"Finished processing {company_name} in {processing_time:.2f} seconds. Result: Homepage: '{result_data['homepage']}', LI: '{result_data['linkedin']}', Desc len: {len(result_data['description']) if result_data['description'] else 0}")
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
    base_ordered_fields = ["name", "homepage", "linkedin", "description"]
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
                        process_company(name, session, sb_client, llm_config, openai_client, current_run_context, serper_api_key)
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
                        task_exc_company_name = "UnknownCompanyInFailedTask" # Placeholder
                        # Attempt to find company name if task stored it, this is a bit complex with asyncio exceptions
                        # For now, using a placeholder
                        logging.error(f"Task for company '{task_exc_company_name}' in {filename} failed: {type(e).__name__} - {e}")
                        # traceback.print_exc(file=open(log_file_path, 'a')) # Already done in process_company
                        exceptions_in_current_file += 1
                        # Optionally save an error entry to CSV
                        # error_entry = {"name": task_exc_company_name, "description": f"Processing Error: {type(e).__name__}"}
                        # for field in expected_csv_fieldnames: # Ensure all fields exist for DictWriter
                        #    if field not in error_entry: error_entry[field] = "ERROR_STATE"
                        # save_results_csv([error_entry], output_file_path, append_mode=True, fieldnames=expected_csv_fieldnames)
                
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

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try: asyncio.run(run_pipeline())
    except KeyboardInterrupt: logging.warning("\nProcessing interrupted.")
    except Exception as e: logging.error(f"\nUnexpected error in main async exec: {e}"); traceback.print_exc() 