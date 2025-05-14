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
import yaml
import traceback
import json

# Import new components
from description_generator import DescriptionGenerator
from finders.base import Finder
from finders.llm_deep_search_finder.finder import LLMDeepSearchFinder
from finders.linkedin_finder import LinkedInFinder
from finders.homepage_finder import HomepageFinder
from src.data_io import load_and_prepare_company_names, save_results_csv, save_results_json, load_session_metadata, save_session_metadata, save_structured_data_incrementally

# Setup logging
logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 10

async def _generate_and_save_raw_markdown_report_async(
    company_name: str,
    company_findings: List[Dict[str, Any]],
    openai_client: AsyncOpenAI,
    llm_config: Dict[str, Any],
    markdown_output_path: Path
):
    """
    Форматирует сырые найденные данные в Markdown с помощью LLM и сохраняет в файл.
    """
    try:
        # Подготовка сырых данных для LLM
        raw_data_text = f"Raw data collected for company: {company_name}\\n\\n"
        for i, finding in enumerate(company_findings):
            source = finding.get("source", f"Unknown_Source_{i+1}")
            result_data = finding.get("result", "No data")
            error = finding.get("error")

            raw_data_text += f"--- Source: {source} ---\\n"
            if error:
                raw_data_text += f"Error: {error}\\n"
            elif isinstance(result_data, dict):
                raw_data_text += json.dumps(result_data, indent=2, ensure_ascii=False) + "\\n"
            else:
                raw_data_text += str(result_data) + "\\n"
            raw_data_text += "\\n"

        if not raw_data_text.strip():
            logger.warning(f"No raw data to format into Markdown for {company_name}")
            return

        # Настройки для LLM (можно вынести в llm_config.yaml при необходимости)
        model_for_markdown = llm_config.get("model_for_raw_markdown", "gpt-4o-mini")
        temperature_for_markdown = llm_config.get("temperature_for_raw_markdown", 0.1)
        max_tokens_for_markdown = llm_config.get("max_tokens_for_raw_markdown", 4000)

        system_prompt = (
            "You are an AI assistant tasked with organizing and formatting raw company data into a structured Markdown report. "
            "The goal is to make the raw data easily readable and understandable, preserving all information. "
            "Use Markdown features like headers, sub-headers, bullet points, and code blocks where appropriate. "
            "Clearly indicate the source of each piece of information. Do not summarize or omit any data. "
            "If there are errors reported from a source, include them under that source's section."
        )
        user_prompt = (
            f"Please format the following raw data for the company '{company_name}' into a structured Markdown report. "
            "Preserve all details and indicate data sources clearly.\\n\\n"
            f"Raw Data:\\n```text\\n{raw_data_text}\\n```"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        logger.info(f"Generating raw Markdown report for {company_name} using model {model_for_markdown}")
        
        response = await openai_client.chat.completions.create(
            model=model_for_markdown,
            messages=messages,
            temperature=temperature_for_markdown,
            max_tokens=max_tokens_for_markdown
        )

        if response.choices and response.choices[0].message and response.choices[0].message.content:
            markdown_content = response.choices[0].message.content.strip()
            
            # Сохранение Markdown файла
            markdown_file_path = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data.md"
            markdown_output_path.mkdir(parents=True, exist_ok=True) # Убедимся, что директория существует
            with open(markdown_file_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            logger.info(f"Saved raw Markdown report for {company_name} to {markdown_file_path}")
        else:
            logger.warning(f"LLM did not generate content for raw Markdown report for {company_name}")

    except Exception as e:
        logger.error(f"Error generating or saving raw Markdown report for {company_name}: {e}")
        logger.error(traceback.format_exc())

async def process_companies(
    company_names: List[str],
    openai_client: AsyncOpenAI,
    aiohttp_session: aiohttp.ClientSession,
    sb_client: ScrapingBeeClient,
    serper_api_key: str,
    llm_config: Dict[str, Any],
    raw_markdown_output_path: Path,
    context_text: Optional[str] = None,
    run_standard_pipeline: bool = True,
    run_llm_deep_search_pipeline: bool = True,
    broadcast_update: Optional[Callable] = None,
    output_csv_path: Optional[str] = None,
    output_json_path: Optional[str] = None,
    llm_deep_search_config_override: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    logger.info(f"Processing {len(company_names)} companies with full LLM config: {llm_config is not None}")
    
    finders = []
    if run_standard_pipeline:
        finders.append(HomepageFinder(serper_api_key, verbose=False))
        finders.append(LinkedInFinder(serper_api_key, verbose=False))
    if run_llm_deep_search_pipeline:
        finders.append(LLMDeepSearchFinder(openai_client.api_key, verbose=False))
    
    description_generator = DescriptionGenerator(openai_client.api_key, model_config=llm_config.get('description_generator_model_config'))
    
    all_results = []
    csv_fields = ["name", "homepage", "linkedin", "description", "timestamp"]
    
    for i, company_name in enumerate(company_names):
        logger.info(f"Processing company {i+1}/{len(company_names)}: {company_name}")
        if broadcast_update:
            await broadcast_update({
                "type": "progress", "company": company_name, "current": i + 1,
                "total": len(company_names), "status": "processing"
            })
        
        company_findings = []
        for finder_instance in finders:
            try:
                context = {
                    'session': aiohttp_session, 'serper_api_key': serper_api_key,
                    'openai_client': openai_client, 'sb_client': sb_client,
                    'context_text': context_text, 'user_context': context_text,
                }
                if isinstance(finder_instance, LLMDeepSearchFinder) and run_llm_deep_search_pipeline:
                    logger.info(f"Запуск LLMDeepSearchFinder для компании {company_name}")
                    current_llm_deep_search_config = llm_deep_search_config_override or llm_config.get('llm_deep_search_config', {})
                    context['specific_aspects'] = current_llm_deep_search_config.get('specific_aspects_for_report_guidance', [])
                
                finder_result_data = await finder_instance.find(company_name, **context)
                
                if isinstance(finder_result_data, dict):
                    finder_result_data['_finder_instance_type'] = finder_instance.__class__.__name__
                else:
                    finder_result_data = {
                        "source": finder_instance.__class__.__name__,
                        "result": finder_result_data,
                        "_finder_instance_type": finder_instance.__class__.__name__
                    }

                if finder_result_data.get("error"):
                    logger.warning(f"Finder {finder_instance.__class__.__name__} для компании {company_name} вернул ошибку: {finder_result_data.get('error')}")
                company_findings.append(finder_result_data)
            except Exception as e:
                logger.error(f"Error with finder {finder_instance.__class__.__name__} for company {company_name}: {e}", exc_info=True)
                company_findings.append({
                    "source": finder_instance.__class__.__name__, 
                    "result": None, 
                    "error": str(e),
                    "_finder_instance_type": finder_instance.__class__.__name__
                })
        
        if company_findings:
            await _generate_and_save_raw_markdown_report_async(
                company_name, company_findings, openai_client, llm_config, raw_markdown_output_path
            )

        structured_data = None
        description = f"No description generated for {company_name}."
        try:
            generated_result = await description_generator.generate_description(
                company_name, company_findings
            )
            if isinstance(generated_result, str) or (isinstance(generated_result, dict) and generated_result.get("error")):
                error_message = generated_result if isinstance(generated_result, str) else generated_result.get("error")
                description = f"Error generating data: {error_message}"
                logger.warning(f"Could not generate structured data for {company_name}. Reason: {error_message}")
            elif isinstance(generated_result, dict):
                description = generated_result.get("description", "No description generated.")
                structured_data = generated_result
            else:
                logger.warning(f"Unexpected result type from description_generator for {company_name}: {type(generated_result)}")
        except Exception as e:
            logger.error(f"Error generating description for {company_name}: {e}", exc_info=True)
            description = f"Error during description generation: {str(e)}"
        
        result = {
            "name": company_name,
            "homepage": "Not found",
            "linkedin": "Not found",
            "description": description,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "structured_data": structured_data
        }
        
        for finding in company_findings:
            finder_type = finding.get("_finder_instance_type", finding.get("source"))
            result_value = finding.get("result")

            if not result_value or not isinstance(result_value, str): continue
            
            if finder_type == "HomepageFinder" or finding.get("source") in ["wikidata", "domains", "wikipedia"] :
                result["homepage"] = result_value
            elif finder_type == "LinkedInFinder":
                result["linkedin"] = result_value
                
        logger.info(f"Data for CSV for {company_name} - Homepage: {result.get('homepage', 'N/A')}, LinkedIn: {result.get('linkedin', 'N/A')}")
        all_results.append(result)
        
        if output_csv_path:
            file_exists = os.path.exists(output_csv_path)
            try:
                csv_row = {key: result.get(key) for key in csv_fields}
                save_results_csv([csv_row], output_csv_path, csv_fields, append_mode=file_exists)
                logger.info(f"Saved result for {company_name} to {output_csv_path}")
            except Exception as e: logger.error(f"Error saving result for {company_name} to CSV: {e}", exc_info=True)
        
        if output_json_path and structured_data and not (isinstance(structured_data, dict) and structured_data.get("error")):
            try:
                save_structured_data_incrementally(result, output_json_path) 
                logger.info(f"Saved structured data for {company_name} to {output_json_path}")
            except Exception as e: logger.error(f"Error saving structured data for {company_name} to JSON: {e}", exc_info=True)
        
        if broadcast_update:
            await broadcast_update({
                "type": "company_completed", "company": company_name, "current": i + 1,
                "total": len(company_names), "status": "completed", 
                "result": {key: result.get(key) for key in csv_fields}
            })
    
    if output_json_path and all_results:
        results_with_structured_data = [r for r in all_results if r.get("structured_data") and not (isinstance(r.get("structured_data"), dict) and r.get("structured_data").get("error"))]
        if results_with_structured_data:
            try:
                save_results_json(results_with_structured_data, output_json_path, append_mode=False)
                logger.info(f"Saved all {len(results_with_structured_data)} structured data to {output_json_path}")
            except Exception as e: logger.error(f"Error saving all structured data to JSON: {e}", exc_info=True)
        else:
            logger.info(f"No valid structured data found in any results to save in final JSON for {output_json_path}")

    return all_results

async def run_pipeline_for_file(
    input_file_path: str | Path,
    output_csv_path: str | Path,
    pipeline_log_path: str,
    scoring_log_path: str,
    session_dir_path: Path,
    llm_config: Dict[str, Any],
    context_text: str | None,
    company_col_index: int,
    aiohttp_session: aiohttp.ClientSession,
    sb_client: ScrapingBeeClient,
    openai_client: AsyncOpenAI,
    serper_api_key: str,
    expected_csv_fieldnames: list[str],
    broadcast_update: callable = None,
    main_batch_size: int = DEFAULT_BATCH_SIZE,
    run_standard_pipeline: bool = True,
    run_llm_deep_search_pipeline: bool = True,
) -> tuple[int, int, list[dict]]:
    company_names = load_and_prepare_company_names(input_file_path, company_col_index)
    if not company_names:
        logger.error(f"No valid company names found in {input_file_path}")
        return 0, 0, []
    logger.info(f"Loaded {len(company_names)} companies from {input_file_path}")
    
    current_expected_csv_fieldnames = ["name", "homepage", "linkedin", "description", "timestamp"]
    
    structured_data_dir = session_dir_path / "structured_data"
    structured_data_dir.mkdir(exist_ok=True)
    structured_data_json_path = structured_data_dir / "company_profiles.json"
    
    raw_markdown_output_dir = session_dir_path / "raw_markdown_reports"
    raw_markdown_output_dir.mkdir(exist_ok=True)
    
    llm_deep_search_config_specific = llm_config.get('llm_deep_search_config')

    results = await process_companies(
        company_names, openai_client, aiohttp_session, sb_client, serper_api_key,
        llm_config=llm_config,
        raw_markdown_output_path=raw_markdown_output_dir,
        context_text=context_text,
        run_standard_pipeline=run_standard_pipeline,
        run_llm_deep_search_pipeline=run_llm_deep_search_pipeline,
        broadcast_update=broadcast_update,
        output_csv_path=str(output_csv_path),
        output_json_path=str(structured_data_json_path),
        llm_deep_search_config_override=llm_deep_search_config_specific
    )
    
    if results:
        try:
            csv_results = []
            for r in results:
                csv_row = {key: r.get(key) for key in current_expected_csv_fieldnames}
                csv_results.append(csv_row)
            save_results_csv(csv_results, output_csv_path, current_expected_csv_fieldnames)
            logger.info(f"Results saved to {output_csv_path}")
        except Exception as e: logger.error(f"Error saving results to CSV: {e}", exc_info=True)
    
    success_count = sum(1 for r in results if r.get("description") and not r.get("description","").startswith("Error"))
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

async def run_pipeline():
    logger.info("Starting pipeline")
    llm_config_path = "llm_config.yaml"
    try:
        with open(llm_config_path, 'r', encoding='utf-8') as f:
            llm_config = yaml.safe_load(f)
            logger.info(f"Loaded LLM config from {llm_config_path}")
    except Exception as e:
        logger.error(f"Error loading LLM config: {e}"); llm_config = {}
    
    # Ensure API keys are loaded (potentially from llm_config or environment)
    openai_api_key = llm_config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    serper_api_key = llm_config.get("serper_api_key") or os.getenv("SERPER_API_KEY")
    scrapingbee_api_key = llm_config.get("scrapingbee_api_key") or os.getenv("SCRAPINGBEE_API_KEY")

    if not openai_api_key: raise ValueError("OpenAI API key not found")
    if not serper_api_key: raise ValueError("Serper API key not found")
    if not scrapingbee_api_key: raise ValueError("ScrapingBee API key not found")

    # Обновляем llm_config ключами, если они были загружены из переменных окружения
    llm_config["openai_api_key"] = openai_api_key
    llm_config["serper_api_key"] = serper_api_key
    llm_config["scrapingbee_api_key"] = scrapingbee_api_key

    openai_client = AsyncOpenAI(api_key=openai_api_key)
    sb_client = ScrapingBeeClient(api_key=scrapingbee_api_key)
    
    input_file_path = "test_companies.csv" # Пример
    company_col_index = 0
    
    output_dir = Path("output"); output_dir.mkdir(exist_ok=True)
    sessions_dir = output_dir / "sessions"; sessions_dir.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    session_dir_path = sessions_dir / f"session_{timestamp}"; session_dir_path.mkdir(exist_ok=True)
    
    output_csv_path = session_dir_path / f"results_{timestamp}.csv" # Сохраняем CSV в папку сессии
    logs_dir = session_dir_path / "logs"; logs_dir.mkdir(exist_ok=True) # Логи тоже в папку сессии
    pipeline_log_path = logs_dir / f"pipeline_{timestamp}.log"
    scoring_log_path = logs_dir / f"scoring_{timestamp}.log"
    
    setup_session_logging(str(pipeline_log_path), str(scoring_log_path))
    
    initial_expected_csv_fieldnames = ["name", "homepage", "linkedin", "description", "timestamp"]

    async with aiohttp.ClientSession() as session:
        success_count, failure_count, results = await run_pipeline_for_file(
            input_file_path=input_file_path, output_csv_path=output_csv_path,
            pipeline_log_path=str(pipeline_log_path), scoring_log_path=str(scoring_log_path),
            session_dir_path=session_dir_path,
            llm_config=llm_config,
            context_text=None, company_col_index=company_col_index,
            aiohttp_session=session, sb_client=sb_client, openai_client=openai_client,
            serper_api_key=serper_api_key, 
            expected_csv_fieldnames=initial_expected_csv_fieldnames,
            broadcast_update=None,
        )
    
    session_metadata = {
        "session_id": timestamp, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "input_file": str(input_file_path), "output_csv": str(output_csv_path),
        "session_dir": str(session_dir_path), "companies_processed": len(results),
        "success_count": success_count, "failure_count": failure_count
    }
    all_metadata = load_session_metadata(); all_metadata.append(session_metadata)
    save_session_metadata(all_metadata)
    
    logger.info(f"Pipeline finished. Success: {success_count}, Failure: {failure_count}")
    return success_count, failure_count, results

# Пример части llm_config.yaml, которую можно добавить:
# llm_deep_search_config:
#   specific_aspects_for_report_guidance:
#     - "company founding year"
#     - "headquarters location (city and country)"
#     # ... другие аспекты ...

# description_generator_model_config:
#   model: "gpt-4o-mini" 
#   temperature: 0.2
#   # ... другие параметры для генератора описаний ...

# model_for_raw_markdown: "gpt-4o-mini"
# temperature_for_raw_markdown: 0.1
# max_tokens_for_raw_markdown: 4000 