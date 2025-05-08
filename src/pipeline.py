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
                         find_and_scrape_about_page_async,
                         get_wikipedia_summary_async) # Added get_wikipedia_summary_async

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
    
    # --- Variables to store collected data ---
    hp_url_found_serper: str | None = None
    li_url_found_serper: str | None = None
    li_snippet_serper: str | None = None
    wiki_url_found_serper: str | None = None
    hp_html_content: str | None = None
    hp_title: str | None = None
    hp_root: str | None = None
    about_page_text: str | None = None
    wiki_summary: str | None = None
    text_src: str | None = None
    page_validated_for_text_extraction: bool = False
    manual_check_flag: bool = False
    pipeline_logger = logging.getLogger(__name__)

    try:
        # --- 1. Find URLs using Serper API ---
        pipeline_logger.info(f"  > {company_name}: Finding URLs via Serper...")
        hp_url_found_serper, li_url_found_serper, li_snippet_serper, wiki_url_found_serper = await find_urls_with_serper_async(
            aiohttp_session, company_name, context_text, serper_api_key, openai_client, pipeline_logger
        )
        
        # <<< START: Extract base URL for homepage column >>>
        base_homepage_url = "Not found"
        if hp_url_found_serper:
            try:
                parsed_hp_url = urlparse(hp_url_found_serper)
                base_homepage_url = f"{parsed_hp_url.scheme}://{parsed_hp_url.netloc}" 
            except Exception as e_parse:
                pipeline_logger.warning(f"  > {company_name}: Could not parse homepage URL '{hp_url_found_serper}' to extract base: {e_parse}")
                base_homepage_url = hp_url_found_serper # Fallback to original if parsing fails
        result_data["homepage"] = base_homepage_url # Assign the cleaned base URL
        # <<< END: Extract base URL >>>
        
        # <<< START: Clean LinkedIn URL for output >>>
        cleaned_linkedin_url = "Not found"
        if li_url_found_serper:
            # Remove trailing '/about/' or '/' if present
            if li_url_found_serper.endswith('/about/'):
                cleaned_linkedin_url = li_url_found_serper[:-len('/about/')]
            elif li_url_found_serper.endswith('/'):
                 cleaned_linkedin_url = li_url_found_serper[:-1]
            else:
                 cleaned_linkedin_url = li_url_found_serper 
        result_data["linkedin"] = cleaned_linkedin_url # Assign cleaned URL
        # <<< END: Clean LinkedIn URL >>>
        
        # Store initial homepage data if found (using the potentially full URL from Serper for logging)
        if hp_url_found_serper:
            pipeline_logger.info(f"  > {company_name}: Homepage URL found: {hp_url_found_serper} (Saved base: {base_homepage_url})") # Log both for clarity
        else:
            pipeline_logger.warning(f"  > {company_name}: Homepage URL NOT found by Serper/LLM.")
            manual_check_flag = True
            
        if li_url_found_serper: # Log the originally found URL
            pipeline_logger.info(f"  > {company_name}: LinkedIn URL found: {li_url_found_serper} (Saved base: {cleaned_linkedin_url})") # Log both
            if li_snippet_serper:
                pipeline_logger.info(f"  > {company_name}: LinkedIn Snippet found (Serper): '{li_snippet_serper[:100]}...'")
        else:
            pipeline_logger.warning(f"  > {company_name}: LinkedIn URL NOT found.")
            
        if wiki_url_found_serper:
            pipeline_logger.info(f"  > {company_name}: Wikipedia URL found: {wiki_url_found_serper}")
        else:
            pipeline_logger.info(f"  > {company_name}: Wikipedia URL NOT found by Serper.")

        # --- 2. Scrape Homepage (if URL found) ---
        if hp_url_found_serper:
            try:
                pipeline_logger.info(f"  > {company_name}: Scraping homepage: {hp_url_found_serper}")
                # Use the async wrapper for ScrapingBee
                hp_data = await scrape_page_data_async(hp_url_found_serper, sb_client)
                if hp_data and hp_data[2]: # Check if HTML content exists
                    hp_title = hp_data[0]
                    hp_root = hp_data[1]
                    hp_html_content = hp_data[2]
                    pipeline_logger.info(f"  > {company_name}: Homepage scraped. Title: '{hp_title}', Root: {hp_root}, HTML len: {len(hp_html_content)}")
                else:
                    pipeline_logger.warning(f"  > {company_name}: Scraping homepage returned no HTML content.")
                    manual_check_flag = True
            except Exception as e_scrape_hp:
                pipeline_logger.error(f"  > {company_name}: Error scraping homepage {hp_url_found_serper}: {e_scrape_hp}")
                manual_check_flag = True

        # --- 3. Find and Scrape 'About Us' page (if homepage HTML available) ---
        if hp_html_content and hp_url_found_serper:
            try:
                pipeline_logger.info(f"  > {company_name}: Attempting to find and scrape 'About Us' page...")
                about_page_text = await find_and_scrape_about_page_async(
                    hp_html_content, 
                    hp_url_found_serper, 
                    company_name, 
                    aiohttp_session, 
                    sb_client, 
                    openai_client, # Pass the client
                    pipeline_logger
                )
                if about_page_text:
                    pipeline_logger.info(f"  > {company_name}: Found text from 'About Us' page (length: {len(about_page_text)}).")
                else:
                     pipeline_logger.info(f"  > {company_name}: No meaningful text from 'About Us' page (or page not found).")
            except Exception as e_about:
                pipeline_logger.error(f"  > {company_name}: Error in find_and_scrape_about_page_async: {e_about}")
                # Continue, fallback to other sources
                
        # --- 4. Fetch Wikipedia Summary (if URL found) ---
        if wiki_url_found_serper:
            try:
                # Extract title from URL (last part after '/')
                wiki_page_title = unquote(urlparse(wiki_url_found_serper).path.split('/')[-1])
                if wiki_page_title:
                    pipeline_logger.info(f"  > {company_name}: Attempting to fetch Wikipedia summary for page title: '{wiki_page_title}'")
                    wiki_summary = await get_wikipedia_summary_async(wiki_page_title, pipeline_logger)
                    if wiki_summary:
                        pipeline_logger.info(f"  > {company_name}: Wikipedia summary fetched successfully (length: {len(wiki_summary)}).")
                    else:
                        pipeline_logger.warning(f"  > {company_name}: Wikipedia summary fetch failed or summary was empty.")
                else:
                    pipeline_logger.warning(f"  > {company_name}: Could not extract page title from Wikipedia URL: {wiki_url_found_serper}")
            except Exception as e_wiki:
                 pipeline_logger.error(f"  > {company_name}: Error fetching Wikipedia summary: {e_wiki}")

        # --- 5. Extract Text from Homepage & Validate (if About page text is missing) ---
        hp_text = None
        if not about_page_text and hp_html_content and hp_url_found_serper:
            pipeline_logger.info(f"  > {company_name}: Extracting text from homepage for potential use...")
            hp_text = extract_text_for_description(hp_html_content)
            if hp_text and len(hp_text) > 100:
                pipeline_logger.info(f"  > {company_name}: Text extracted from homepage (length: {len(hp_text)}). Validating homepage...")
                page_validated_for_text_extraction = validate_page(company_name, hp_title, hp_root, hp_html_content, hp_url_found_serper)
                if page_validated_for_text_extraction:
                    pipeline_logger.info(f"  > {company_name}: Homepage content IS validated.")
                else:
                    pipeline_logger.warning(f"  > {company_name}: Homepage content validation FAILED. Will not use homepage text.")
                    hp_text = None # Discard text if validation fails
            else:
                pipeline_logger.warning(f"  > {company_name}: No description-like text extracted from homepage.")
                hp_text = None
        elif about_page_text:
             # If we got text from 'About Us', we consider validation passed for text source
             page_validated_for_text_extraction = True
             pipeline_logger.info(f"  > {company_name}: Using text from 'About Us' page, skipping homepage validation for description text.")

        # --- 6. Combine Text Sources for LLM --- 
        combined_sources = []
        if about_page_text:
            combined_sources.append("[From About Page Found at N/A]:\n" + about_page_text)
        if wiki_summary:
            combined_sources.append("[From Wikipedia Summary]:\n" + wiki_summary)
        if li_url_found_serper and li_snippet_serper:
             combined_sources.append(f"[From LinkedIn Serper Snippet ({li_url_found_serper})]:\n{li_snippet_serper}")
        if not about_page_text and not wiki_summary and hp_text and page_validated_for_text_extraction:
             combined_sources.append("[From Homepage]:\n" + hp_text)
             
        if combined_sources:
            text_src = "\n\n---\n\n".join(combined_sources)
            pipeline_logger.debug(f"  > {company_name}: Final combined text_src length: {len(text_src)}")
        else:
            pipeline_logger.warning(f"  > {company_name}: No text source available after checking About page, Wikipedia, and Homepage.")
            manual_check_flag = True
            
        # --- 7. Generate Description using LLM --- 
        llm_generated_output = None
        if text_src:
            pipeline_logger.info(f"  > {company_name}: Combined text source found (length: {len(text_src)}), generating LLM description...")
            try:
                 llm_generated_output = await generate_description_openai_async(
                     openai_client=openai_client, 
                     llm_config=llm_config, 
                     company_name=company_name, 
                     about_snippet=text_src, # Pass the combined text
                     homepage_root=hp_root, 
                     linkedin_url=li_url_found_serper, 
                     context_text=context_text
                 )
                 if llm_generated_output:
                     result_data["description"] = llm_generated_output
                     pipeline_logger.info(f"  > {company_name}: LLM description generated successfully (length {len(llm_generated_output)}).")
                 else:
                     pipeline_logger.warning(f"  > {company_name}: LLM generation returned empty result.")
                     manual_check_flag = True
            except Exception as e_llm:
                pipeline_logger.error(f"  > {company_name}: LLM description generation FAILED: {e_llm}")
                pipeline_logger.debug(traceback.format_exc()) # Log full traceback for LLM errors
                manual_check_flag = True
        else:
             pipeline_logger.warning(f"  > {company_name}: No usable text source found. LLM description cannot be generated.")
             manual_check_flag = True # Already flagged above, but redundant doesn't hurt
             
    except Exception as e_outer:
        logging.critical(f"CRITICAL ERROR processing {company_name}: {type(e_outer).__name__} - {e_outer}")
        logging.debug(traceback.format_exc())
        result_data["description"] = "Error in processing - check logs"
        result_data["homepage"] = hp_url_found_serper if hp_url_found_serper else result_data.get("homepage", "Error")
        result_data["linkedin"] = li_url_found_serper if li_url_found_serper else result_data.get("linkedin", "Error")
    
    processing_time = time.time() - start_time
    logging.info(f"Finished processing {company_name} in {processing_time:.2f} seconds. Result: Homepage: '{result_data['homepage']}', LI: '{result_data['linkedin']}', Desc len: {len(result_data['description']) if result_data['description'] else 0}")
    return result_data


