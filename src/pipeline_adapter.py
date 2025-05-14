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
    output_csv_path: Optional[str] = None,  # Путь к CSV для сохранения
    output_json_path: Optional[str] = None,  # Путь к JSON для сохранения
    llm_deep_search_config: Optional[Dict[str, Any]] = None
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
        output_json_path: Path to save structured JSON data incrementally
        llm_deep_search_config: LLM deep search configuration
        
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
    csv_fields = ["name", "homepage", "linkedin", "description", "founding_year", "headquarters_location", "industry", "main_products_services", "employees_count", "timestamp"]
    
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
                # Создаем правильный контекст для финдеров
                context = {
                    'session': aiohttp_session,
                    'serper_api_key': serper_api_key,
                    'openai_client': openai_client,
                    'sb_client': sb_client,
                    'context_text': context_text,
                    'user_context': context_text,
                }
                
                # Добавляем дополнительные параметры для LLMDeepSearchFinder
                if finder.__class__.__name__ == 'LLMDeepSearchFinder' and run_llm_deep_search_pipeline:
                    logger.info(f"Запуск LLMDeepSearchFinder для компании {company_name}")
                    # Возможность использовать config если передан
                    if context.get('llm_deep_search_config'):
                        logger.info(f"Используем переданный конфиг для LLMDeepSearchFinder")
                
                finder_result = await finder.find(
                    company_name,
                    **context
                )
                
                # Если результат содержит информацию об ошибке, но не сломал выполнение, логируем ее
                if finder_result.get("error"):
                    logger.warning(f"Finder {finder.__class__.__name__} для компании {company_name} вернул ошибку: {finder_result.get('error')}")
                
                company_findings.append(finder_result)
            except Exception as e:
                error_message = f"Error with finder {finder.__class__.__name__} for company {company_name}: {e}"
                logger.error(error_message)
                logger.error(traceback.format_exc())
                company_findings.append({
                    "source": finder.__class__.__name__,
                    "result": None,
                    "error": str(e)
                })
        
        # Generate description with structured data
        try:
            generated_result = await description_generator.generate_description(
                company_name, 
                company_findings
            )
            
            # Проверяем, вернулся ли структурированный результат или строка ошибки
            if isinstance(generated_result, str):
                description = generated_result
                structured_data = None
            else:
                # Извлекаем описание и структурированные данные непосредственно из полученного результата
                description = generated_result.get("description", "No description generated.")
                # Теперь generated_result уже содержит полные структурированные данные
                structured_data = generated_result
        except Exception as e:
            logger.error(f"Error generating description for {company_name}: {e}")
            description = f"Error generating description: {str(e)}"
            structured_data = None
        
        # Prepare result
        result = {
            "name": company_name,
            "description": description,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "homepage": "Not found",
            "linkedin": "Not found"
        }
        
        # Добавляем структурированные данные, если они есть
        if structured_data:
            # Добавляем поля из структурированных данных используя полную схему
            result["founding_year"] = structured_data.get("founding_year", "Unknown")
            
            # Данные о местоположении теперь извлекаются из полных данных
            headquarters_location = structured_data.get("headquarters_location")
            if not headquarters_location and (structured_data.get("headquarters_city") or structured_data.get("headquarters_country")):
                city = structured_data.get("headquarters_city", "")
                country = structured_data.get("headquarters_country", "")
                if city and country:
                    headquarters_location = f"{city}, {country}"
                elif city:
                    headquarters_location = city
                elif country:
                    headquarters_location = country
            
            result["headquarters_location"] = headquarters_location or "Unknown"
            result["industry"] = structured_data.get("industry", "Unknown")
            result["main_products_services"] = structured_data.get("main_products_services", "Unknown")
            result["employees_count"] = structured_data.get("employees_count", "Unknown")
            
            # Сохраняем полные структурированные данные
            result["structured_data"] = structured_data
        else:
            # Если структурированных данных нет, заполняем поля значениями по умолчанию
            result["founding_year"] = "Unknown"
            result["headquarters_location"] = "Unknown"
            result["industry"] = "Unknown"
            result["main_products_services"] = "Unknown"
            result["employees_count"] = "Unknown"
            result["structured_data"] = None
        
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
        
        # Сохраняем структурированные данные в JSON
        if output_json_path:
            try:
                save_structured_data_incrementally(result, output_json_path)
                logger.info(f"Saved structured data for {company_name} to {output_json_path}")
            except Exception as e:
                logger.error(f"Error saving structured data for {company_name} to JSON: {e}")
        
        if broadcast_update:
            await broadcast_update({
                "type": "company_completed",
                "company": company_name,
                "current": i + 1,
                "total": len(company_names),
                "status": "completed",
                "result": result  # Добавляем результат в обновление
            })
    
    # После обработки всех компаний, сохраняем полный JSON файл для дополнительной безопасности
    if output_json_path and all_results:
        try:
            save_results_json(all_results, output_json_path, append_mode=False)
            logger.info(f"Saved all structured data to {output_json_path}")
        except Exception as e:
            logger.error(f"Error saving all structured data to JSON: {e}")
    
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
    
    # Обновляем expected_csv_fieldnames для добавления новых полей из структурированных данных
    if expected_csv_fieldnames and "name" in expected_csv_fieldnames:
        if "founding_year" not in expected_csv_fieldnames:
            expected_csv_fieldnames.extend(["founding_year", "headquarters_location", "industry", 
                                           "main_products_services", "employees_count"])
    
    # Создаем директорию для структурированных данных в сессии
    structured_data_dir = session_dir_path / "structured_data"
    structured_data_dir.mkdir(exist_ok=True)
    
    # Путь к JSON файлу для сохранения структурированных данных
    structured_data_json_path = structured_data_dir / "company_profiles.json"
    
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
        str(output_csv_path),  # Передаем путь к CSV для инкрементального сохранения
        str(structured_data_json_path),  # Передаем путь к JSON для сохранения структурированных данных
        llm_deep_search_config
    )
    
    # Save results to CSV
    if results:
        try:
            save_results_csv(results, output_csv_path, expected_csv_fieldnames)
            logger.info(f"Results saved to {output_csv_path}")
        except Exception as e:
            logger.error(f"Error saving results to CSV: {e}")
        
        # Дополнительно сохраняем все структурированные данные в JSON (как резервную копию)
        try:
            save_results_json(results, structured_data_json_path)
            logger.info(f"Structured data saved to {structured_data_json_path}")
        except Exception as e:
            logger.error(f"Error saving structured data to JSON: {e}")
    
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

