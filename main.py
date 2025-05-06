import pandas as pd
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import tldextract
from openai import AsyncOpenAI
from scrapingbee import ScrapingBeeClient
import os
from dotenv import load_dotenv
import json
import time
import yaml
import traceback

# Load environment variables
load_dotenv()
SCRAPINGBEE_API_KEY = os.getenv("SCRAPINGBEE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

LLM_CONFIG = None # Global LLM config placeholder

def load_llm_config(config_path="llm_config.yaml") -> dict | None:
    """Loads the ENTIRE content of the YAML configuration file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        if isinstance(config, dict) and 'model' in config: # Check it's a dict AND has model
            print(f"LLM configuration loaded successfully from {config_path}")
            return config 
        elif isinstance(config, dict):
             print(f"Error: LLM config file {config_path} is missing required 'model' key.")
             return None
        else:
             print(f"Error: Content of LLM config file {config_path} is not a dictionary."); 
             return None
    except FileNotFoundError: print(f"Error: LLM config file {config_path} not found."); return None
    except yaml.YAMLError as e: print(f"Error parsing LLM config file {config_path}: {e}"); return None
    except Exception as e: print(f"Error loading LLM config {config_path}: {e}"); return None

def load_and_prepare_company_names(file_path: str, col_index: int = 0) -> list[str] | None:
    """Loads the first column from Excel/CSV, handles headers, returns list of names."""
    df_loaded = None
    read_params = {"usecols": [col_index], "header": 0}
    try:
        reader = pd.read_excel if file_path.lower().endswith(('.xlsx', '.xls')) else pd.read_csv
        df_loaded = reader(file_path, **read_params)
    except (ValueError, ImportError, FileNotFoundError) as ve:
        print(f" Initial read failed for {file_path}, trying header=None: {ve}")
        read_params["header"] = None
        try: df_loaded = reader(file_path, **read_params)
        except Exception as read_err_no_header: print(f" Error reading {file_path} even with header=None: {read_err_no_header}"); return None
    except Exception as read_err: print(f" Error reading file {file_path}: {read_err}"); return None
    if df_loaded is not None and not df_loaded.empty:
        company_names = df_loaded.iloc[:, 0].astype(str).str.strip().tolist()
        valid_names = [name for name in company_names if name and name.lower() not in ['nan', '']]
        if valid_names: return valid_names
        else: print(f" No valid names in first column of {file_path}."); return None
    else: print(f" Could not load data from first column of {file_path}."); return None

def load_context_file(context_file_path: str) -> str | None:
    """Loads the content of a context text file."""
    if os.path.exists(context_file_path):
        try:
            with open(context_file_path, 'r', encoding='utf-8') as f:
                context_text = f.read().strip()
            print(f"Successfully loaded context from: {context_file_path}")
            return context_text
        except Exception as e:
            print(f"Error reading context file {context_file_path}: {e}")
            return None
    else:
        print(f"Context file not found: {context_file_path}")
        return None

def save_results_csv(data: list[dict], output_file_path: str) -> None:
    """Saves the processed data to a CSV file."""
    if not data: print(f"No data to save for {output_file_path}."); return
    # Determine columns dynamically from the first data dictionary if possible
    # This handles cases where LLM returns variable keys in JSON mode
    columns = list(data[0].keys()) if data else [] 
    df = pd.DataFrame(data, columns=columns)
    try:
        output_dir = os.path.dirname(output_file_path)
        if output_dir and not os.path.exists(output_dir): os.makedirs(output_dir); print(f"Created output dir: {output_dir}")
        df.to_csv(output_file_path, index=False, encoding='utf-8')
        print(f"Results saved to {output_file_path}")
    except Exception as e: print(f"Error saving CSV to {output_file_path}: {e}")

async def find_urls_with_serper_async(session: aiohttp.ClientSession, company_name: str, context_text: str | None) -> tuple[str | None, str | None]:
    """Async: Finds homepage and LinkedIn URL using Serper.dev, incorporating context_text."""
    if not SERPER_API_KEY: print("SERPER_API_KEY not found."); return None, None
    
    homepage_url, linkedin_url = None, None
    serper_search_url = "https://google.serper.dev/search"
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    # print(f"--- Async Serper.dev DEBUG for {company_name} ---") # Reduced logging

    # Append context to search queries if available
    context_query_part = f" {context_text}" if context_text else ""
    # Limit context length to avoid overly long queries
    if len(context_query_part) > 100: context_query_part = context_query_part[:100] + "..."

    try:
        # Find homepage
        search_query_homepage = f'{company_name}{context_query_part} official website'
        payload_homepage = json.dumps({"q": search_query_homepage, "num": 3})
        async with session.post(serper_search_url, headers=headers, data=payload_homepage, timeout=15) as resp_hp:
            if resp_hp.status != 200:
                 print(f"Serper HP search failed for {company_name}. Status: {resp_hp.status}. Response: {await resp_hp.text()}")
            else:
                results_homepage_dict = await resp_hp.json()
                if results_homepage_dict.get("organic"):
                    for res in results_homepage_dict["organic"]:
                        link = res.get("link")
                        if link: homepage_url = link; break 
        
        await asyncio.sleep(0.3) # Short sleep between calls
        
        # Find LinkedIn URL
        search_query_linkedin = f'{company_name}{context_query_part} site:linkedin.com/company'
        payload_linkedin = json.dumps({"q": search_query_linkedin, "num": 3})
        async with session.post(serper_search_url, headers=headers, data=payload_linkedin, timeout=15) as resp_li:
             if resp_li.status != 200:
                 print(f"Serper LI search failed for {company_name}. Status: {resp_li.status}. Response: {await resp_li.text()}")
             else:
                results_linkedin_dict = await resp_li.json()
                if results_linkedin_dict.get("organic"):
                    for res in results_linkedin_dict["organic"]:
                        link = res.get("link")
                        if link and "linkedin.com/company/" in link: linkedin_url = link; break
                        
    except asyncio.TimeoutError:
        print(f"Timeout during async Serper.dev search for {company_name}")
    except aiohttp.ClientError as client_err:
         print(f"AIOHttp client error during Serper.dev search for {company_name}: {client_err}")
    except Exception as e:
        print(f"Generic exception during async Serper.dev search for {company_name}: {type(e).__name__} - {e}")
        # traceback.print_exc()

    # print(f"--- End Async Serper.dev DEBUG for {company_name} --- Found: HP={homepage_url}, LI={linkedin_url}")
    return homepage_url, linkedin_url

def scrape_page_data(url: str, client: ScrapingBeeClient) -> tuple[str | None, str | None, str | None]:
    """Scrapes a page using ScrapingBee, trying simple fetch first, then fallback to JS rendering."""
    if not url or not client: 
        # print("Sync Scrape skipped: No URL or client.")
        return None, None, None

    title, root_domain, html_content = None, None, None
    
    # --- Attempt 1: Simple Fetch (render_js=False) ---
    # print(f"Sync Scraping (Attempt 1: Simple): {url}")
    try:
        response_simple = client.get(url, params={'render_js': False, 'timeout': 15000})
        
        if response_simple.status_code == 200:
            html_simple = response_simple.text
            soup_simple = BeautifulSoup(html_simple, 'html.parser')
            title_tag_simple = soup_simple.find('title')
            title_simple = title_tag_simple.string.strip() if title_tag_simple else None
            
            # Check if simple fetch was successful enough (got 200 OK and found a title)
            if title_simple:
                html_content, title = html_simple, title_simple
                extracted_domain = tldextract.extract(url)
                root_domain = f"{extracted_domain.domain}.{extracted_domain.suffix}"
                return title, root_domain, html_content
            else:
                # print(" Sync Simple fetch OK, but no title found. Falling back.")
                pass
        else:
            # print(f" Sync Simple fetch failed (Status: {response_simple.status_code}). Falling back.")
            pass
            
    except Exception as e:
        print(f"Error during sync simple fetch for {url}: {e}. Falling back.")

    # --- Attempt 2: JS Rendering Fetch (Fallback) ---
    # This part executes only if the simple fetch failed or was deemed insufficient
    # print(f"Sync Scraping (Attempt 2: JS Render): {url}")
    try:
        response_js = client.get(url, params={'render_js': True, 'timeout': 25000, 'wait': 2000}) # Keep longer timeout, add wait 
        
        if response_js.status_code == 200:
            html_content = response_js.text
            soup_js = BeautifulSoup(html_content, 'html.parser')
            title_tag_js = soup_js.find('title')
            title = title_tag_js.string.strip() if title_tag_js else None
            extracted_domain = tldextract.extract(url)
            root_domain = f"{extracted_domain.domain}.{extracted_domain.suffix}"
            # print(f" Sync JS render successful. Title: '{title}'")
            # Return data from JS render attempt
            return title, root_domain, html_content 
        else:
            # print(f"Sync Failed JS render scrape {url}. Status: {response_js.status_code}")
            return None, None, None # Failed both attempts
            
    except Exception as e:
        print(f"Error during sync JS render fetch for {url}: {e}")
        return None, None, None # Failed both attempts

def validate_page(company_name: str, title: str | None, domain: str | None) -> bool:
    if not title and not domain: 
        return False
        
    company_name_lower = company_name.lower()
    normalized_domain = domain.lower().replace("-", "") if domain else ""
    title_lower = title.lower() if title else ""

    # Simple checks first
    if company_name_lower in title_lower: 
        return True
    if domain and company_name_lower.replace(" ", "").replace(",", "").replace(".", "") in normalized_domain: 
        return True
    
    # Prepare parts for check if simple checks failed
    parts_to_check = []
    parts = [p for p in company_name_lower.split() if len(p) > 2] 
    if parts: # If we found parts > 2 chars
        parts_to_check = parts
    elif len(company_name_lower) > 2: # Otherwise, if the whole name is > 2 chars, use it
        parts_to_check = [company_name_lower]
        
    # Iterate through parts if we have any valid ones
    if parts_to_check:
        for part in parts_to_check:
            title_match = title and part in title_lower
            domain_match = domain and part in normalized_domain
            if title_match or domain_match:
                return True
                
    # If no checks passed
    return False

def extract_text_for_description(html_content: str | None) -> str | None:
    if not html_content: return None
    soup = BeautifulSoup(html_content, 'html.parser')
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'): return meta_desc['content'].strip()
    for selector in ['main p', 'article p', 'div[role="main"] p', 'body > div p', 'body > p']: 
        try:
            first_p = soup.select_one(selector)
            if first_p:
                p_text = first_p.get_text(strip=True)
                if len(p_text) > 50: return p_text
        except Exception: continue
    for keyword_base in ['about', 'о компании', 'о нас']:
        elements = soup.find_all(lambda tag: tag.name in ['h1','h2','h3','p','div'] and keyword_base in tag.get_text(strip=True).lower())
        for el in elements:
            parent = el.find_parent(['section', 'div'])
            if parent:
                p_tags = parent.find_all('p', limit=3)
                text_block = " ".join(p.get_text(strip=True) for p in p_tags)
                if len(text_block) > 50: return text_block.strip()
            elif el.name == 'p' and len(el.get_text(strip=True)) > 50: return el.get_text(strip=True)
    return None

async def generate_description_openai_async(company_name: str, homepage_root: str | None, linkedin_url: str | None, about_snippet: str | None, llm_config: dict, openai_client: AsyncOpenAI, context_text: str | None) -> dict | str | None:
    """Async: Generates LLM output using config, also incorporating context_text."""
    if not about_snippet: print(f"No text for LLM input ({company_name})."); return None
    if not llm_config or not isinstance(llm_config, dict): print(f"Invalid LLM config ({company_name})."); return None
    model_name = llm_config.get('model')
    if not model_name: print(f"LLM model missing in config ({company_name})."); return None
    messages_template = llm_config.get('messages')
    if not isinstance(messages_template, list):
        print(f"LLM config missing/invalid 'messages' list ({company_name})."); return None
    formatted_messages = []
    format_data = {
        "company": company_name, 
        "website_url": homepage_root or "N/A", 
        "linkedin_url": linkedin_url or "N/A", 
        "about_snippet": about_snippet[:4000],
        "user_provided_context": context_text or "Not available" # Add context here
    }
    try:
        for msg_template in messages_template:
            if isinstance(msg_template, dict) and 'role' in msg_template and 'content' in msg_template:
                formatted_content = msg_template['content'].format(**format_data)
                formatted_messages.append({"role": msg_template['role'], "content": formatted_content})
            else: print(f"Warning: Invalid message template item in llm_config ({company_name})")
    except KeyError as e: print(f"Msg template formatting error ({company_name}): Missing key {e}"); return None
    except Exception as fmt_err: print(f"Msg template formatting error ({company_name}): {fmt_err}"); return None
    api_params = {k: v for k, v in llm_config.items() if k != 'messages'}
    api_params['model'] = model_name
    api_params['messages'] = formatted_messages
    try:
        response = await openai_client.chat.completions.create(**api_params)
        if response.choices:
            response_content = response.choices[0].message.content.strip()
            response_format = api_params.get("response_format")
            if isinstance(response_format, dict) and response_format.get("type") == "json_object":
                try:
                    parsed_json = json.loads(response_content)
                    return parsed_json # Return dict
                except json.JSONDecodeError:
                    print(f"Error: OpenAI response not valid JSON ({company_name})."); return None # Indicate error
            else: return response_content # Return string
        else: print(f"OpenAI no choices ({company_name})."); return None # Indicate error
    except Exception as e: print(f"OpenAI API error ({company_name}): {type(e).__name__}"); return None # Indicate error

async def process_company(company_name: str, aiohttp_session: aiohttp.ClientSession, sb_client: ScrapingBeeClient, llm_config: dict, openai_client: AsyncOpenAI, context_text: str | None) -> dict:
    """Async: Processes a single company. Returns a dictionary for the output row."""
    print(f" Starting async process for: {company_name} (Context: {bool(context_text)})")
    start_time = time.time()
    result_data = {"name": company_name, "homepage": "Not found", "linkedin": "Not found", "description": ""} # Base result
    text_src = None
    manual_check_flag = False # Use a flag instead of modifying result_data["description"] mid-way

    try:
        hp_url_found, li_url_found = await find_urls_with_serper_async(aiohttp_session, company_name, context_text)
        result_data["linkedin"] = li_url_found or "Not found"
        if not sb_client: raise ValueError("ScrapingBee client error") 

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

        if hp_data:
            hp_title, hp_root, hp_html = hp_data
            result_data["homepage"] = hp_root 
            if hp_title and hp_root:
                if validate_page(company_name, hp_title, hp_root): text_src = extract_text_for_description(hp_html)
                else: print(f" > {company_name}: HP validation FAILED."); manual_check_flag = True
            else: print(f" > {company_name}: Insufficient HP scrape data."); manual_check_flag = True
        elif hp_url_found: 
             print(f" > {company_name}: HP scrape failed/timed out.")
             extracted_hp = tldextract.extract(hp_url_found); result_data["homepage"] = f"{extracted_hp.domain}.{extracted_hp.suffix}" if extracted_hp.domain else hp_url_found
             manual_check_flag = True
        else: print(f" > {company_name}: HP URL not found."); manual_check_flag = True
        
        if li_data and (not text_src or manual_check_flag):
            li_title, _, li_html = li_data
            if li_title and company_name.lower() in li_title.lower(): 
                 if not text_src: text_src = extract_text_for_description(li_html)
                 if text_src: manual_check_flag = False # Found text via LI, potentially override earlier manual flag
            elif not text_src: print(f" > {company_name}: LI validation FAILED."); manual_check_flag = True
        elif li_url_found and (not text_src or manual_check_flag):
             print(f" > {company_name}: LI scrape failed/timed out.")
             if not text_src: manual_check_flag = True 
             
        # --- Generate LLM Output --- 
        llm_generated_output = None
        if text_src:
             print(f" > {company_name}: Generating LLM output...")
             llm_generated_output = await generate_description_openai_async(company_name, result_data["homepage"], result_data["linkedin"], text_src, llm_config, openai_client, context_text)
        else:
            print(f" > {company_name}: No text found for LLM.")
            manual_check_flag = True # Ensure manual check if no text

        # --- Finalize Result Dictionary --- 
        if isinstance(llm_generated_output, dict):
            # If LLM returned dict (JSON mode ok), merge it into result_data
            print(f" > {company_name}: LLM OK (JSON).")
            result_data.pop('description', None) # Remove default empty description
            result_data.update(llm_generated_output) # Add keys from LLM output
        elif isinstance(llm_generated_output, str):
            # If LLM returned string, put it in 'description'
            print(f" > {company_name}: LLM OK (Text).")
            result_data['description'] = llm_generated_output
            # If JSON was expected, flag for manual check
            if isinstance(llm_config.get("response_format"), dict) and llm_config["response_format"].get("type") == "json_object":
                print(" > Warning: Expected JSON, got Text.")
                manual_check_flag = True
        elif llm_generated_output is None and text_src:
            # If generation failed but we had text
            print(f" > {company_name}: LLM generation failed.")
            result_data['description'] = "Generation Error"
            manual_check_flag = True
            
        # If manual check is needed and description wasn't set to an error already
        if manual_check_flag and result_data.get('description',"") == "":
            result_data['description'] = "Manual check required"
            
    except Exception as e:
        print(f"!! Unhandled exception in process_company for {company_name}: {type(e).__name__} - {e}")
        traceback.print_exc()
        result_data["description"] = f"Processing Error: {type(e).__name__}"
        
    elapsed = time.time() - start_time
    print(f" Finished async process for: {company_name} in {elapsed:.2f}s.")
    return result_data

async def scrape_page_data_async(url: str, sb_client: ScrapingBeeClient) -> tuple[str | None, str | None, str | None]:
    """Async wrapper for the blocking scrape_page_data function."""
    if not url or not sb_client:
        return None, None, None
    # print(f" Scheduling scrape_page_data in thread for: {url}")
    try:
        # Run the synchronous function in a separate thread
        result = await asyncio.to_thread(scrape_page_data, url, sb_client)
        # print(f" Finished scrape_page_data in thread for: {url}")
        return result
    except Exception as e:
        print(f"Error running scrape_page_data in thread for {url}: {e}")
        return None, None, None

async def main():
    input_dir = "input"
    output_dir = "output"
    final_output_dir = os.path.join(output_dir, "final_outputs") 
    llm_config_file = "llm_config.yaml" 
    company_col_index = 0 
    for dir_path in [output_dir, final_output_dir]: 
        if not os.path.exists(dir_path):
            os.makedirs(dir_path); print(f"Created directory: {dir_path}")
            
    llm_config = load_llm_config(llm_config_file) 
    if not llm_config: print(f"Failed to load LLM config from {llm_config_file}. Exiting."); exit()
        
    missing_api_keys = []
    if not SERPER_API_KEY: missing_api_keys.append("SERPER_API_KEY") 
    if not SCRAPINGBEE_API_KEY: missing_api_keys.append("SCRAPINGBEE_API_KEY")
    if not OPENAI_API_KEY: missing_api_keys.append("OPENAI_API_KEY")
    if missing_api_keys: print(f"Error: Missing API keys in .env: {', '.join(missing_api_keys)}. Exiting."); exit()
    
    print(f"Starting ASYNC batch company processing. Input: '{input_dir}', Final Outputs: '{final_output_dir}', LLM Config: '{llm_config_file}'")
    supported_extensions = ('.xlsx', '.xls', '.csv')
    overall_results = []
    processed_files_count = 0
    if not os.path.exists(input_dir): print(f"Error: Input directory '{input_dir}' not found. Exiting."); exit()
    sb_client = ScrapingBeeClient(api_key=SCRAPINGBEE_API_KEY) if SCRAPINGBEE_API_KEY else None
    if not sb_client and SCRAPINGBEE_API_KEY: print("Warning: ScrapingBeeClient potentially failed to initialize?")
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) 
    async with aiohttp.ClientSession() as session:
        for filename in os.listdir(input_dir):
            original_input_path = os.path.join(input_dir, filename)
            if os.path.isfile(original_input_path) and filename.lower().endswith(supported_extensions):
                print(f"\n>>> Processing file: {filename}")
                base_name, _ = os.path.splitext(filename)
                
                # --- Generate Unique Output Filename --- 
                output_file_base = os.path.join(final_output_dir, f"{base_name}_output")
                output_file_path = f"{output_file_base}.csv"
                counter = 1
                while os.path.exists(output_file_path):
                    output_file_path = f"{output_file_base}_{counter}.csv"
                    counter += 1
                # --- --- --- --- --- --- ---
                
                # Attempt to load context for this data file
                context_file_name = f"{base_name}_context.txt"
                context_file_path = os.path.join(input_dir, context_file_name)
                context_text = load_context_file(context_file_path)
                if not context_text:
                    print(f"Warning: No context found for {filename}. Proceeding without it.")
                
                company_names = load_and_prepare_company_names(original_input_path, company_col_index)
                if not company_names: print(f"--- Skipping file {filename} due to loading issues or no valid names."); continue
                print(f" Found {len(company_names)} companies. Creating async tasks...")
                tasks = [asyncio.create_task(process_company(name, session, sb_client, llm_config, openai_client, context_text)) for name in company_names]
                file_task_results = await asyncio.gather(*tasks, return_exceptions=True)
                file_successful_results = []
                exceptions_count = 0
                for result in file_task_results:
                    if isinstance(result, Exception): print(f"!! Task failed: {result}"); exceptions_count += 1
                    elif isinstance(result, dict): file_successful_results.append(result)
                    else: print(f"!! Unexpected result type: {type(result)}")
                print(f"<<< Finished {filename}. Success: {len(file_successful_results)}, Failures: {exceptions_count}")
                if file_successful_results:
                    save_results_csv(file_successful_results, output_file_path) # Use unique path
                    overall_results.extend(file_successful_results)
                    processed_files_count += 1
                else: print(f" No successful results for {filename}.")
            else: print(f"Skipping non-supported/file item: {filename}")
    # --- Final Summary --- 
    if processed_files_count > 0:
        print(f"\nSuccessfully processed {processed_files_count} file(s). Total successful results: {len(overall_results)}.")
        if overall_results:
            print("\n--- Consolidated JSON Output ---")
            print(json.dumps(overall_results, indent=2, ensure_ascii=False))
            print("--- --- --- --- --- --- ---")
    else: print(f"No supported files processed successfully in '{input_dir}'.")
    print("Async batch processing finished.")

if __name__ == "__main__":
    # Set policy for Windows if needed (often helps with aiohttp/asyncio)
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred in the main async execution: {e}")
        traceback.print_exc() 