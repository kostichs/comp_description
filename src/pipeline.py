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
from typing import Optional, Dict, Any

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

async def process_company(company_name: str, 
                          aiohttp_session: aiohttp.ClientSession, 
                          sb_client: ScrapingBeeClient, 
                          llm_config: dict, 
                          openai_client: AsyncOpenAI,
                          context_text: str | None, 
                          serper_api_key: str | None,
                          run_standard_pipeline: bool = True,
                          run_llm_deep_search_pipeline: bool = False,
                          llm_deep_search_config: Optional[Dict[str, Any]] = None) -> dict:
    """Async: Processes a single company. Returns a dictionary for the output row."""
    pipeline_logger = logging.getLogger(__name__)
    pipeline_logger.info(f"Starting process for: {company_name} (Std: {run_standard_pipeline}, Deep: {run_llm_deep_search_pipeline}) Context: {bool(context_text)}")
    start_time_processing = time.time()
    
    current_date_iso = datetime.now().strftime("%Y-%m-%d")

    # Инициализация result_data стандартными полями
    result_data = {
        "name": company_name,
        "homepage": "Not found", 
        "linkedin": "Not found", 
        "description": "Description not generated", # Будет перезаписано
        "timestamp": current_date_iso
    }
    
    # --- Переменные для сбора данных ---
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
    text_src_for_llms: str = "" # Инициализируем пустой строкой, будем конкатенировать
    manual_check_flag: bool = False

    try:
        # --- ШАГ 0: Поиск URL (Serper) ---
        # Необходимо, если включен стандартный пайплайн (для homepage/linkedin полей)
        # или если включен любой из LLM пайплайнов (для сбора текстовых источников)
        if run_standard_pipeline or run_llm_deep_search_pipeline:
            pipeline_logger.info(f"  > {company_name}: Finding URLs via Serper...")
            serper_urls = await find_urls_with_serper_async(
                aiohttp_session, company_name, context_text, serper_api_key, openai_client, pipeline_logger
            )
            if serper_urls:
                hp_url_found_serper, li_url_found_serper, li_snippet_serper, wiki_url_found_serper = serper_urls
            else:
                pipeline_logger.error(f"  > {company_name}: Critical error in find_urls_with_serper_async, returned None.")
                if run_standard_pipeline: manual_check_flag = True # Для стандартных полей, если они ожидаются

        # --- Заполнение полей homepage и linkedin для СТАНДАРТНОГО пайплайна (если он активен) ---
        if run_standard_pipeline:
            if hp_url_found_serper:
                try:
                    parsed_hp_url = urlparse(hp_url_found_serper)
                    result_data["homepage"] = f"{parsed_hp_url.scheme}://{parsed_hp_url.netloc}"
                except Exception: result_data["homepage"] = hp_url_found_serper
            else:
                result_data["homepage"] = "Not found"
                manual_check_flag = True
            
            if li_url_found_serper:
                cleaned_li = li_url_found_serper
                if cleaned_li.endswith('/about/'): cleaned_li = cleaned_li[:-len('/about/')]
                if cleaned_li.endswith('/'): cleaned_li = cleaned_li[:-1]
                result_data["linkedin"] = cleaned_li
            else:
                result_data["linkedin"] = "Not found"
        else: # Если стандартный пайплайн не запускается, но эти колонки все равно есть
            result_data["homepage"] = "Standard pipeline not run"
            result_data["linkedin"] = "Standard pipeline not run"

        # --- Сбор текстовых данных для LLM (стандартного и/или deep search) ---
        # Необходимо, если включен хотя бы один из LLM-зависимых этапов
        # (генерация стандартного описания или LLM Deep Search, который использует query_llm_for_deep_info)
        needs_text_sources_collection = run_standard_pipeline or run_llm_deep_search_pipeline

        if needs_text_sources_collection:
            pipeline_logger.info(f"  > {company_name}: Text source collection for LLMs needed.")
            # (Логика сбора hp_html_content, about_page_text, wiki_summary, hp_text_for_llm - остается как была раньше)
            if hp_url_found_serper:
                try:
                    pipeline_logger.info(f"  > {company_name}: Scraping homepage: {hp_url_found_serper}")
                    hp_data = await scrape_page_data_async(hp_url_found_serper, sb_client)
                    if hp_data and hp_data[2]:
                        hp_title = hp_data[0]; hp_root = hp_data[1]; hp_html_content = hp_data[2]
                        pipeline_logger.info(f"  > {company_name}: Homepage scraped. Title: '{hp_title}', HTML len: {len(hp_html_content)}")
                    else: pipeline_logger.warning(f"  > {company_name}: Scraping homepage '{hp_url_found_serper}' failed or no HTML.")
                except Exception as e_scrape_hp: pipeline_logger.error(f"  > {company_name}: Error scraping HP: {e_scrape_hp}")

            if hp_html_content and hp_url_found_serper:
                try:
                    about_page_text = await find_and_scrape_about_page_async(hp_html_content, hp_url_found_serper, company_name, aiohttp_session, sb_client, openai_client, pipeline_logger)
                    if about_page_text: pipeline_logger.info(f"  > {company_name}: Found text from 'About Us' (len: {len(about_page_text)}).")
                except Exception as e_about: pipeline_logger.error(f"  > {company_name}: Error finding/scraping About page: {e_about}")

            if wiki_url_found_serper:
                try:
                    wiki_page_title = unquote(urlparse(wiki_url_found_serper).path.split('/')[-1])
                    if wiki_page_title: wiki_summary = await get_wikipedia_summary_async(wiki_page_title, pipeline_logger)
                    if wiki_summary: pipeline_logger.info(f"  > {company_name}: Wikipedia summary fetched (len: {len(wiki_summary)}).")
                except Exception as e_wiki: pipeline_logger.error(f"  > {company_name}: Error fetching Wikipedia: {e_wiki}")
            
            page_validated_for_text_extraction = False
            if not about_page_text and hp_html_content and hp_url_found_serper:
                current_hp_text = extract_text_for_description(hp_html_content)
                if current_hp_text and len(current_hp_text) > 100:
                    page_validated_for_text_extraction = validate_page(company_name, hp_title, hp_root, hp_html_content, hp_url_found_serper)
                    if page_validated_for_text_extraction: hp_text_for_llm = current_hp_text; pipeline_logger.info(f"  > {company_name}: HP content validated.")
                    else: pipeline_logger.warning(f"  > {company_name}: HP content validation FAILED.")
            elif about_page_text: page_validated_for_text_extraction = True

            # --- Комбинирование источников текста (стандартная часть) ---
            standard_text_sources_list = []
            if about_page_text: standard_text_sources_list.append("[From About Page]:\n" + about_page_text)
            if wiki_summary: standard_text_sources_list.append("[From Wikipedia Summary]:\n" + wiki_summary)
            if li_url_found_serper and li_snippet_serper: standard_text_sources_list.append(f"[From LinkedIn Serper Snippet ({li_url_found_serper})]:\n{li_snippet_serper}")
            if not about_page_text and not wiki_summary and hp_text_for_llm and page_validated_for_text_extraction: standard_text_sources_list.append("[From Homepage]:\n" + hp_text_for_llm)
            
            if standard_text_sources_list:
                text_src_for_llms += "\n\n---\n\n".join(standard_text_sources_list)
                pipeline_logger.debug(f"  > {company_name}: Standard text sources combined (len: {len(text_src_for_llms)})")
            else:
                pipeline_logger.warning(f"  > {company_name}: No standard text sources found for LLMs.")
        else:
            pipeline_logger.info(f"  > {company_name}: Text source collection for LLMs SKIPPED.")

        # --- LLM DEEP SEARCH (если включен) --- 
        # Результаты этого шага будут добавлены к text_src_for_llms
        if run_llm_deep_search_pipeline:
            pipeline_logger.info(f"  > {company_name}: Running LLM DEEP SEARCH to augment description context...")
            if llm_deep_search_config and llm_deep_search_config.get("specific_queries"):
                specific_queries = llm_deep_search_config["specific_queries"]
                # Используем существующий text_src_for_llms как основу для query_llm_for_deep_info,
                # так как эта функция по плану ожидает text_sources_for_deep_search.
                # Если text_src_for_llms пуст, то deep search будет работать только на основе своего промпта.
                # Это соответствует текущей реализации query_llm_for_deep_info, которая комбинирует company_name, text_sources и query.
                base_text_for_deep_search = text_src_for_llms if text_src_for_llms else "No prior text context available."
                
                pipeline_logger.info(f"  > {company_name}: LLM Deep Search: Calling query_llm_for_deep_info with base_text (len: {len(base_text_for_deep_search)}).")
                deep_search_results_dict = await query_llm_for_deep_info(
                    openai_client=openai_client,
                    company_name=company_name,
                    text_sources_for_deep_search=base_text_for_deep_search, 
                    specific_queries=specific_queries
                )
                
                if deep_search_results_dict and not deep_search_results_dict.get("error"):
                    formatted_deep_search_text = "\n\n--- Additional Information from Deep Search ---\n"
                    for original_query, answer in deep_search_results_dict.items():
                        formatted_deep_search_text += f"- Query: {original_query}\n  Answer: {answer}\n"
                    text_src_for_llms += formatted_deep_search_text # Добавляем к общему источнику
                    pipeline_logger.info(f"  > {company_name}: LLM Deep Search results appended to text_src_for_llms. New total len: {len(text_src_for_llms)}.")
                elif deep_search_results_dict.get("error"):
                    pipeline_logger.warning(f"  > {company_name}: LLM Deep Search returned an error: {deep_search_results_dict.get('error')}")
                else:
                    pipeline_logger.warning(f"  > {company_name}: LLM Deep Search returned no results or an unexpected format.")
            else:
                pipeline_logger.warning(f"  > {company_name}: LLM Deep Search: No specific_queries configured. Skipping augmentation.")
        
        # --- ФИНАЛЬНАЯ ГЕНЕРАЦИЯ ОПИСАНИЯ --- 
        # Выполняется всегда, если есть хоть какой-то text_src_for_llms или если стандартный пайплайн был включен (он мог сгенерировать заглушку, которую надо перезаписать)
        # По факту, если run_standard_pipeline = False и run_llm_deep_search_pipeline = False, то text_src_for_llms будет пуст, и LLM не вызовется.
        # Если хотя бы один из них True, то text_src_for_llms может содержать данные.
        
        if text_src_for_llms: # Если есть хоть какой-то текст для LLM
            pipeline_logger.info(f"  > {company_name}: Generating FINAL description using LLM with combined text (len: {len(text_src_for_llms)})...")
            try:
                final_description = await generate_description_openai_async(
                     openai_client=openai_client, llm_config=llm_config, company_name=company_name,
                     about_snippet=text_src_for_llms, # Передаем потенциально обогащенный текст
                     homepage_root=hp_root, 
                     linkedin_url=li_url_found_serper, 
                     context_text=context_text
                )
                if final_description:
                    result_data["description"] = final_description
                    pipeline_logger.info(f"  > {company_name}: Final description generated (len {len(final_description)}).")
                else:
                    pipeline_logger.warning(f"  > {company_name}: Final LLM description generation returned empty result.")
                    # Если run_standard_pipeline был false, то тут будет "Description not generated" или "Standard pipeline not run" (если не перезаписано)
                    # Если run_standard_pipeline был true, то он уже мог записать свою версию или ошибку.
                    # Оставляем как есть, если LLM вернул пустоту на финальном этапе.
                    if result_data["description"] == "Description not generated": # Только если не было попытки от стандартного
                         result_data["description"] = "Final LLM: No description generated"
                    manual_check_flag = True # В любом случае, если финальный LLM не сработал - повод для проверки
            except Exception as e_llm_final:
                pipeline_logger.error(f"  > {company_name}: Final LLM description generation FAILED: {e_llm_final}")
                # Аналогично, сохраняем предыдущее состояние description или ставим ошибку
                if result_data["description"] == "Description not generated":
                    result_data["description"] = "Final LLM: Error during generation"
                manual_check_flag = True
        elif run_standard_pipeline: # Если text_src_for_llms пуст, но стандартный пайплайн был включен
            # Значит, стандартный пайплайн не смог собрать текст и уже должен был записать 
            # "Standard LLM: No text source for generation" или аналогичное в result_data["description"]
            # или "Not found" если даже URL не было. Ничего дополнительно тут не делаем.
            pipeline_logger.warning(f"  > {company_name}: No text_src_for_llms available for final LLM, and standard pipeline was run (its result for description stands).")
            # manual_check_flag уже должен быть True из блока стандартного пайплайна
        else: # Если оба пайплайна выключены или не дали текста
             pipeline_logger.warning(f"  > {company_name}: No text_src_for_llms available. Final description cannot be generated.")
             # result_data["description"] уже будет "Description not generated" или "Standard pipeline not run"
             if not run_standard_pipeline : result_data["description"] = "No pipeline run to generate description"
             manual_check_flag = True

    except asyncio.CancelledError:
        pipeline_logger.warning(f"Processing of company '{company_name}' was cancelled.")
        result_data["homepage"] = result_data.get("homepage", "Processing cancelled")
        result_data["linkedin"] = result_data.get("linkedin", "Processing cancelled")
        result_data["description"] = result_data.get("description", "Processing cancelled")
        raise
    except Exception as e_outer:
        pipeline_logger.critical(f"CRITICAL ERROR processing {company_name}: {type(e_outer).__name__} - {e_outer}", exc_info=True)
        result_data["description"] = f"Error: {type(e_outer).__name__}"
        result_data["homepage"] = "Error"
        result_data["linkedin"] = "Error"

    processing_duration = time.time() - start_time_processing
    pipeline_logger.info(f"Finished processing {company_name} in {processing_duration:.2f}s. Std: {run_standard_pipeline}, Deep: {run_llm_deep_search_pipeline}. Result keys: {list(result_data.keys())}")
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
                                        run_llm_deep_search_pipeline=False, # Для консольного run_pipeline пока без LLM Deep Search
                                        llm_deep_search_config=None # Соответственно, конфиг тоже None
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
    context_text: str | None,
    company_col_index: int,
    aiohttp_session: aiohttp.ClientSession,
    sb_client: ScrapingBeeClient,
    llm_config: dict, # llm_config теперь используется только для process_company (стандартного)
    openai_client: AsyncOpenAI,
    serper_api_key: str,
    expected_csv_fieldnames: list[str], # <--- Этот параметр теперь ЕДИНСТВЕННЫЙ ИСТОЧНИК fieldnames
    broadcast_update: callable = None,
    main_batch_size: int = 50,
    # ++ Новые параметры для выбора пайплайнов ++
    run_standard_pipeline: bool = True,
    run_llm_deep_search_pipeline: bool = False,
    llm_deep_search_config: Optional[Dict[str, Any]] = None # Содержит specific_queries
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
                        llm_config=llm_config, # Для стандартного пайплайна
                        openai_client=openai_client,
                        context_text=context_text,
                        serper_api_key=serper_api_key,
                        # ++ Передаем фактические значения из аргументов функции ++
                        run_standard_pipeline=run_standard_pipeline,
                        run_llm_deep_search_pipeline=run_llm_deep_search_pipeline,
                        llm_deep_search_config=llm_deep_search_config
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
                        llm_deep_search_config=None 
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