def setup_session_logging(pipeline_log_path: str, scoring_log_path: str):
    """Configures logging handlers for a specific session run."""
    # Remove existing handlers for the root logger (if any were added before)
    root_logger = logging.getLogger()
    # Keep only the StreamHandler if present, remove FileHandlers from previous sessions
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
             root_logger.removeHandler(handler)
             handler.close() # Ensure file is closed
        # Optional: Keep StreamHandler if you want console output during UI run
        # if isinstance(handler, logging.StreamHandler):
        #     pass # Keep console handler

    # Add new file handler for the current session's pipeline log
    fh_pipeline = logging.FileHandler(pipeline_log_path, mode='w', encoding='utf-8')
    fh_pipeline.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'))
    root_logger.addHandler(fh_pipeline)
    root_logger.setLevel(logging.DEBUG) # Ensure root logger level is set

    # Configure scoring logger for the specific session file
    scoring_logger = logging.getLogger('ScoringLogger')
    scoring_logger.setLevel(logging.DEBUG)
    scoring_logger.propagate = False 
    for handler in scoring_logger.handlers[:]: # Remove old handlers
        scoring_logger.removeHandler(handler)
        handler.close()
    fh_scoring = logging.FileHandler(scoring_log_path, mode='w', encoding='utf-8')
    fh_scoring.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    scoring_logger.addHandler(fh_scoring)

