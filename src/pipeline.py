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
from .processing import validate_page, extract_text_for_description, extract_definitive_url_from_html # Added extract_definitive_url_from_html

# --- Setup Logging --- 
# Remove any existing handlers for the root logger
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Configure logging to file and console
log_file_path = os.path.join("output", "pipeline_run.log")
# Ensure output directory exists for the log file
if not os.path.exists("output"):
    os.makedirs("output")

logging.basicConfig(
    level=logging.INFO, # Main log level for console and general file logging
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, mode='a', encoding='utf-8'), # Append mode
        logging.StreamHandler() # To console
    ]
)

# Separate logger for detailed scoring, only to a specific file
scoring_log_file_path = os.path.join("output", "scoring_details.log")
scoring_logger = logging.getLogger('ScoringLogger')
scoring_logger.setLevel(logging.DEBUG)
# Prevent scoring_logger from propagating to the root logger (and thus console)
scoring_logger.propagate = False 
# Add a specific handler for scoring_logger
if not scoring_logger.handlers: # Avoid adding handler multiple times if module is reloaded
    fh_scoring = logging.FileHandler(scoring_log_file_path, mode='a', encoding='utf-8')
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
    page_validated_for_text_extraction = False # Flag to see if any page passed all checks

    try:
        # Pass scoring_logger to find_urls
        hp_url_found_serper, li_url_found_serper = await find_urls_with_serper_async(
            aiohttp_session, company_name, context_text, serper_api_key, openai_client, scoring_logger
        )
        result_data["linkedin"] = li_url_found_serper or "Not found"
        
        # Set homepage URL in result_data based on the found URL
        if hp_url_found_serper:
            try:
                parsed_url = urlparse(hp_url_found_serper)
                scheme = parsed_url.scheme; netloc = parsed_url.netloc; path = parsed_url.path
                if scheme and netloc: result_data["homepage"] = f"{scheme}://{netloc}"
                elif not scheme and (netloc or (path and '.' in path and '/' not in path)):
                     result_data["homepage"] = f"https://{netloc if netloc else path}"
                else: result_data["homepage"] = hp_url_found_serper
            except: result_data["homepage"] = hp_url_found_serper
        
        if not sb_client: 
            logging.error(f"ScrapingBee client not available for {company_name}.")
            raise ValueError("ScrapingBee client error")

        # Scrape concurrently
        scrape_tasks = {}
        if hp_url_found_serper: scrape_tasks['homepage'] = asyncio.create_task(scrape_page_data_async(hp_url_found_serper, sb_client))
        if li_url_found_serper and "linkedin.com/company/" in li_url_found_serper: 
            scrape_tasks['linkedin'] = asyncio.create_task(scrape_page_data_async(li_url_found_serper, sb_client))
        scraped_results = {}
        if scrape_tasks:
            done, _ = await asyncio.wait(scrape_tasks.values(), timeout=60) 
            for task_name, task in scrape_tasks.items():
                if task in done and not task.cancelled() and task.exception() is None: scraped_results[task_name] = task.result()
                elif task.exception(): logging.warning(f"Scrape task {task_name}({company_name}) failed: {task.exception()}")
                else: logging.warning(f"Scrape task {task_name}({company_name}) timed out.")
        hp_data = scraped_results.get('homepage')
        li_data = scraped_results.get('linkedin')

        # Process Homepage Result (using original URL for validation)
        if hp_data:
            hp_title, hp_root, hp_html = hp_data
            
            # Attempt to extract definitive URL from HTML meta tags
            if hp_html and hp_url_found_serper: # Need original URL for base in urljoin
                definitive_hp_url_from_meta = extract_definitive_url_from_html(hp_html, hp_url_found_serper)
                if definitive_hp_url_from_meta:
                    logging.info(f"  > {company_name}: Definitive HP URL found from meta/JSON-LD: {definitive_hp_url_from_meta}")
                    result_data["homepage"] = definitive_hp_url_from_meta # Override with this one
                    # If we trust this definitive URL, we might even skip some validation or LLM check
                    # For now, we continue with validation on this new URL's content
            
            # Validate using the (potentially updated) homepage URL and its content
            current_hp_to_validate = definitive_hp_url_from_meta or hp_url_found_serper
            is_hp_valid = validate_page(company_name, hp_title, hp_root, hp_html, original_url=current_hp_to_validate)
            if is_hp_valid:
                # LLM Check for homepage relevance
                logging.info(f"  > {company_name}: HP structurally valid, performing LLM check...")
                first_few_text_nodes = " ".join(BeautifulSoup(hp_html, 'html.parser').stripped_strings)
                is_hp_llm_confirmed = await is_url_company_page_llm(company_name, first_few_text_nodes[:2000], openai_client)
                if is_hp_llm_confirmed:
                    text_src = extract_text_for_description(hp_html) 
                    logging.info(f"  > {company_name}: HP validated by Structure & LLM. Text: {bool(text_src)}")
                    page_validated_for_text_extraction = True
                else:
                    logging.warning(f"  > {company_name}: HP FAILED LLM relevance check.")
                    manual_check_flag = True
            else: 
                logging.warning(f"  > {company_name}: HP structural validation FAILED (URL: {current_hp_to_validate}).")
                manual_check_flag = True
        elif hp_url_found_serper: 
             logging.warning(f"  > {company_name}: HP scrape failed/timed out for {hp_url_found_serper}.")
             manual_check_flag = True 
        else: 
             logging.info(f"  > {company_name}: HP URL not initially found."); 
             manual_check_flag = True 
        
        # LinkedIn Website Cross-Validation
        if hp_url_found_serper and li_data: 
            _, _, li_html_scraped = li_data 
            if li_html_scraped:
                soup_li = BeautifulSoup(li_html_scraped, 'html.parser')
                website_link_tag = None
                possible_selectors = ['a[data-tracking-control-name="org-about_website_button"]', 'a[href*="http"]:not([href*="linkedin.com"])']
                for selector in possible_selectors:
                    link_tag = soup_li.select_one(selector)
                    if link_tag and link_tag.get('href'): website_link_tag = link_tag; break
                if website_link_tag and website_link_tag.get('href'):
                    linkedin_site_url_raw = website_link_tag.get('href')
                    try:
                        parsed_linkedin_site_url = urlparse(linkedin_site_url_raw)
                        parsed_hp_url_found_to_compare = urlparse(hp_url_found_serper)
                        li_netloc = parsed_linkedin_site_url.netloc.replace("www.", "").strip('/')
                        hp_netloc = parsed_hp_url_found_to_compare.netloc.replace("www.", "").strip('/')
                        if li_netloc and hp_netloc and li_netloc != hp_netloc:
                            logging.warning(f"  > WARNING ({company_name}): LI website ({li_netloc}) != Serper HP ({hp_netloc}).")
                    except Exception as e_parse_compare: logging.warning(f"  > Error comparing LI site link ({linkedin_site_url_raw}): {e_parse_compare}")

        # Process LinkedIn Scraped Data (if needed & available)
        if li_data and (not text_src or manual_check_flag):
            li_title, li_domain, li_html = li_data # Use actual li_domain if needed, though often just linkedin.com
            is_li_structurally_valid = validate_page(company_name, li_title, li_domain, li_html, original_url=li_url_found_serper)
            if is_li_structurally_valid:
                # Optional: LLM Check for LinkedIn page relevance (might be overkill if title check is good)
                # print(f"  > {company_name}: LI structurally valid, (optional LLM check)...") 
                # first_few_li_text = " ".join(BeautifulSoup(li_html, 'html.parser').stripped_strings)
                # is_li_llm_confirmed = await is_url_company_page_llm(company_name, first_few_li_text[:1500], openai_client)
                # if is_li_llm_confirmed:
                if not text_src: 
                    text_src = extract_text_for_description(li_html)
                    logging.info(f"  > {company_name}: LI validated for text. Text: {bool(text_src)}")
                    page_validated_for_text_extraction = True
                if text_src: manual_check_flag = False 
                # else: # LI LLM check failed
                #     print(f"  > {company_name}: LI FAILED LLM relevance check.")
                #     if not text_src : manual_check_flag = True # If we still have no text from HP
            elif not text_src: 
                logging.warning(f"  > {company_name}: LI structural validation/text FAILED.")
                manual_check_flag = True 
        elif li_url_found_serper and (not text_src or manual_check_flag):
             logging.warning(f"  > {company_name}: LI scrape failed/timed out.")
             if not text_src: manual_check_flag = True 
             
        llm_generated_output = None
        if text_src and page_validated_for_text_extraction:
             logging.info(f" > {company_name}: Validated text source found, generating LLM description...")
             llm_generated_output = await generate_description_openai_async(company_name, result_data["homepage"], result_data["linkedin"], text_src, llm_config, openai_client, context_text)
        else:
            logging.info(f" > {company_name}: No validated text source for LLM."); manual_check_flag = True 
        
        if isinstance(llm_generated_output, dict):
            logging.info(f" > {company_name}: LLM OK (JSON).")
            result_data.pop('description', None) 
            result_data.update({f"llm_{k}": v for k, v in llm_generated_output.items() if k != 'error'}) 
            if "error" in llm_generated_output: 
                result_data['description'] = f"LLM Error: {llm_generated_output['error']}"; manual_check_flag = True 
        elif isinstance(llm_generated_output, str):
            logging.info(f" > {company_name}: LLM OK (Text).")
            result_data['description'] = llm_generated_output
            if isinstance(llm_config.get("response_format"), dict) and llm_config["response_format"].get("type") == "json_object":
                logging.warning(" > Warning: Expected JSON, got Text."); manual_check_flag = True
        elif llm_generated_output is None and text_src and page_validated_for_text_extraction:
            logging.warning(f" > {company_name}: LLM generation returned None despite validated text source.")
            result_data['description'] = "Generation Error"; manual_check_flag = True
            
        if manual_check_flag and result_data.get('description',"") == "":
            result_data['description'] = "Manual check required"
            
    except Exception as e:
        logging.error(f"!! Unhandled exception in process_company for {company_name}: {type(e).__name__} - {e}")
        traceback.print_exc(file=open(log_file_path, 'a')) # Log traceback to file
        result_data["description"] = f"Processing Error: {type(e).__name__}"
        
    elapsed = time.time() - start_time
    logging.info(f"Finished async process for: {company_name} in {elapsed:.2f}s.")
    return result_data