async def run_pipeline():
    """
    Основной метод запуска пайплайна, вызываемый из main.py.
    Настраивает все необходимые компоненты и запускает обработку.
    """
    logger.info("Starting pipeline")
    
    # Путь к конфигурационному файлу LLM
    llm_config_path = "llm_config.yaml"
    
    # Загрузка конфигурации
    try:
        with open(llm_config_path, 'r', encoding='utf-8') as f:
            llm_config = yaml.safe_load(f)
            logger.info(f"Loaded LLM config from {llm_config_path}")
    except Exception as e:
        logger.error(f"Error loading LLM config: {e}")
        llm_config = {}
    
    # Загрузка API ключей
    if not llm_config.get("openai_api_key"):
        llm_config["openai_api_key"] = os.environ.get("OPENAI_API_KEY")
    
    if not llm_config.get("serper_api_key"):
        llm_config["serper_api_key"] = os.environ.get("SERPER_API_KEY")
    
    if not llm_config.get("scrapingbee_api_key"):
        llm_config["scrapingbee_api_key"] = os.environ.get("SCRAPINGBEE_API_KEY")
    
    # Проверка наличия необходимых API ключей
    if not llm_config.get("openai_api_key"):
        raise ValueError("OpenAI API key not found in config or environment variables")
    
    if not llm_config.get("serper_api_key"):
        raise ValueError("Serper API key not found in config or environment variables")
    
    if not llm_config.get("scrapingbee_api_key"):
        raise ValueError("ScrapingBee API key not found in config or environment variables")
    
    # Инициализация клиентов
    openai_client = AsyncOpenAI(api_key=llm_config["openai_api_key"])
    sb_client = ScrapingBeeClient(api_key=llm_config["scrapingbee_api_key"])
    
    # Путь к входному и выходному файлам
    input_file_path = "test_companies.csv"
    company_col_index = 0  # Индекс колонки с названиями компаний
    
    # Создаем директорию для вывода, если она не существует
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    # Создаем директорию для сессий, если она не существует
    sessions_dir = output_dir / "sessions"
    sessions_dir.mkdir(exist_ok=True)
    
    # Пути к выходным файлам
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_csv_path = output_dir / f"results_{timestamp}.csv"
    
    # Создаем директорию для текущей сессии
    session_dir_path = sessions_dir / f"session_{timestamp}"
    session_dir_path.mkdir(exist_ok=True)
    
    # Пути к логам
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    pipeline_log_path = logs_dir / f"pipeline_{timestamp}.log"
    scoring_log_path = logs_dir / f"scoring_{timestamp}.log"
    
    # Настройка логирования
    setup_session_logging(str(pipeline_log_path), str(scoring_log_path))
    
    # Запуск пайплайна
    async with aiohttp.ClientSession() as session:
        # Ожидаемые поля в CSV
        expected_csv_fieldnames = ["name", "homepage", "linkedin", "description", 
                                  "founding_year", "headquarters_location", "industry", 
                                  "main_products_services", "employees_count", "timestamp"]
        
        success_count, failure_count, results = await run_pipeline_for_file(
            input_file_path=input_file_path,
            output_csv_path=output_csv_path,
            pipeline_log_path=str(pipeline_log_path),
            scoring_log_path=str(scoring_log_path),
            session_dir_path=session_dir_path,
            context_text=None,
            company_col_index=company_col_index,
            aiohttp_session=session,
            sb_client=sb_client,
            llm_config=llm_config,
            openai_client=openai_client,
            serper_api_key=llm_config["serper_api_key"],
            expected_csv_fieldnames=expected_csv_fieldnames,
            broadcast_update=None,
            main_batch_size=DEFAULT_BATCH_SIZE,
            run_standard_pipeline=True,
            run_llm_deep_search_pipeline=True
        )
    
    # Сохраняем метаданные сессии
    session_metadata = {
        "session_id": timestamp,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "input_file": str(input_file_path),
        "output_csv": str(output_csv_path),
        "session_dir": str(session_dir_path),
        "companies_processed": len(results),
        "success_count": success_count,
        "failure_count": failure_count
    }
    
    # Загружаем существующие метаданные и добавляем новые
    all_metadata = load_session_metadata()
    all_metadata.append(session_metadata)
    save_session_metadata(all_metadata)
    
    logger.info(f"Pipeline finished. Success: {success_count}, Failure: {failure_count}")
    return success_count, failure_count, results 