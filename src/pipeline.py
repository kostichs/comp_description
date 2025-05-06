import asyncio
import aiohttp
import os
import json
import time
import traceback
import tldextract
from urllib.parse import urlparse

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
from .external_apis.openai_client import generate_description_openai_async
from .processing import validate_page, extract_text_for_description

async def process_company(company_name: str, 
                          aiohttp_session: aiohttp.ClientSession, 
                          sb_client: ScrapingBeeClient, 
                          llm_config: dict, 
                          openai_client: AsyncOpenAI, 
                          context_text: str | None, 
                          serper_api_key: str | None) -> dict:
    """Async: Processes a single company. Returns a dictionary for the output row."""
    print(f" Starting async process for: {company_name} (Context: {bool(context_text)})")
    start_time = time.time()
    result_data = {"name": company_name, "homepage": "Not found", "linkedin": "Not found", "description": ""} 
    text_src = None
    manual_check_flag = False 
    try:
        hp_url_found, li_url_found = await find_urls_with_serper_async(aiohttp_session, company_name, context_text, serper_api_key)
        result_data["linkedin"] = li_url_found or "Not found"
        if not sb_client: raise ValueError("ScrapingBee client error") 

        # --- Set Homepage URL Correctly First --- 
        if hp_url_found:
            try:
                parsed_url = urlparse(hp_url_found)
                scheme = parsed_url.scheme
                netloc = parsed_url.netloc
                path = parsed_url.path
                if scheme and netloc:
                    result_data["homepage"] = f"{scheme}://{netloc}"
                elif not scheme and (netloc or (path and '.' in path and '/' not in path)):
                     domain_part = netloc if netloc else path
                     result_data["homepage"] = f"https://{domain_part}" # Default to https
                else: 
                    result_data["homepage"] = hp_url_found # Fallback
                    if hp_url_found: print(f" > Warning: Could not reliably format homepage URL: {hp_url_found}")
            except Exception as parse_err:
                 print(f" > Warning: Could not parse homepage URL {hp_url_found}: {parse_err}")
                 result_data["homepage"] = hp_url_found # Fallback
        # else: homepage remains "Not found"
        # --- Homepage URL is now set in result_data if found --- 
        
        scrape_tasks = {}
        if hp_url_found: scrape_tasks['homepage'] = asyncio.create_task(scrape_page_data_async(hp_url_found, sb_client))
        if li_url_found: scrape_tasks['linkedin'] = asyncio.create_task(scrape_page_data_async(li_url_found, sb_client))
        scraped_results = {}
        if scrape_tasks:
            done, _ = await asyncio.wait(scrape_tasks.values(), timeout=45) 
            for task_name, task in scrape_tasks.items():
                if task in done and not task.cancelled() and task.exception() is None: scraped_results[task_name] = task.result()
                elif task.exception(): print(f" Scrape task {task_name}({company_name}) failed: {task.exception()}")
                else: print(f" Scrape task {task_name}({company_name}) timed out.")
        
        hp_data = scraped_results.get('homepage')
        li_data = scraped_results.get('linkedin')

        # --- Process Homepage Scrape Result (hp_data) --- 
        # Use hp_data only for validation and text extraction, NOT for setting homepage URL again.
        if hp_data: 
            hp_title, hp_root, hp_html = hp_data
            if hp_title and hp_root: 
                if validate_page(company_name, hp_title, hp_root): text_src = extract_text_for_description(hp_html)
                else: print(f" > {company_name}: HP validation FAILED."); manual_check_flag = True
            else: print(f" > {company_name}: Insufficient HP scrape data."); manual_check_flag = True
        elif hp_url_found: # Scrape failed or timed out, URL was found but no data returned
             print(f" > {company_name}: HP scrape failed/timed out.")
             manual_check_flag = True 
        # else: HP URL not found initially, homepage already set to "Not found"

        # Step 4: Process LinkedIn Data (if needed)
        if li_data and (not text_src or manual_check_flag):
            li_title, _, li_html = li_data
            if li_title and company_name.lower() in li_title.lower(): 
                 if not text_src: 
                    text_src = extract_text_for_description(li_html)
                    # print(f"  > {company_name}: LI validated. Text: {bool(text_src)}")
                 if text_src: manual_check_flag = False # Found text via LI, potentially override flag
            elif not text_src: 
                # print(f"  > {company_name}: LI validation FAILED.")
                manual_check_flag = True 
        elif li_url_found and (not text_src or manual_check_flag):
             # print(f"  > {company_name}: LI scrape failed/timed out.")
             if not text_src: manual_check_flag = True 
             
        # Step 5: Generate LLM Output
        llm_generated_output = None
        if text_src:
             print(f" > {company_name}: Generating LLM output...")
             llm_generated_output = await generate_description_openai_async(
                 company_name, result_data["homepage"], result_data["linkedin"], 
                 text_src, llm_config, openai_client, context_text
             )
        else:
            print(f" > {company_name}: No text found for LLM.")
            manual_check_flag = True 

        # Step 6: Finalize Result Dictionary
        if isinstance(llm_generated_output, dict):
            print(f" > {company_name}: LLM OK (JSON).")
            result_data.pop('description', None) 
            # Prefix LLM keys to avoid conflicts
            result_data.update({f"llm_{k}": v for k, v in llm_generated_output.items() if k != 'error'}) 
            if "error" in llm_generated_output: # Handle error dict from LLM func
                result_data['description'] = f"LLM Error: {llm_generated_output['error']}"
                manual_check_flag = True 
        elif isinstance(llm_generated_output, str):
            print(f" > {company_name}: LLM OK (Text).")
            result_data['description'] = llm_generated_output
            response_format = llm_config.get("response_format") 
            if isinstance(response_format, dict) and response_format.get("type") == "json_object":
                print(" > Warning: Expected JSON, got Text."); manual_check_flag = True
        elif llm_generated_output is None and text_src:
            print(f" > {company_name}: LLM generation failed.")
            result_data['description'] = "Generation Error"
            manual_check_flag = True
            
        # Set final description if manual check needed and description is empty
        if manual_check_flag and result_data.get('description',"") == "":
            result_data['description'] = "Manual check required"
            
    except Exception as e:
        print(f"!! Unhandled exception in process_company for {company_name}: {type(e).__name__} - {e}")
        traceback.print_exc()
        result_data["description"] = f"Processing Error: {type(e).__name__}"
        
    elapsed = time.time() - start_time
    print(f" Finished async process for: {company_name} in {elapsed:.2f}s.")
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
            os.makedirs(dir_path); print(f"Created directory: {dir_path}")
            
    # --- Load Configs and Keys --- 
    print("Loading configurations and API keys...")
    scrapingbee_api_key, openai_api_key, serper_api_key = load_env_vars()
    # Check if load_env_vars indicated failure by returning None for keys
    if not all([scrapingbee_api_key, openai_api_key, serper_api_key]):
        # The specific error message is already printed by load_env_vars
        print("Exiting due to missing API keys.") 
        exit()
        
    llm_config = load_llm_config(llm_config_file) 
    if not llm_config: 
        print(f"Failed to load LLM config from {llm_config_file}. Exiting."); 
        exit()
        
    print(f"Starting ASYNC batch company processing. Input: '{input_dir}', Outputs: '{final_output_dir}'")
    
    supported_extensions = ('.xlsx', '.xls', '.csv')
    overall_results = []
    processed_files_count = 0

    if not os.path.exists(input_dir): 
        print(f"Error: Input directory '{input_dir}' not found. Exiting."); 
        exit()
        
    # --- Initialize Shared Clients --- 
    print("Initializing API clients...")
    sb_client = ScrapingBeeClient(api_key=scrapingbee_api_key) 
    openai_client = AsyncOpenAI(api_key=openai_api_key) 
    
    # --- Process Files --- 
    async with aiohttp.ClientSession() as session:
        for filename in os.listdir(input_dir):
            original_input_path = os.path.join(input_dir, filename)
            if os.path.isfile(original_input_path) and filename.lower().endswith(supported_extensions):
                print(f"\n>>> Found data file: {filename}")
                base_name, _ = os.path.splitext(filename)
                
                # Generate Unique Output Filename
                output_file_base = os.path.join(final_output_dir, f"{base_name}_output")
                output_file_path = f"{output_file_base}.csv"
                counter = 1
                while os.path.exists(output_file_path):
                    output_file_path = f"{output_file_base}_{counter}.csv"
                    counter += 1
                
                # Handle Context File
                context_file_path = os.path.join(input_dir, f"{base_name}_context.txt")
                context_text = load_context_file(context_file_path) 
                if context_text is None: 
                    try:
                        print(f"\n*** Context file for '{filename}' not found or empty. ***")
                        user_input = input(f"Enter context (industry, region, source...) or press Enter to skip: ")
                        context_text = user_input.strip()
                        if context_text:
                            if save_context_file(context_file_path, context_text):
                                print("Context saved.")
                            else:
                                print("Failed to save context, proceeding without it.")
                                context_text = None
                        else:
                            print("Context not entered, proceeding without it.")
                            context_text = None 
                    except EOFError: 
                         print("\nCannot read input. Proceeding without context.")
                         context_text = None
                         
                # Load Companies
                company_names = load_and_prepare_company_names(original_input_path, company_col_index)
                if not company_names: 
                    print(f"--- Skipping file {filename}: No valid company names found."); 
                    continue
                
                # Create and Run Tasks
                print(f" Found {len(company_names)} companies. Creating async tasks...")
                tasks = [asyncio.create_task(process_company(name, session, sb_client, llm_config, openai_client, context_text, serper_api_key)) for name in company_names]
                file_task_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process and Save Results for the File
                file_successful_results = []
                exceptions_count = 0
                for result in file_task_results:
                    if isinstance(result, Exception): print(f"!! Task failed: {result}"); exceptions_count += 1
                    elif isinstance(result, dict): file_successful_results.append(result)
                    else: print(f"!! Unexpected result type: {type(result)}")
                    
                print(f"<<< Finished {filename}. Success: {len(file_successful_results)}, Failures: {exceptions_count}")
                if file_successful_results:
                    save_results_csv(file_successful_results, output_file_path) 
                    overall_results.extend(file_successful_results)
                    processed_files_count += 1
                else: 
                    print(f" No successful results for {filename}.")
            else: 
                print(f"Skipping non-supported/file item: {filename}")
            
    # --- Final Summary --- 
    if processed_files_count > 0:
        print(f"\nSuccessfully processed {processed_files_count} file(s). Total successful results: {len(overall_results)}.")
        if overall_results:
            print("\n--- Consolidated JSON Output ---")
            print(json.dumps(overall_results, indent=2, ensure_ascii=False))
            print("--- --- --- --- --- --- ---")
    else: 
        print(f"No supported files processed successfully in '{input_dir}'.")
    
    print("Async batch processing finished.") 