async def run_pipeline():
    """Main asynchronous pipeline orchestration."""
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
    # Check if load_env_vars indicated failure by returning None for keys
    if not all([scrapingbee_api_key, openai_api_key, serper_api_key]):
        # The specific error message is already printed by load_env_vars
        logging.critical("Exiting due to missing API keys.") 
        exit()
        
    llm_config = load_llm_config(llm_config_file) 
    if not llm_config: 
        logging.critical(f"Failed to load LLM config from {llm_config_file}. Exiting."); 
        exit()
        
    logging.info(f"Starting ASYNC batch company processing. Input: '{input_dir}', Outputs: '{final_output_dir}'")
    
    supported_extensions = ('.xlsx', '.xls', '.csv')
    overall_results = []
    processed_files_count = 0

    if not os.path.exists(input_dir): 
        logging.critical(f"Error: Input directory '{input_dir}' not found. Exiting."); 
        exit()
        
    # --- Initialize Shared Clients --- 
    logging.info("Initializing API clients...")
    sb_client = ScrapingBeeClient(api_key=scrapingbee_api_key) 
    openai_client = AsyncOpenAI(api_key=openai_api_key) 
    
    # --- Process Files --- 
    async with aiohttp.ClientSession() as session:
        for filename in os.listdir(input_dir):
            original_input_path = os.path.join(input_dir, filename)
            if os.path.isfile(original_input_path) and filename.lower().endswith(supported_extensions):
                logging.info(f"\n>>> Found data file: {filename}")
                base_name, _ = os.path.splitext(filename)
                
                # Generate Unique Output Filename
                output_file_base = os.path.join(final_output_dir, f"{base_name}_output")
                output_file_path = f"{output_file_base}.csv"
                counter = 1
                while os.path.exists(output_file_path):
                    output_file_path = f"{output_file_base}_{counter}.csv"
                    counter += 1
                
                # --- Handle Context File --- 
                context_file_path = os.path.join(input_dir, f"{base_name}_context.txt")
                existing_context = load_context_file(context_file_path) # Try loading existing
                current_run_context = None
                
                try:
                    prompt_message = f"\nEnter context for '{filename}'" 
                    if existing_context:
                        prompt_message += f" (Press Enter to use previous: '{existing_context[:70]}...'): "
                    else:
                        prompt_message += f" (industry, region, source...) or press Enter to skip: "
                        
                    user_input = input(prompt_message)
                    provided_context = user_input.strip()
                    
                    if provided_context: # User entered new context
                        current_run_context = provided_context
                    elif existing_context: # User pressed Enter, use existing
                        current_run_context = existing_context
                        logging.info(f"Using existing context for {filename}.")
                    else: # User pressed Enter, no existing context
                        current_run_context = None
                        logging.info(f"No context provided or used for {filename}.")

                    # Save context if it was newly provided or changed (and not empty)
                    if current_run_context and current_run_context != existing_context:
                         if save_context_file(context_file_path, current_run_context):
                             logging.info("Context saved.")
                         else:
                             logging.error("Failed to save context.") # Continue with context in memory anyway
                             
                except EOFError: 
                     logging.warning("\nCannot read input. Proceeding without context.")
                     current_run_context = None # Ensure context is None
                         
                # --- Load Companies and Process --- 
                company_names = load_and_prepare_company_names(original_input_path, company_col_index)
                if not company_names: 
                    logging.warning(f"--- Skipping file {filename}: No valid company names found."); 
                    continue
                
                logging.info(f" Found {len(company_names)} companies. Creating async tasks...")
                # Pass the context determined for this specific run
                tasks = [asyncio.create_task(process_company(name, session, sb_client, llm_config, openai_client, current_run_context, serper_api_key)) for name in company_names]
                file_task_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process and Save Results for the File
                file_successful_results = []
                exceptions_count = 0
                for result in file_task_results:
                    if isinstance(result, Exception): logging.error(f"!! Task failed: {result}"); exceptions_count += 1
                    elif isinstance(result, dict): file_successful_results.append(result)
                    else: logging.error(f"!! Unexpected result type: {type(result)}")
                    
                logging.info(f"<<< Finished {filename}. Success: {len(file_successful_results)}, Failures: {exceptions_count}")
                if file_successful_results:
                    save_results_csv(file_successful_results, output_file_path) 
                    overall_results.extend(file_successful_results)
                    processed_files_count += 1
                else: 
                    logging.info(f" No successful results for {filename}.")
            else: 
                logging.info(f"Skipping non-supported/file item: {filename}")
            
    # --- Final Summary --- 
    if processed_files_count > 0:
        logging.info(f"\nSuccessfully processed {processed_files_count} file(s). Total successful results: {len(overall_results)}.")
        if overall_results:
            logging.info("\n--- Consolidated JSON Output ---")
            logging.info(json.dumps(overall_results, indent=2, ensure_ascii=False))
            print("\n--- Consolidated JSON Output (also in pipeline_run.log) ---")
            print(json.dumps(overall_results, indent=2, ensure_ascii=False)) # Keep print for console
            print("--- --- --- --- --- --- ---")
    else: 
        logging.info(f"No supported files processed successfully in '{input_dir}'.")
    
    logging.info("Async batch processing finished.") 

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try: asyncio.run(run_pipeline())
    except KeyboardInterrupt: logging.warning("\nProcessing interrupted.")
    except Exception as e: logging.error(f"\nUnexpected error in main async exec: {e}"); traceback.print_exc() 