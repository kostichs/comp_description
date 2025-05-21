"""
Pipeline Core Module

This module contains the core processing functions for the pipeline.
"""

import asyncio
import logging
import time
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable
import aiohttp
from openai import AsyncOpenAI
from scrapingbee import ScrapingBeeClient
import json

# Finders
from finders.base import Finder
from finders.llm_deep_search_finder.finder import LLMDeepSearchFinder
from finders.linkedin_finder import LinkedInFinder
from finders.homepage_finder.finder import HomepageFinder
from finders.domain_check_finder import DomainCheckFinder, check_url_liveness
from finders.login_detection_finder import LoginDetectionFinder

# Pipeline components
from description_generator import DescriptionGenerator
from src.data_io import save_results_csv, save_results_json, save_structured_data_incrementally
from src.pipeline.utils import generate_and_save_raw_markdown_report_async

logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 5

async def _process_single_company_async(
    company_name: str,
    openai_client: AsyncOpenAI,
    aiohttp_session: aiohttp.ClientSession,
    sb_client: ScrapingBeeClient,
    serper_api_key: str,
    finder_instances: Dict[str, Finder],
    description_generator: DescriptionGenerator,
    llm_config: Dict[str, Any],
    raw_markdown_output_path: Path,
    output_csv_path: Optional[str],
    output_json_path: Optional[str],
    csv_fields: List[str],
    company_index: int,
    total_companies: int,
    context_text: Optional[str] = None,
    run_llm_deep_search_pipeline: bool = True,
    run_standard_homepage_finders: bool = True,
    run_domain_check_finder: bool = True,
    llm_deep_search_config_override: Optional[Dict[str, Any]] = None,
    broadcast_update: Optional[Callable] = None,
    second_column_data: Optional[Dict[str, str]] = None,
    hubspot_client: Optional[Any] = None,
    use_raw_llm_data_as_description: bool = False
) -> Dict[str, Any]:
    """
    Process a single company asynchronously
    
    This function handles the entire pipeline for a single company, from
    finding the website to generating the description.
    
    Args:
        company_name: Name of the company
        openai_client: OpenAI client
        aiohttp_session: aiohttp client session
        sb_client: ScrapingBee client
        serper_api_key: Serper API key
        finder_instances: Dictionary of finder instances
        description_generator: Description generator
        llm_config: LLM configuration
        raw_markdown_output_path: Path to save raw markdown reports
        output_csv_path: Path to save CSV output
        output_json_path: Path to save JSON output
        csv_fields: CSV field names
        company_index: Index of the company in the batch
        total_companies: Total number of companies
        context_text: Optional context text
        run_llm_deep_search_pipeline: Whether to run LLM deep search
        run_standard_homepage_finders: Whether to run standard homepage finders
        run_domain_check_finder: Whether to run domain check finder
        llm_deep_search_config_override: Override for LLM deep search config
        broadcast_update: Callback for broadcasting updates
        second_column_data: Data from the second column
        hubspot_client: HubSpot client
        use_raw_llm_data_as_description: Whether to use raw LLM data as description
        
    Returns:
        Dict: The result of processing the company
    """
    # Проверяем, является ли company_name кортежем, и разделяем на имя и URL, если это так
    homepage_url_from_tuple = None
    if isinstance(company_name, tuple) and len(company_name) >= 2:
        homepage_url_from_tuple = company_name[1]
        company_name = company_name[0]
        
    result_data = {
        "Company_Name": company_name,
        "Official_Website": None,
        "LinkedIn_URL": None,
        "Description": None,
        "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "structured_data": {}
    }
    
    run_stage_log = f"[{company_index+1}/{total_companies}] {company_name}"
    logger.info(f"{run_stage_log} - Starting processing")
    
    try:
        found_homepage_url = None
        linkedin_url = None
        
        # Если URL уже предоставлен в кортеже, используем его
        if homepage_url_from_tuple:
            found_homepage_url = homepage_url_from_tuple
            logger.info(f"{run_stage_log} - Using URL from input tuple: {found_homepage_url}")
            run_standard_homepage_finders = False  # Отключаем поиск, так как URL уже есть
            run_domain_check_finder = False  # Также отключаем проверку домена
        # Если есть данные второго столбца, используем их напрямую как официальный сайт
        elif second_column_data and company_name in second_column_data:
            found_homepage_url = second_column_data[company_name]
            logger.info(f"{run_stage_log} - Using provided URL from second column: {found_homepage_url}")
            run_standard_homepage_finders = False  # Отключаем поиск, так как URL уже есть
            run_domain_check_finder = False  # Также отключаем проверку домена
        
        # Если нет данных второго столбца и включен стандартный пайплайн, ищем официальный сайт
        if run_standard_homepage_finders:
            # 1. Поиск официального сайта компании с помощью homepage_finder
            logger.info(f"{run_stage_log} - Running homepage finder")
            try:
                if "homepage_finder" in finder_instances:
                    homepage_finder = finder_instances["homepage_finder"]
                    # Передаем aiohttp_session напрямую в context
                    homepage_result = await homepage_finder.find(
                        company_name,
                        session=aiohttp_session,
                        serper_api_key=serper_api_key
                    )
                    if homepage_result and "url" in homepage_result:
                        found_homepage_url = homepage_result["url"]
                        logger.info(f"{run_stage_log} - Homepage finder found URL: {found_homepage_url}")
                    else:
                        logger.warning(f"{run_stage_log} - Homepage finder did not return a URL")
                else:
                    logger.warning(f"{run_stage_log} - Homepage finder not available")
            except Exception as e:
                logger.error(f"{run_stage_log} - Error running homepage finder: {e}", exc_info=True)
        
        # 2. Проверка доступности URL (если включена и найден URL)
        if found_homepage_url and run_domain_check_finder:
            logger.info(f"{run_stage_log} - Running domain check finder for {found_homepage_url}")
            try:
                if "domain_check_finder" in finder_instances:
                    domain_check_finder = finder_instances["domain_check_finder"]
                    domain_check_result = await domain_check_finder.find(found_homepage_url)
                    
                    if domain_check_result and domain_check_result.get("is_valid"):
                        if domain_check_result.get("redirected_url"):
                            # Если URL перенаправлен, используем новый URL
                            logger.info(f"{run_stage_log} - URL redirected to: {domain_check_result['redirected_url']}")
                            found_homepage_url = domain_check_result["redirected_url"]
                        
                        logger.info(f"{run_stage_log} - URL valid: {found_homepage_url}")
                    else:
                        logger.warning(f"{run_stage_log} - URL invalid: {found_homepage_url}")
                        if domain_check_result and "error" in domain_check_result:
                            logger.warning(f"{run_stage_log} - URL error: {domain_check_result['error']}")
                else:
                    logger.warning(f"{run_stage_log} - Domain check finder not available")
            except Exception as e:
                logger.error(f"{run_stage_log} - Error running domain check finder: {e}", exc_info=True)
        
        # 3. Поиск LinkedIn URL
        logger.info(f"{run_stage_log} - Running LinkedIn finder")
        try:
            if "linkedin_finder" in finder_instances:
                linkedin_finder = finder_instances["linkedin_finder"]
                # Исправляем передачу session и serper_api_key через context
                linkedin_result = await linkedin_finder.find(
                    company_name, 
                    session=aiohttp_session,
                    serper_api_key=serper_api_key
                )
                if linkedin_result and "result" in linkedin_result and linkedin_result["result"]:
                    linkedin_url = linkedin_result["result"]
                    logger.info(f"{run_stage_log} - LinkedIn finder found URL: {linkedin_url}")
                else:
                    logger.warning(f"{run_stage_log} - LinkedIn finder did not return a URL")
            else:
                logger.warning(f"{run_stage_log} - LinkedIn finder not available")
        except Exception as e:
            logger.error(f"{run_stage_log} - Error running LinkedIn finder: {e}", exc_info=True)
        
        # 4. Глубокий поиск информации о компании с помощью LLM
        structured_data = {}
        llm_deep_search_raw_result = None
        
        if run_llm_deep_search_pipeline:
            logger.info(f"{run_stage_log} - Running LLM deep search finder")
            try:
                if "llm_deep_search_finder" in finder_instances:
                    llm_deep_search_finder = finder_instances["llm_deep_search_finder"]
                    
                    # Передаем конфигурацию перегрузки, если она есть
                    if llm_deep_search_config_override:
                        llm_deep_search_finder.update_config(llm_deep_search_config_override)
                    
                    llm_search_result = await llm_deep_search_finder.find(
                        company_name, 
                        company_homepage_url=found_homepage_url,
                        linkedin_url=linkedin_url,
                        context_text=context_text
                    )
                    
                    if llm_search_result and isinstance(llm_search_result, dict):
                        structured_data = llm_search_result
                        # Сохраняем сырой результат для использования в качестве описания, если нужно
                        if "result" in llm_search_result:
                            llm_deep_search_raw_result = llm_search_result["result"]
                        
                        if "homepage" in structured_data and structured_data["homepage"] and not found_homepage_url:
                            found_homepage_url = structured_data["homepage"]
                            logger.info(f"{run_stage_log} - Using homepage from LLM deep search: {found_homepage_url}")
                        
                        if "linkedin" in structured_data and structured_data["linkedin"] and not linkedin_url:
                            linkedin_url = structured_data["linkedin"]
                            logger.info(f"{run_stage_log} - Using LinkedIn from LLM deep search: {linkedin_url}")
                    else:
                        logger.warning(f"{run_stage_log} - LLM deep search finder did not return valid data")
                else:
                    logger.warning(f"{run_stage_log} - LLM deep search finder not available")
            except Exception as e:
                logger.error(f"{run_stage_log} - Error running LLM deep search finder: {e}", exc_info=True)
        
        # 5. Генерация описания компании с помощью Description Generator или использование сырых данных
        description_text = None
        
        # Если указано использовать сырые данные от LLM Deep Search, пропускаем генерацию через DescriptionGenerator
        if use_raw_llm_data_as_description and llm_deep_search_raw_result:
            logger.info(f"{run_stage_log} - Using raw LLM data as description")
            description_text = llm_deep_search_raw_result
        else:
            logger.info(f"{run_stage_log} - Running description generator")
            try:
                # Собираем найденные данные для передачи в генератор описания
                company_data = {
                    "company_name": company_name,
                    "homepage_url": found_homepage_url,
                    "linkedin_url": linkedin_url,
                    "structured_data": structured_data
                }
                
                # Преобразуем найденные данные в формат, ожидаемый генератором
                findings_list = []
                
                # Добавляем homepage_url если есть
                if found_homepage_url:
                    findings_list.append({
                        "source": "homepage_finder",
                        "result": found_homepage_url
                    })
                    
                # Добавляем LinkedIn URL если есть
                if linkedin_url:
                    findings_list.append({
                        "source": "linkedin_finder",
                        "result": linkedin_url
                    })
                    
                # Добавляем structured_data от LLM Deep Search если есть
                if structured_data:
                    findings_list.append({
                        "source": "llm_deep_search",
                        "result": json.dumps(structured_data, ensure_ascii=False)
                    })
                
                # Вызываем генератор описания с правильными параметрами
                description_result = await description_generator.generate_description(
                    company_name, 
                    findings_list
                )
                
                if isinstance(description_result, dict) and "description" in description_result:
                    description_text = description_result["description"]
                    logger.info(f"{run_stage_log} - Description generated successfully ({len(description_text)} chars)")
                    
                    # Обновляем structured_data, если он есть в результате
                    for key, value in description_result.items():
                        if key != "description" and value:
                            structured_data[key] = value
                elif isinstance(description_result, str):
                    # Если вернулась строка, это, скорее всего, сообщение об ошибке
                    logger.warning(f"{run_stage_log} - Description generator returned error: {description_result}")
                    description_text = f"Error generating description for {company_name}: {description_result}"
                else:
                    logger.warning(f"{run_stage_log} - Description generator did not return valid data")
                    description_text = f"Error generating description for {company_name}"
            except Exception as e:
                logger.error(f"{run_stage_log} - Error generating description: {e}", exc_info=True)
                description_text = f"Error generating description for {company_name}: {str(e)}"
        
        # 6. Сохранение результатов в Raw Markdown формате
        if raw_markdown_output_path and structured_data:
            try:
                # Преобразуем структурированные данные в формат для markdown
                findings_for_markdown = []
                # Добавляем основной результат LLM Deep Search
                if structured_data:
                    findings_for_markdown.append({
                        "source": "llm_deep_search",
                        "result": structured_data
                    })
                
                # Генерация и сохранение Raw Markdown отчета с правильными параметрами
                report_path = await generate_and_save_raw_markdown_report_async(
                    company_name=company_name,
                    company_findings=findings_for_markdown,
                    openai_client=openai_client,
                    llm_config=llm_config,
                    markdown_output_path=raw_markdown_output_path
                )
                logger.info(f"{run_stage_log} - Raw markdown report saved to {report_path}")
            except Exception as e:
                logger.error(f"{run_stage_log} - Error saving raw markdown report: {e}", exc_info=True)
        
        # 7. Подготовка итогового результата
        result_data["Official_Website"] = found_homepage_url or ""
        result_data["LinkedIn_URL"] = linkedin_url or ""
        result_data["Description"] = description_text or f"Error generating description for {company_name}"
        result_data["structured_data"] = structured_data
        
        # Если задан output_json_path, сохраняем structured_data в JSON инкрементально
        if output_json_path and structured_data:
            try:
                # Создаем словарь с результатами для сохранения
                result_data_for_json = {
                    "name": company_name,
                    "structured_data": structured_data,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                
                # Вызываем без await, так как функция не асинхронная
                save_structured_data_incrementally(
                    result_data_for_json, 
                    output_json_path
                )
                logger.info(f"{run_stage_log} - Structured data saved to {output_json_path}")
            except Exception as e:
                logger.error(f"{run_stage_log} - Error saving structured data: {e}", exc_info=True)
        
        # 8. Сохранение в HubSpot, если клиент доступен
        if hubspot_client and structured_data:
            try:
                logger.info(f"{run_stage_log} - Attempting to upload data to HubSpot")
                hubspot_upload_result = await hubspot_client.update_company(company_name, structured_data, description_text)
                if hubspot_upload_result:
                    logger.info(f"{run_stage_log} - Data uploaded to HubSpot successfully")
                    # Добавляем информацию о загрузке в HubSpot в результаты
                    result_data.setdefault("integrations", {})["hubspot"] = {
                        "success": True, 
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                else:
                    logger.warning(f"{run_stage_log} - Failed to upload data to HubSpot")
                    result_data.setdefault("integrations", {})["hubspot"] = {
                        "success": False,
                        "error": "Failed to upload data to HubSpot",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
            except Exception as e:
                logger.error(f"{run_stage_log} - Error uploading to HubSpot: {e}", exc_info=True)
                result_data.setdefault("integrations", {})["hubspot"] = {
                    "success": False,
                    "error": str(e),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
        
        logger.info(f"{run_stage_log} - Processing completed successfully")
        return result_data
    
    except Exception as e:
        logger.error(f"{run_stage_log} - Unhandled error during processing: {e}", exc_info=True)
        result_data["Description"] = f"Error processing {company_name}: {str(e)}"
        return result_data

async def process_companies(
    company_names: List[str],
    openai_client: AsyncOpenAI,
    aiohttp_session: aiohttp.ClientSession,
    sb_client: ScrapingBeeClient,
    serper_api_key: str,
    llm_config: Dict[str, Any],
    raw_markdown_output_path: Path,
    batch_size: int, 
    context_text: Optional[str] = None,
    run_llm_deep_search_pipeline_cfg: bool = True,
    run_standard_pipeline_cfg: bool = True,
    run_domain_check_finder_cfg: bool = True,
    broadcast_update: Optional[Callable] = None,
    output_csv_path: Optional[str] = None,
    output_json_path: Optional[str] = None,
    expected_csv_fieldnames: Optional[List[str]] = None,
    llm_deep_search_config_override: Optional[Dict[str, Any]] = None,
    second_column_data: Optional[Dict[str, str]] = None,
    hubspot_client: Optional[Any] = None,
    use_raw_llm_data_as_description: bool = False
) -> List[Dict[str, Any]]:
    """
    Process multiple companies in batches
    
    Args:
        company_names: List of company names
        openai_client: OpenAI client
        aiohttp_session: aiohttp client session
        sb_client: ScrapingBee client
        serper_api_key: Serper API key
        llm_config: LLM configuration
        raw_markdown_output_path: Path to save raw markdown reports
        batch_size: Size of batches for processing
        context_text: Optional context text
        run_llm_deep_search_pipeline_cfg: Whether to run LLM deep search
        run_standard_pipeline_cfg: Whether to run standard pipeline
        run_domain_check_finder_cfg: Whether to run domain check finder
        broadcast_update: Callback for broadcasting updates
        output_csv_path: Path to save CSV output
        output_json_path: Path to save JSON output
        expected_csv_fieldnames: Expected field names for CSV output
        llm_deep_search_config_override: Override for LLM deep search config
        second_column_data: Data from the second column
        hubspot_client: HubSpot client
        use_raw_llm_data_as_description: Whether to use raw LLM data as description
        
    Returns:
        List of results from processing companies
    """
    if not company_names:
        logger.warning("No company names provided for processing")
        return []
    
    total_companies = len(company_names)
    logger.info(f"Starting processing for {total_companies} companies with batch size {batch_size}")
    
    # Создание экземпляров finder-ов
    finder_instances = {}
    
    # Настройка HomepageFinder для поиска официального сайта
    if run_standard_pipeline_cfg:
        try:
            homepage_finder = HomepageFinder(serper_api_key)
            finder_instances["homepage_finder"] = homepage_finder
            logger.info("Initialized HomepageFinder")
        except Exception as e:
            logger.error(f"Error initializing HomepageFinder: {e}", exc_info=True)
    
    # Настройка DomainCheckFinder для проверки доступности URL
    if run_domain_check_finder_cfg:
        try:
            domain_check_finder = DomainCheckFinder(sb_client, aiohttp_session)
            finder_instances["domain_check_finder"] = domain_check_finder
            logger.info("Initialized DomainCheckFinder")
        except Exception as e:
            logger.error(f"Error initializing DomainCheckFinder: {e}", exc_info=True)
    
    # Настройка LinkedInFinder для поиска LinkedIn URL
    try:
        linkedin_finder = LinkedInFinder(serper_api_key)
        finder_instances["linkedin_finder"] = linkedin_finder
        logger.info("Initialized LinkedInFinder")
    except Exception as e:
        logger.error(f"Error initializing LinkedInFinder: {e}", exc_info=True)
    
    # Настройка LLMDeepSearchFinder для глубокого поиска информации
    if run_llm_deep_search_pipeline_cfg:
        try:
            # Получаем API ключ OpenAI от клиента OpenAI
            openai_api_key = openai_client.api_key
            
            if not openai_api_key:
                logger.error("OpenAI API key not found in openai_client")
                raise ValueError("OpenAI API key is required for LLMDeepSearchFinder")
                
            llm_deep_search_finder = LLMDeepSearchFinder(
                openai_api_key=openai_api_key,
                verbose=True
            )
            finder_instances["llm_deep_search_finder"] = llm_deep_search_finder
            logger.info("Initialized LLMDeepSearchFinder")
        except Exception as e:
            logger.error(f"Error initializing LLMDeepSearchFinder: {e}", exc_info=True)
    
    # Создание DescriptionGenerator
    try:
        # Получаем API ключ OpenAI
        openai_api_key = openai_client.api_key
        if not openai_api_key:
            logger.error("OpenAI API key not found in openai_client")
            raise ValueError("OpenAI API key is required for DescriptionGenerator")
            
        description_generator = DescriptionGenerator(
            api_key=openai_api_key,
            model_config=llm_config
        )
        logger.info("Initialized DescriptionGenerator")
    except Exception as e:
        logger.error(f"Error initializing DescriptionGenerator: {e}", exc_info=True)
        description_generator = None
    
    # Подготовка ожидаемых полей CSV, если не переданы извне
    if expected_csv_fieldnames is None:
        csv_fields = ["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp"]
    else:
        csv_fields = expected_csv_fieldnames
        logger.info(f"Using provided CSV fields: {csv_fields}")
    
    # Обработка компаний по батчам для ограничения параллельных запросов
    all_results = []
    
    for batch_start in range(0, total_companies, batch_size):
        batch_end = min(batch_start + batch_size, total_companies)
        batch = company_names[batch_start:batch_end]
        logger.info(f"Processing batch {batch_start//batch_size + 1}/{(total_companies+batch_size-1)//batch_size}: {len(batch)} companies")
        
        # Параллельная обработка компаний в батче
        tasks = []
        for i, company in enumerate(batch):
            task = _process_single_company_async(
                company_name=company,
                openai_client=openai_client,
                aiohttp_session=aiohttp_session,
                sb_client=sb_client,
                serper_api_key=serper_api_key,
                finder_instances=finder_instances,
                description_generator=description_generator,
                llm_config=llm_config,
                raw_markdown_output_path=raw_markdown_output_path,
                output_csv_path=output_csv_path,
                output_json_path=output_json_path,
                csv_fields=csv_fields,
                company_index=batch_start + i,
                total_companies=total_companies,
                context_text=context_text,
                run_llm_deep_search_pipeline=run_llm_deep_search_pipeline_cfg,
                run_standard_homepage_finders=run_standard_pipeline_cfg,
                run_domain_check_finder=run_domain_check_finder_cfg,
                llm_deep_search_config_override=llm_deep_search_config_override,
                broadcast_update=broadcast_update,
                second_column_data=second_column_data,
                hubspot_client=hubspot_client,
                use_raw_llm_data_as_description=use_raw_llm_data_as_description
            )
            tasks.append(task)
        
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обработка результатов батча
        for i, result in enumerate(batch_results):
            company_name = batch[i]
            if isinstance(result, Exception):
                # Если произошло исключение во время обработки, создаем запись об ошибке
                logger.error(f"Error processing company {company_name}: {result}", exc_info=True)
                error_result = {
                    "Company_Name": company_name,
                    "Official_Website": "",
                    "LinkedIn_URL": "",
                    "Description": f"Error processing {company_name}: {str(result)}",
                    "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                all_results.append(error_result)
            else:
                # Иначе добавляем результат обработки
                all_results.append(result)
        
        # Если задан output_csv_path, сохраняем промежуточные результаты в CSV
        if output_csv_path:
            try:
                # Извлекаем только нужные поля для CSV
                csv_results = []
                for r in all_results:
                    csv_result = {key: r.get(key, "") for key in csv_fields}
                    csv_results.append(csv_result)
                
                save_results_csv(csv_results, output_csv_path, csv_fields)
                logger.info(f"Intermediate results saved to {output_csv_path}")
            except Exception as e:
                logger.error(f"Error saving intermediate results to CSV: {e}", exc_info=True)
        
        # Обновляем прогресс, если задан broadcast_update
        if broadcast_update:
            try:
                update_data = {
                    "type": "progress_update",
                    "processed": len(all_results),
                    "total": total_companies,
                    "last_processed": batch[-1] if batch else None
                }
                await broadcast_update(update_data)
                logger.debug(f"Progress update broadcasted: {len(all_results)}/{total_companies}")
            except Exception as e:
                logger.error(f"Error broadcasting progress update: {e}")
    
    logger.info(f"Finished processing {len(all_results)} companies")
    return all_results 