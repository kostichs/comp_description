"""
HubSpot Pipeline Adapter Module

Extends the base PipelineAdapter to include HubSpot integration
"""

import logging
import os
import datetime # Added for HubSpotAdapter
from typing import Dict, List, Any, Optional, Tuple, Callable, Union
from pathlib import Path
import aiohttp
from openai import AsyncOpenAI
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient
from dotenv import load_dotenv
from urllib.parse import urlparse # Added for HubSpotAdapter
import asyncio # Add asyncio import
import time

from src.pipeline.adapter import PipelineAdapter
from src.pipeline.core import process_companies
from src.data_io import load_and_prepare_company_names, save_results_csv, load_session_metadata, save_session_metadata
from .client import HubSpotClient

logger = logging.getLogger(__name__)

class HubSpotAdapter:
    """
    Adapter for HubSpot integration with main company processing pipeline.
    
    Provides:
    - Check if company exists in HubSpot by domain
    - Extract existing description if it's current
    - Save new descriptions to HubSpot
    """
    
    def __init__(self, api_key: Optional[str] = None, max_age_months: int = 6):
        """
        Initialize the adapter.
        
        Args:
            api_key (str, optional): HubSpot API key. If not specified, 
                                     will be taken from HUBSPOT_API_KEY environment variable.
            max_age_months (int): Maximum description age in months.
                                  Descriptions older than this will be considered outdated.
        """
        # Load environment variables if api_key is not passed explicitly and not in .env
        if api_key is None:
            load_dotenv() # Make sure .env is loaded
            api_key = os.getenv("HUBSPOT_API_KEY")

        self.client = HubSpotClient(api_key=api_key) # Pass api_key to client
        self.max_age_months = max_age_months
        logger.info(f"HubSpot Adapter initialized with max age: {max_age_months} months. API key {'present' if api_key else 'MISSING'}.")
    
    async def check_company_description(self, company_name: str, url: str, aiohttp_session=None, sb_client=None) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check for current company description in HubSpot.
        Search by original and final domain (after redirects).
        
        Args:
            company_name (str): Company name
            url (str): Company URL
            aiohttp_session: HTTP session for redirect checking
            sb_client: ScrapingBee client
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: 
                - First element (description_is_fresh): True if current description found (skip processing), otherwise False.
                - Second element: Dictionary with company data if found, otherwise None.
        """
        if not self.client.api_key:
            logger.warning("HubSpot API key not available in HubSpotAdapter. Skipping check.")
            return False, None # Don't skip, no key

        if not url:
            logger.info(f"No URL provided for company '{company_name}', skipping HubSpot check")
            return False, None # Don't skip, no URL
        
        try:
            logger.info(f"Checking HubSpot for company '{company_name}' with URL '{url}'")
            
            # Use new function to search by multiple domains
            company, used_domain = await search_company_by_multiple_domains(
                self.client, url, aiohttp_session, sb_client
            )
            
            if not company:
                logger.info(f"Company '{company_name}' not found in HubSpot by any domain")
                return False, None # Don't skip, company not found
            
            properties = company.get("properties", {})
            description = properties.get("ai_description") 
            updated_timestamp = properties.get("ai_description_updated")
            linkedin_page = properties.get("linkedin_company_page") # Extract LinkedIn URL
            
            logger.info(
                f"Found company in HubSpot by domain '{used_domain}': {properties.get('name')}, "
                f"description length: {len(description) if description else 0}, "
                f"updated: {updated_timestamp}, LinkedIn: {linkedin_page}"
            )
            
            if description and updated_timestamp:
                is_fresh = self.client.is_description_fresh(updated_timestamp, self.max_age_months)
                if is_fresh:
                    logger.info(
                        f"Using existing description for '{company_name}' from HubSpot. "
                        f"Last updated: {updated_timestamp}"
                    )
                    # Found fresh description, so return True (skip processing)
                    # Return company to have access to linkedin_page in calling code
                    return True, company 
                else:
                    logger.info(
                        f"Description for '{company_name}' in HubSpot is outdated. "
                        f"Last updated: {updated_timestamp}"
                    )
                    # Description is outdated, don't skip processing
                    return False, company 
            else:
                logger.info(f"No AI description or timestamp found for '{company_name}' in HubSpot")
                # No description/date, don't skip processing
                return False, company
        
        except Exception as e:
            logger.error(f"Error checking company '{company_name}' in HubSpot: {e}", exc_info=True)
            return False, None # Error, don't skip processing
    
    async def create_company(
        self, 
        company_name: str, 
        url: str, 
        description: str,
        linkedin_url: Optional[str] = None  # Add LinkedIn URL
    ) -> Optional[Dict[str, Any]]:
        """
        Create new company in HubSpot.
        """
        if not self.client.api_key:
            logger.warning("HubSpot API key not available in HubSpotAdapter. Skipping creation.")
            return None

        if not url:
            logger.info(f"No URL provided for company '{company_name}', cannot create in HubSpot")
            return None
        
        try:
            domain = self._extract_domain_from_url(url)
            if not domain:
                logger.warning(f"Could not extract domain from URL '{url}' for company '{company_name}'")
                return None
            
            now = datetime.datetime.now().strftime("%Y-%m-%d")
            
            properties = {
                "name": company_name,
                "domain": domain,
                "ai_description": description, # Use HubSpot custom field
                "ai_description_updated": now # Use HubSpot custom field
            }
            if linkedin_url: # Add LinkedIn if available
                properties["linkedin_company_page"] = linkedin_url
            
            logger.info(f"Creating new company '{company_name}' with domain '{domain}' in HubSpot. LinkedIn: {linkedin_url}")
            company = await self.client.create_company(domain, properties)
            
            if company:
                logger.info(f"Successfully created company '{company_name}' in HubSpot")
                return company
            else:
                logger.error(f"Failed to create company '{company_name}' in HubSpot")
                return None
        
        except Exception as e:
            logger.error(f"Error creating company '{company_name}' in HubSpot: {e}", exc_info=True)
            return None
    
    async def save_company_description(
        self, 
        company_data: Optional[Dict[str, Any]], 
        company_name: str,
        url: str,
        description: str,
        linkedin_url: Optional[str] = None, # Add LinkedIn URL
        aiohttp_session=None, # Add HTTP session
        sb_client=None # Add ScrapingBee client
    ) -> Tuple[bool, Optional[str]]:
        """
        Save company description to HubSpot.
        Returns tuple (success, HubSpot company ID or None).
        """
        if not self.client.api_key:
            logger.warning("HubSpot API key not available in HubSpotAdapter. Skipping save.")
            return False, None # Return ID as None

        company_id_to_return: Optional[str] = None
        try:
            if not company_data and url: # If company not found earlier, search again
                # Use search by multiple domains
                company_data, used_domain = await search_company_by_multiple_domains(
                    self.client, url, aiohttp_session, sb_client
                )
                if company_data:
                    logger.info(f"Found company '{company_name}' in HubSpot by domain: {used_domain}")
            
            if company_data:
                company_id = company_data.get("id")
                company_id_to_return = company_id # Save ID for return
                now = datetime.datetime.now().strftime("%Y-%m-%d")
                properties_to_update = {
                    "ai_description": description, # Use HubSpot custom field
                    "ai_description_updated": now # Use HubSpot custom field
                }
                if linkedin_url: # Add LinkedIn if available
                    properties_to_update["linkedin_company_page"] = linkedin_url
                
                logger.info(f"Updating description and LinkedIn for company '{company_name}' (ID: {company_id}) in HubSpot. LinkedIn: {linkedin_url}")
                result = await self.client.update_company_properties(company_id, properties_to_update)
                
                if result:
                    logger.info(f"Successfully updated description for '{company_name}' in HubSpot")
                    return True, company_id_to_return # Return ID
                else:
                    logger.error(f"Failed to update description for '{company_name}' in HubSpot")
                    return False, None # Return ID as None
            else: # Company not found, create new one
                logger.info(f"Company '{company_name}' not found in HubSpot, creating new entry.")
                new_company = await self.create_company(company_name, url, description, linkedin_url)
                if new_company:
                    company_id_to_return = new_company.get("id")
                    return True, company_id_to_return # Return ID of new company
                return False, None # Return ID as None
        
        except Exception as e:
            logger.error(f"Error saving description for '{company_name}' in HubSpot: {e}", exc_info=True)
            return False, None # Return ID as None
    
    def _extract_domain_from_url(self, url: str) -> str:
        """
        Extract domain from URL.
        """
        return self.client._normalize_domain(url) # Use method from HubSpotClient
    
    def get_company_details_from_hubspot_data(self, company_data: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
        """
        Extract description, timestamp and LinkedIn URL from HubSpot company data.
        """
        properties = company_data.get("properties", {})
        description = properties.get("ai_description", "") 
        timestamp = properties.get("ai_description_updated", "") 
        linkedin_url = properties.get("linkedin_company_page") # Can be None
        return description, timestamp, linkedin_url

class HubSpotPipelineAdapter(PipelineAdapter):
    """
    Pipeline adapter with HubSpot integration
    
    This class extends the base PipelineAdapter to include
    functionality for checking and updating data in HubSpot.
    """
    
    def __init__(self, config_path: str = "llm_config.yaml", input_file: Optional[str] = None, session_id: Optional[str] = None):
        super().__init__(config_path, input_file, session_id) # Pass session_id
        self.hubspot_adapter: Optional[HubSpotAdapter] = None
        # use_hubspot and max_age_months will be initialized in self.setup() from llm_config
        # self.use_hubspot = True # Will be determined in setup
        # self.max_age_months = 6 # Will be determined in setup
        
        # Attribute for storing deduplication information
        self.deduplication_info = None
    
    async def setup(self) -> bool:
        """
        Set up the pipeline configuration and dependencies, including HubSpot.
        """
        # First perform basic setup from PipelineAdapter
        setup_successful = await super().setup()
        if not setup_successful:
            return False

        # Then set up HubSpot integration
        # API key should be in self.api_keys['hubspot'], loaded in processing_runner.py
        hubspot_api_key = self.api_keys.get("hubspot")
        
        # use_hubspot_integration is taken from llm_config.yaml
        self.use_hubspot = self.llm_config.get("use_hubspot_integration", False) # Default False, if not specified
        self.max_age_months = self.llm_config.get("hubspot_description_max_age_months", 6)
        
        if self.use_hubspot:
            if hubspot_api_key:
                self.hubspot_adapter = HubSpotAdapter(api_key=hubspot_api_key, max_age_months=self.max_age_months)
                logger.info(f"HubSpot integration enabled via config. Max description age: {self.max_age_months} months.")
            else:
                logger.warning("HubSpot integration is enabled in config, but HUBSPOT_API_KEY is missing. HubSpot will not be used.")
                self.use_hubspot = False # Turn off if there is no key
        else:
            logger.info("HubSpot integration is disabled via config or HUBSPOT_API_KEY.")
            
        return True # Return True if basic setup was successful

    async def run_pipeline_for_file(self, input_file_path: str | Path, output_csv_path: str | Path, 
                                   pipeline_log_path: Path, # Changed type to Path
                                   session_dir_path: Path, llm_config: Dict[str, Any],
                                   context_text: str | None, company_col_index: int, 
                                   aiohttp_session: aiohttp.ClientSession,
                                   sb_client: CustomScrapingBeeClient, openai_client: AsyncOpenAI,
                                   serper_api_key: str, # Keep, as it's used in process_companies
                                   expected_csv_fieldnames: list[str], broadcast_update: Optional[Callable] = None,
                                   main_batch_size: int = 5,
                                   run_llm_deep_search_pipeline: bool = True,
                                   write_to_hubspot: bool = True) -> tuple[int, int, list[dict]]:
        """
        Run the pipeline for a specific input file with HubSpot integration
        """
        # Run standard file processing with URL normalization and duplicate removal
        logger.info(f"Normalizing URLs and removing duplicates in input file: {input_file_path}")
        
        try:
            # Create temporary file for processed data
            processed_file_path = session_dir_path / f"processed_{Path(input_file_path).name}"
            
            # Import normalization and deduplication function
            from normalize_urls import normalize_and_remove_duplicates
            
            # Call async function normalize_and_remove_duplicates
            # Make sure to pass session_id
            normalized_file, dedup_info = await normalize_and_remove_duplicates(
                str(input_file_path), 
                str(processed_file_path),
                session_id_for_metadata=self.session_id, # Pass session_id
                scrapingbee_client=sb_client # <--- Add sb_client here
            )
            
            if normalized_file:
                logger.info(f"Successfully processed {input_file_path} (URL check, dedup), saved to {normalized_file}")
                logger.info(f"Processing details: {dedup_info}")
                # Use processed file instead of original
                input_file_path = normalized_file
                
                # Save deduplication and URL check information for later use
                # self.deduplication_info can now contain more detailed information from dedup_info
                self.deduplication_info = dedup_info 
                
                # Additionally, if needed to update session metadata at this stage (although normalize_and_remove_duplicates already does this)
                # Can consider whether to duplicate logic or rely on internal update in normalize_and_remove_duplicates.
                # For now, self.deduplication_info is saved for possible use in other parts of HubSpotPipelineAdapter.

            elif dedup_info and dedup_info.get("error"):
                logger.error(f"Failed to process {input_file_path} (URL check, dedup): {dedup_info.get('error')}. Using original file.")
                # In case of error, can also save dedup_info to session metadata if needed
                # For example, by adding them to self.session_data or a special field.
            else:
                logger.warning(f"Processing {input_file_path} (URL check, dedup) did not return a file. Using original file.")
        except Exception as e:
            logger.error(f"Error processing {input_file_path}: {e}")
            logger.warning("Using original file without normalization and deduplication")
            
        # Create necessary directories
        input_file_path = Path(input_file_path)
        output_csv_path = Path(output_csv_path)
        structured_data_dir = session_dir_path / "json"
        structured_data_dir.mkdir(exist_ok=True)
        structured_data_json_path = structured_data_dir / f"{self.session_id or 'results'}.json"

        # Load company data remains the same
        company_data_list = load_and_prepare_company_names(input_file_path, company_col_index)
        if not company_data_list:
            logger.error(f"No valid company names in {input_file_path}")
            return 0, 0, []
            
        # Create or clear CSV file before starting processing
        save_results_csv([], output_csv_path, expected_csv_fieldnames, append_mode=False)
        logger.info(f"Created empty CSV file with headers at {output_csv_path}")

        all_results: List[Dict[str, Any]] = []
        success_count = 0
        failure_count = 0
        
        companies_to_process_standard: List[Dict[str, Any]] = []
        companies_with_template_descriptions: List[Dict[str, Any]] = []  # For duplicates and dead links
        
        if self.use_hubspot and self.hubspot_adapter:
            logger.info("HubSpot integration is active. Checking companies before processing...")
            for i, company_info_dict in enumerate(company_data_list):
                company_name = company_info_dict["name"]
                company_url = company_info_dict.get("url")
                company_status = company_info_dict.get("status", "VALID")  # Default VALID for old format

                # If company is marked as duplicate or with dead link, create template description
                if company_status in ["DUPLICATE", "DEAD_URL"]:
                    if company_status == "DUPLICATE":
                        template_description = f"This is a duplicate entry. The company '{company_name}' with domain '{company_url}' was already processed earlier in this dataset."
                    else:  # DEAD_URL
                        template_description = f"Unable to access website. The URL '{company_url}' for company '{company_name}' is not accessible or does not exist."
                    
                    template_result = {
                        "Company_Name": company_name,
                        "Official_Website": company_url or "",
                        "LinkedIn_URL": "",
                        "Description": template_description,
                        "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "Data_Source": "Template",
                        "HubSpot_Company_ID": ""
                    }
                    
                    for field in expected_csv_fieldnames:
                        if field not in template_result:
                            template_result[field] = ""
                    
                    companies_with_template_descriptions.append(template_result)
                    logger.info(f"Company '{company_name}' marked as {company_status}, using template description")
                    continue

                # description_is_fresh will be True if fresh description found and processing can be skipped
                description_is_fresh, hubspot_company_data = await self.hubspot_adapter.check_company_description(company_name, company_url, aiohttp_session, sb_client)
                
                # FIXED: if description_is_fresh == True, it means description is fresh and company exists in HubSpot
                if description_is_fresh and hubspot_company_data:
                    logger.info(f"Company '{company_name}' has a fresh description in HubSpot. Skipping processing.")
                    description, timestamp, linkedin_url = self.hubspot_adapter.get_company_details_from_hubspot_data(hubspot_company_data)
                    hubspot_id = hubspot_company_data.get("id") # Get ID
                    result_from_hubspot = {
                        "Company_Name": company_name,
                        "Official_Website": company_url or hubspot_company_data.get("properties",{}).get("domain",""), 
                        "LinkedIn_URL": linkedin_url or "", 
                        "Description": description,
                        "Timestamp": timestamp,
                        "Data_Source": "HubSpot",
                        "HubSpot_Company_ID": format_hubspot_company_id(hubspot_id) # Add ID to result
                    }
                    
                    for field in expected_csv_fieldnames:
                        if field not in result_from_hubspot:
                            result_from_hubspot[field] = ""

                    all_results.append(result_from_hubspot)
                    
                    # Remove Data_Source field before saving to CSV
                    hubspot_result_for_csv = {key: value for key, value in result_from_hubspot.items() if key != "Data_Source"}
                    save_results_csv([hubspot_result_for_csv], output_csv_path, expected_csv_fieldnames, append_mode=True)
                    success_count +=1
                    if broadcast_update:
                        # Take into account already processed companies for correct progress bar
                        total_companies_count = len(company_data_list)
                        processed_count = len(all_results) # Use length of all_results as count of processed
                        await broadcast_update(self.session_id, {"status": "processing", "progress": (processed_count / total_companies_count) * 100, "message": f"Processed {company_name} (from HubSpot)"})
                else: 
                    # Log from check_company_description already said why we don't skip (not found, outdated, error)
                    # logger.info(f"Company '{company_name}' needs processing or is not fresh in HubSpot.") # This log is now duplicate or inaccurate
                    company_info_dict["hubspot_data"] = hubspot_company_data # Save HubSpot data for update, even if description is outdated
                    companies_to_process_standard.append(company_info_dict)
            logger.info(f"{len(companies_to_process_standard)} companies require standard processing after HubSpot check.")
            logger.info(f"{len(companies_with_template_descriptions)} companies received template descriptions.")
        else: 
            # HubSpot integration is not active. Processing companies by status.
            logger.info("HubSpot integration is not active. Processing companies by status.")
            for company_info_dict in company_data_list:
                company_name = company_info_dict["name"]
                company_url = company_info_dict.get("url")
                company_status = company_info_dict.get("status", "VALID")  # Default VALID for old format

                # If company is marked as duplicate or with dead link, create template description
                if company_status in ["DUPLICATE", "DEAD_URL"]:
                    if company_status == "DUPLICATE":
                        template_description = f"This is a duplicate entry. The company '{company_name}' with domain '{company_url}' was already processed earlier in this dataset."
                    else:  # DEAD_URL
                        template_description = f"Unable to access website. The URL '{company_url}' for company '{company_name}' is not accessible or does not exist."
                    
                    template_result = {
                        "Company_Name": company_name,
                        "Official_Website": company_url or "",
                        "LinkedIn_URL": "",
                        "Description": template_description,
                        "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "Data_Source": "Template",
                        "HubSpot_Company_ID": ""
                    }
                    
                    for field in expected_csv_fieldnames:
                        if field not in template_result:
                            template_result[field] = ""
                    
                    companies_with_template_descriptions.append(template_result)
                    logger.info(f"Company '{company_name}' marked as {company_status}, using template description")
                else:
                    companies_to_process_standard.append(company_info_dict)
            
            logger.info(f"{len(companies_to_process_standard)} companies will be processed by standard pipeline.")
            logger.info(f"{len(companies_with_template_descriptions)} companies received template descriptions.")
        
        # Save companies with template descriptions to CSV
        if companies_with_template_descriptions:
            # Remove Data_Source field from saving to avoid cluttering result file
            template_results_for_csv = []
            for template_result in companies_with_template_descriptions:
                csv_result = {key: value for key, value in template_result.items() if key != "Data_Source"}
                template_results_for_csv.append(csv_result)
            
            save_results_csv(template_results_for_csv, output_csv_path, expected_csv_fieldnames, append_mode=True)
            all_results.extend(companies_with_template_descriptions)
            success_count += len(companies_with_template_descriptions)
            
            # Update progress for each company with template description
            if broadcast_update:
                total_companies_count = len(company_data_list)
                for template_company in companies_with_template_descriptions:
                    processed_count = len(all_results)
                    await broadcast_update(self.session_id, {"status": "processing", "progress": (processed_count / total_companies_count) * 100, "message": f"Processed {template_company['Company_Name']} (template)"})

        # If companies remain for standard processing
        if companies_to_process_standard:
            # Determine if we need to append to CSV/JSON
            # If all_results already contains something (from HubSpot), then we need to append.
            should_append_csv = len(all_results) > 0
            should_append_json = len(all_results) > 0 # Similarly for JSON, if used the same way

            # Convert companies_to_process_standard to format expected by process_companies
            # List[Union[str, Tuple[str, str]]]
            company_names_for_core_processing = []
            for company_dict in companies_to_process_standard:
                name = company_dict['name']
                url = company_dict.get('url')
                if url:
                    company_names_for_core_processing.append((name, url))
                else:
                    company_names_for_core_processing.append(name)

            # Paths for raw data and JSON output in process_companies
            # (they may be overwritten or not used depending on process_companies configuration)
            raw_data_path = session_dir_path / "raw_data"
            raw_data_path.mkdir(exist_ok=True) # Make sure directory exists
            
            # Save JSON file to json folder
            output_json_filename = f"{self.session_id or 'results'}_structured_results.json"
            output_json_path_for_core = structured_data_dir / output_json_filename

            # Call process_companies from src.pipeline.core
            # Make sure to pass all necessary and correct arguments
            std_results = await process_companies( # process_companies returns only list of results
                company_names=company_names_for_core_processing,
                openai_client=openai_client,
                aiohttp_session=aiohttp_session,
                sb_client=sb_client,
                serper_api_key=self.api_keys.get("serper"), # Take from self.api_keys
                llm_config=llm_config,
                raw_markdown_output_path=raw_data_path,
                batch_size=main_batch_size, # Use main_batch_size
                context_text=context_text,
                run_llm_deep_search_pipeline_cfg=run_llm_deep_search_pipeline, # Pass flag
                # run_domain_check_finder_cfg remains default True in process_companies, if different control needed - add
                broadcast_update=broadcast_update,
                output_csv_path=str(output_csv_path), # Pass path to CSV for incremental writing
                output_json_path=str(output_json_path_for_core), # Pass path to JSON
                expected_csv_fieldnames=expected_csv_fieldnames,
                # llm_deep_search_config_override - can add if exists in self
                # second_column_data - don't pass, because URL is already in company_names_for_core_processing
                hubspot_client=self.hubspot_adapter if self.use_hubspot else None, # Pass HubSpot adapter
                use_raw_llm_data_as_description=self.llm_config.get('use_raw_llm_data_as_description', True), # Take from llm_config
                csv_append_mode=should_append_csv, # Use flag for CSV
                json_append_mode=should_append_json, # Use flag for JSON
                already_saved_count=len(all_results),  # Pass count of already saved results
                write_to_hubspot=write_to_hubspot # Pass HubSpot write flag
            )
            
            # process_companies returns only list of results.
            # success_count and failure_count need to be determined based on std_results,
            # or modify process_companies to return them.
            # For now, for simplicity, we'll assume all returned results are successful if they exist.
            # In the ideal case, each element in std_results should have a "status" or "error" field type.
            
            std_success = len([res for res in std_results if res.get("Description")]) # Example approximate count of successful
            std_failure = len(std_results) - std_success # Example approximate count of unsuccessful

            success_count += std_success
            failure_count += std_failure
            
            all_results.extend(std_results)
            # Results are already saved in CSV inside process_companies_batch

        logger.info(f"HubSpotPipelineAdapter finished. Total successes: {success_count}, Total failures: {failure_count}")
        return success_count, failure_count, all_results

async def test_hubspot_pipeline_adapter():
    # Example simple test function (requires environment and file setup)
    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    # Create temporary input_file.xlsx
    import pandas as pd
    temp_input_data = {'Company Name': ['Test Company 1', 'HubSpot'], 'Website': ['www.testcompany1.com', 'hubspot.com']}
    temp_input_df = pd.DataFrame(temp_input_data)
    temp_input_path = Path("temp_input_test.xlsx")
    temp_input_df.to_excel(temp_input_path, index=False)
    
    # Create temporary llm_config.yaml
    temp_llm_config_data = {
        "model": "gpt-3.5-turbo", # or another model
        "temperature": 0.1,
        "use_hubspot_integration": True, # Enable HubSpot
        "hubspot_description_max_age_months": 1, # Set small term for test
        "messages": [ # Minimally required messages
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": "Provide info about {company}."}
        ]
    }
    temp_llm_config_path = Path("temp_llm_config_test.yaml")
    import yaml
    with open(temp_llm_config_path, 'w') as f:
        yaml.dump(temp_llm_config_data, f)

    adapter = HubSpotPipelineAdapter(config_path=str(temp_llm_config_path), input_file=str(temp_input_path), session_id="test_session_hubspot")
    
    # For setup we need api_keys
    adapter.api_keys = {
        "openai": os.getenv("OPENAI_API_KEY"),
        "serper": os.getenv("SERPER_API_KEY"),
        "scrapingbee": os.getenv("SCRAPINGBEE_API_KEY"),
        "hubspot": os.getenv("HUBSPOT_API_KEY") # Make sure the key exists
    }
    adapter.llm_config = temp_llm_config_data # Pass config directly for setup test

    if not adapter.api_keys["hubspot"]:
        logger.error("HUBSPOT_API_KEY not found in environment variables. Test cannot run.")
        if temp_input_path.exists(): os.remove(temp_input_path)
        if temp_llm_config_path.exists(): os.remove(temp_llm_config_path)
        return

    await adapter.setup() # Call setup to initialize hubspot_adapter

    if adapter.use_hubspot and adapter.hubspot_adapter:
        logger.info("HubSpot adapter initialized in PipelineAdapter.")
        # Can add run call, but it requires many dependencies
        # success, failure, results = await adapter.run()
        # logger.info(f"Test run completed. Success: {success}, Failure: {failure}")
        # logger.info(f"Results: {results}")
    else:
        logger.warning("HubSpot adapter was NOT initialized in PipelineAdapter. Check config and API key.")

    # Clean up temporary files
    if temp_input_path.exists():
        os.remove(temp_input_path)
    if temp_llm_config_path.exists():
        os.remove(temp_llm_config_path)

def format_hubspot_company_id(hubspot_id: Optional[str]) -> str:
    """
    Format HubSpot Company ID with link for result file.
    
    Args:
        hubspot_id: Company ID in HubSpot or None
        
    Returns:
        str: Formatted string with ID and link or empty string
    """
    if not hubspot_id:
        return ""
    
    # Load base link from environment variable
    import os
    base_url = os.getenv("HUBSPOT_BASE_URL", "https://app.hubspot.com/contacts/39585958/record/0-2/")
    
    # Make sure URL ends with /
    if not base_url.endswith("/"):
        base_url += "/"
    
    return f"{base_url}{hubspot_id}"

async def search_company_by_multiple_domains(hubspot_client, url: str, aiohttp_session=None, sb_client=None) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Search for company in HubSpot by original and final domain (after redirects).
    
    Args:
        hubspot_client: HubSpot client
        url: Original URL
        aiohttp_session: HTTP session for redirect checking
        sb_client: ScrapingBee client
        
    Returns:
        Tuple[Optional[Dict[str, Any]], str]: (Company data or None, used domain)
    """
    # Get original normalized domain
    original_domain = hubspot_client._normalize_domain(url)
    if not original_domain:
        logger.warning(f"Could not extract domain from URL '{url}'")
        return None, ""
    
    # First search by original domain
    logger.info(f"Searching in HubSpot by original domain: {original_domain}")
    company = await hubspot_client.search_company_by_domain(original_domain)
    if company:
        logger.info(f"Found company in HubSpot by original domain: {original_domain}")
        return company, original_domain
    
    # If not found by original domain, get final URL after redirects
    if aiohttp_session:
        try:
            from normalize_urls import get_url_status_and_final_location_async
            
            # Add protocol if not present for redirect checking
            url_with_protocol = url
            if not url_with_protocol.startswith(('http://', 'https://')):
                url_with_protocol = 'https://' + url_with_protocol
                
            logger.info(f"Checking redirects for URL: {url_with_protocol}")
            is_live, final_url, error_msg = await get_url_status_and_final_location_async(
                url_with_protocol, aiohttp_session, scrapingbee_client=sb_client
            )
            
            if is_live and final_url:
                final_domain = hubspot_client._normalize_domain(final_url)
                
                # Check if final domain differs from original
                if final_domain and final_domain != original_domain:
                    logger.info(f"Final domain after redirects: {final_domain} (different from original: {original_domain})")
                    
                    # Search by final domain
                    logger.info(f"Searching in HubSpot by final domain: {final_domain}")
                    company = await hubspot_client.search_company_by_domain(final_domain)
                    if company:
                        logger.info(f"Found company in HubSpot by final domain: {final_domain}")
                        return company, final_domain
                else:
                    logger.info(f"Final domain is the same as original: {original_domain}")
            else:
                logger.warning(f"Could not get final URL for {url_with_protocol}: {error_msg}")
        except Exception as e:
            logger.error(f"Error checking redirects for URL {url}: {e}")
    
    logger.info(f"Company not found in HubSpot by either original ({original_domain}) or final domain")
    return None, original_domain

if __name__ == "__main__":
    # asyncio.run(test_hubspot_adapter()) # For basic HubSpotAdapter check
    asyncio.run(test_hubspot_pipeline_adapter()) # For HubSpotPipelineAdapter check 