async def run_pipeline_cli():
    """Main asynchronous pipeline orchestration for CLI execution."""
    run_timestamp = time.strftime("%Y%m%d_%H%M%S")
    logs_base_dir = os.path.join("output", "logs")
    if not os.path.exists(logs_base_dir):
        os.makedirs(logs_base_dir)
        
    # Setup initial basic logging (will be reconfigured by setup_session_logging per file)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        handlers=[logging.StreamHandler()] # Log to console initially
    )

    logging.info(f"\n{'='*30} CLI PIPELINE RUNNING {'='*30}")
    input_dir = "input"
    output_dir = "output"
    final_output_dir = os.path.join(output_dir, "final_outputs") 
    llm_config_file = "llm_config.yaml"
    company_col_index = 0 

    # Create Directories
    for dir_path in [output_dir, final_output_dir]: 
        if not os.path.exists(dir_path):
            os.makedirs(dir_path); logging.info(f"Created directory: {dir_path}")
            
    logging.info("Loading configurations and API keys...")
    scrapingbee_api_key, openai_api_key, serper_api_key = load_env_vars()
    if not all([scrapingbee_api_key, openai_api_key, serper_api_key]):
        logging.critical("Exiting due to missing API keys.") 
        return
        
    llm_config = load_llm_config(llm_config_file) 
    if not llm_config: 
        logging.critical(f"Failed to load LLM config from {llm_config_file}. Exiting."); 
        return
        
    expected_csv_fieldnames = ["name", "homepage", "linkedin", "description"] # Simplified for CLI example
    logging.info(f"Final CSV fieldnames will be: {expected_csv_fieldnames}")
        
    logging.info(f"Starting ASYNC batch company processing. Input: '{input_dir}', Outputs: '{final_output_dir}'")
    
    supported_extensions = ('.xlsx', '.xls', '.csv')
    overall_results = []
    processed_files_count = 0

    if not os.path.exists(input_dir): 
        logging.critical(f"Error: Input directory '{input_dir}' not found. Exiting."); 
        return
        
    logging.info("Initializing API clients...")
    sb_client = ScrapingBeeClient(api_key=scrapingbee_api_key) 
    openai_client = AsyncOpenAI(api_key=openai_api_key) 
    
    async with aiohttp.ClientSession() as session:
        for filename in os.listdir(input_dir):
            original_input_path = os.path.join(input_dir, filename)
            if os.path.isfile(original_input_path) and filename.lower().endswith(supported_extensions):
                logging.info(f"\n>>> Found data file: {filename}")
                base_name, _ = os.path.splitext(filename)
                
                # Generate session-specific paths for CLI run
                session_id = f"cli_{run_timestamp}_{base_name}" # Example session ID for CLI
                session_log_dir = os.path.join(logs_base_dir, session_id)
                if not os.path.exists(session_log_dir):
                    os.makedirs(session_log_dir)
                    
                output_file_path = os.path.join(final_output_dir, f"{base_name}_output_{run_timestamp}.csv") # Keep original output scheme for CLI
                pipeline_log_path = os.path.join(session_log_dir, "pipeline.log")
                scoring_log_path = os.path.join(session_log_dir, "scoring.log")
                
                # --- Handle Context for CLI --- 
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
                     
                # --- Run the processing logic for this file --- 
                success_count, failure_count, file_results = await run_pipeline_for_file(
                    input_file_path=original_input_path,
                    output_csv_path=output_file_path,
                    pipeline_log_path=pipeline_log_path,
                    scoring_log_path=scoring_log_path,
                    context_text=current_run_context,
                    company_col_index=company_col_index,
                    aiohttp_session=session,
                    sb_client=sb_client,
                    llm_config=llm_config,
                    openai_client=openai_client,
                    serper_api_key=serper_api_key,
                    expected_csv_fieldnames=expected_csv_fieldnames
                )
                
                logging.info(f"<<< Finished processing for {filename}. Successes: {success_count}, Failures: {failure_count}")
                if file_results: 
                    overall_results.extend(file_results)
                    processed_files_count += 1
                else: 
                    logging.warning(f"No successful results for {filename} to add to overall summary.") # Changed info to warning
            else: 
                logging.info(f"Skipping non-supported/file item: {filename}")
                
    # ... (Final summary logging as before) ...
    logging.info(f"CLI run finished.")

