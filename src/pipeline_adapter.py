"""
Pipeline Adapter Module for Web Interface Integration

This adapter bridges the gap between the new refactored pipeline and the existing backend.
It provides the same API that the backend expects while using the new implementation under the hood.
"""

import asyncio
import aiohttp
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable
from openai import AsyncOpenAI
from scrapingbee import ScrapingBeeClient
import time  # Добавляем для timestamp

# Import new components
from description_generator import DescriptionGenerator
from finders.base import Finder
from finders.llm_deep_search_finder.finder import LLMDeepSearchFinder
from finders.linkedin_finder import LinkedInFinder
from finders.homepage_finder import HomepageFinder
from src.data_io import load_and_prepare_company_names, save_results_csv

# Setup logging
logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 10

async def process_companies(
    company_names: List[str],
    openai_client: AsyncOpenAI,
    aiohttp_session: aiohttp.ClientSession,
    sb_client: ScrapingBeeClient,
    serper_api_key: str,
    context_text: Optional[str] = None,
    run_standard_pipeline: bool = True,
    run_llm_deep_search_pipeline: bool = True,
    broadcast_update: Optional[Callable] = None,
    output_csv_path: Optional[str] = None  # Добавляем путь к CSV для сохранения
) -> List[Dict[str, Any]]:
    """
    Process a list of companies using the new pipeline components.
    
    Args:
        company_names: List of company names to process
        openai_client: Initialized AsyncOpenAI client
        aiohttp_session: Initialized aiohttp session
        sb_client: Initialized ScrapingBeeClient
        serper_api_key: Serper API key for search
        context_text: Optional context for processing
        run_standard_pipeline: Whether to run standard URL finding
        run_llm_deep_search_pipeline: Whether to run LLM deep search
        broadcast_update: Optional callback to broadcast updates
        output_csv_path: Path to save results CSV incrementally
        
    Returns:
        List of company processing results
    """
    logger.info(f"Processing {len(company_names)} companies")
    
    # Initialize finders
    finders = []
    
    if run_standard_pipeline:
        # Add standard finders
        finders.append(HomepageFinder(serper_api_key, verbose=False))
        finders.append(LinkedInFinder(serper_api_key, verbose=False))
    
    if run_llm_deep_search_pipeline:
        # Add LLM deep search finder
        finders.append(LLMDeepSearchFinder(openai_client.api_key, verbose=False))
    
    # Initialize description generator
    description_generator = DescriptionGenerator(openai_client.api_key)
    
    # Process companies
    all_results = []
    
    # Определяем поля CSV для сохранения результатов
    csv_fields = ["name", "homepage", "linkedin", "description", "timestamp"]
    
    for i, company_name in enumerate(company_names):
        logger.info(f"Processing company {i+1}/{len(company_names)}: {company_name}")
        
        if broadcast_update:
            await broadcast_update({
                "type": "progress",
                "company": company_name,
                "current": i + 1,
                "total": len(company_names),
                "status": "processing"
            })
        
        # Process with finders
        company_findings = []
        
        for finder in finders:
            try:
                # Создаем правильный контекст для фидеров
                context = {
                    'session': aiohttp_session,
                    'serper_api_key': serper_api_key,
                    'openai_client': openai_client,
                    'sb_client': sb_client,
                    'context_text': context_text,
                    'user_context': context_text,
                }
                
                finder_result = await finder.find(
                    company_name,
                    **context
                )
                company_findings.append(finder_result)
            except Exception as e:
                logger.error(f"Error with finder {finder.__class__.__name__} for company {company_name}: {e}")
                company_findings.append({
                    "source": finder.__class__.__name__,
                    "result": None,
                    "error": str(e)
                })
        
        # Generate description
        try:
            description = await description_generator.generate_description(
                company_name, 
                company_findings
            )
        except Exception as e:
            logger.error(f"Error generating description for {company_name}: {e}")
            description = f"Error generating description: {str(e)}"
        
        # Prepare result
        result = {
            "name": company_name,
            "description": description,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "homepage": "Not found",
            "linkedin": "Not found"
        }
        
        # Extract URLs from findings
        for finding in company_findings:
            source = finding.get("source", "")
            finder_class = finding.get("source_class", "")
            result_value = finding.get("result")
            
            # Проверяем, что результат есть
            if not result_value:
                continue
                
            # Если это результат от HomepageFinder или его подисточников
            if finder_class == "HomepageFinder" or source in ["wikidata", "domains", "wikipedia", "wikidata_via_wiki", 
                                               "wikipedia_page", "wikipedia_first", "wikipedia_page_first"]:
                result["homepage"] = result_value
                
            # Если это результат от LinkedInFinder
            elif finder_class == "LinkedInFinder" or source == "linkedin_finder":
                result["linkedin"] = result_value
                
        # Логируем результаты для отладки
        logger.info(f"Found for {company_name} - Homepage: {result['homepage']}, LinkedIn: {result['linkedin']}")
        
        all_results.append(result)
        
        # Сохраняем результат сразу в CSV
        if output_csv_path:
            # Создаем файл с заголовками, если он не существует
            file_exists = os.path.exists(output_csv_path)
            try:
                save_results_csv([result], output_csv_path, csv_fields, append_mode=file_exists)
                logger.info(f"Saved result for {company_name} to {output_csv_path}")
            except Exception as e:
                logger.error(f"Error saving result for {company_name} to CSV: {e}")
        
        if broadcast_update:
            await broadcast_update({
                "type": "company_completed",
                "company": company_name,
                "current": i + 1,
                "total": len(company_names),
                "status": "completed",
                "result": result  # Добавляем результат в обновление
            })
    
    return all_results

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
    main_batch_size: int = DEFAULT_BATCH_SIZE,
    run_standard_pipeline: bool = True,
    run_llm_deep_search_pipeline: bool = True,
    llm_deep_search_config: Optional[Dict[str, Any]] = None
) -> tuple[int, int, list[dict]]:
    """
    Run the pipeline for an input file, adapting new code to the old interface.
    
    Args:
        input_file_path: Path to the input file
        output_csv_path: Path to save the output CSV
        pipeline_log_path: Path to save pipeline logs
        scoring_log_path: Path to save scoring logs
        session_dir_path: Path to the session directory
        context_text: Optional context text
        company_col_index: Index of the company name column
        aiohttp_session: Initialized aiohttp session
        sb_client: Initialized ScrapingBeeClient
        llm_config: LLM configuration
        openai_client: Initialized AsyncOpenAI client
        serper_api_key: Serper API key
        expected_csv_fieldnames: Expected CSV field names
        broadcast_update: Optional callback to broadcast updates
        main_batch_size: Batch size for processing
        run_standard_pipeline: Whether to run standard pipeline
        run_llm_deep_search_pipeline: Whether to run LLM deep search pipeline
        llm_deep_search_config: LLM deep search configuration
        
    Returns:
        Tuple of (success count, failure count, results)
    """
    # Load company names
    company_names = load_and_prepare_company_names(input_file_path, company_col_index)
    
    if not company_names:
        logger.error(f"No valid company names found in {input_file_path}")
        return 0, 0, []
    
    logger.info(f"Loaded {len(company_names)} companies from {input_file_path}")
    
    # Process companies
    results = await process_companies(
        company_names,
        openai_client,
        aiohttp_session,
        sb_client,
        serper_api_key,
        context_text,
        run_standard_pipeline,
        run_llm_deep_search_pipeline,
        broadcast_update,
        str(output_csv_path)  # Передаем путь к CSV для инкрементального сохранения
    )
    
    # Save results to CSV
    if results:
        try:
            save_results_csv(results, output_csv_path, expected_csv_fieldnames)
            logger.info(f"Results saved to {output_csv_path}")
        except Exception as e:
            logger.error(f"Error saving results to CSV: {e}")
    
    # Count successes and failures
    success_count = sum(1 for r in results if r.get("description") and not r.get("description").startswith("Error"))
    failure_count = len(results) - success_count
    
    return success_count, failure_count, results

def setup_session_logging(pipeline_log_path: str, scoring_log_path: str):
    """
    Setup logging for a session.
    
    Args:
        pipeline_log_path: Path to save pipeline logs
        scoring_log_path: Path to save scoring logs
    """
    # Make sure the directory exists
    os.makedirs(os.path.dirname(pipeline_log_path), exist_ok=True)
    
    # Setup file handlers
    pipeline_handler = logging.FileHandler(pipeline_log_path, mode='w', encoding='utf-8')
    pipeline_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
    
    scoring_handler = logging.FileHandler(scoring_log_path, mode='w', encoding='utf-8')
    scoring_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # Add handlers to loggers
    logger.addHandler(pipeline_handler)
    
    # Create a specific logger for scoring
    scoring_logger = logging.getLogger('ScoringLogger')
    scoring_logger.setLevel(logging.DEBUG)
    scoring_logger.propagate = False
    scoring_logger.addHandler(scoring_handler)
    
    logger.info("Session logging setup complete") 