async def run_pipeline_for_file(input_file_path: str, output_csv_path: str, pipeline_log_path: str, scoring_log_path: str, context_text: str | None, company_col_index: int, aiohttp_session: aiohttp.ClientSession, sb_client: ScrapingBeeClient, llm_config: dict, openai_client: AsyncOpenAI, serper_api_key: str | None, expected_csv_fieldnames: list[str]) -> tuple[int, int, list[dict]]:
    """Processes a single input file and saves results incrementally."""
    
    # Setup logging for this specific run
    setup_session_logging(pipeline_log_path, scoring_log_path)
    base_name = os.path.basename(input_file_path)
    logging.info(f"Starting processing for file: {base_name}")
    
    company_names = load_and_prepare_company_names(input_file_path, company_col_index)
    if not company_names:
        logging.warning(f"--- Skipping file {base_name}: No valid company names found.")
        return 0, 0, [] # Success count, Failure count, Results list

    logging.info(f"Found {len(company_names)} companies for {base_name}. Processing each and saving incrementally to {output_csv_path}...")

    current_file_successful_results = []
    exceptions_in_current_file = 0
    
    # Ensure output directory exists before trying to save
    output_dir = os.path.dirname(output_csv_path)
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            logging.info(f"Created output directory for session: {output_dir}")
        except OSError as e:
            logging.critical(f"Could not create output directory {output_dir}. Error: {e}")
            return 0, len(company_names), [] # Treat all as failures if cannot write output

    tasks = [
        asyncio.create_task(
            process_company(name, aiohttp_session, sb_client, llm_config, openai_client, context_text, serper_api_key)
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
                    output_csv_path,
                    append_mode=True, # Critical for incremental saving
                    fieldnames=expected_csv_fieldnames # Provide all expected headers
                )
            else:
                logging.error(f"Unexpected result type for a company in {base_name}: {type(result_data)}")
                exceptions_in_current_file += 1

        except Exception as e:
            task_exc_company_name = "UnknownCompanyInFailedTask" # Placeholder
            logging.error(f"Task for company '{task_exc_company_name}' in {base_name} failed: {type(e).__name__} - {e}")
            exceptions_in_current_file += 1
            # Optionally save error to CSV?
            # error_entry = {"name": task_exc_company_name, "description": f"Processing Error: {type(e).__name__}"}
            # ... (ensure all fields exist)
            # save_results_csv([error_entry], output_csv_path, append_mode=True, fieldnames=expected_csv_fieldnames)

    return len(current_file_successful_results), exceptions_in_current_file, current_file_successful_results

# --- Main Execution Block (for CLI) --- 
if __name__ == "__main__":
    # Keep the original CLI execution logic
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try: asyncio.run(run_pipeline_cli()) # Call the CLI runner
    except KeyboardInterrupt: logging.warning("\nProcessing interrupted.")
    except Exception as e: logging.error(f"\nUnexpected error in main async exec: {e}"); traceback.print_exc() 