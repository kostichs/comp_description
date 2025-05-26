"""
Pipeline Core Module

This module contains the core processing functions for the pipeline.
"""

import asyncio
import logging
import time
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable, Union
import aiohttp
from openai import AsyncOpenAI
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient
import json
import re
from src.input_validators import normalize_domain, validate_company_name, normalize_company_name, detect_encoding_issues
from src.company_name_resolver import resolve_company_name_if_needed
from normalize_urls import get_url_status_and_final_location_async

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

# Импортируем функции валидации
# from src.input_validators import normalize_domain #, CompanyInfo

logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 5

async def _process_single_company_async(
    company_name: str,
    openai_client: AsyncOpenAI,
    aiohttp_session: aiohttp.ClientSession,
    sb_client: Optional[CustomScrapingBeeClient],
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
    run_stage_log = f"[{company_index + 1}/{total_companies}] {company_name}"
    
    # COMPANY NAME NORMALIZATION STAGE
    original_company_name = company_name
    
    # Проверяем на проблемы с кодировкой
    encoding_issues = detect_encoding_issues(company_name)
    if encoding_issues:
        logger.warning(f"{run_stage_log} - Detected encoding issues: {', '.join(encoding_issues)}")
    
    # Нормализуем название компании
    normalized_company_name = normalize_company_name(company_name, for_search=True)
    if normalized_company_name != company_name:
        logger.info(f"{run_stage_log} - Company name normalized: '{company_name}' -> '{normalized_company_name}'")
        company_name = normalized_company_name
        run_stage_log = f"[{company_index + 1}/{total_companies}] {company_name} (normalized from: {original_company_name})"
    
    # COMPANY NAME RESOLUTION STAGE (if enabled)
    resolution_metadata = {}
    
    try:
        # Try to resolve company name if needed (juridical names, founder names, etc.)
        resolved_name, resolution_metadata = await resolve_company_name_if_needed(
            company_name, openai_client
        )
        
        if resolution_metadata.get("resolution_used", False):
            logger.info(f"{run_stage_log} - Company name resolved: '{company_name}' → '{resolved_name}'")
            company_name = resolved_name
            run_stage_log = f"[{company_index + 1}/{total_companies}] {company_name} (resolved from: {original_company_name})"
        
    except Exception as e:
        logger.error(f"{run_stage_log} - Error during company name resolution: {e}")
        # Continue with original name if resolution fails
    
    # ВАЛИДАЦИЯ НАЗВАНИЯ КОМПАНИИ (after potential resolution)
    is_valid_name, validation_error = validate_company_name(company_name)
    if not is_valid_name:
        logger.warning(f"{run_stage_log} - Company name validation failed: {validation_error}")
        
        error_description = f"Invalid company name detected: {validation_error}. This entry was not processed to avoid generating incorrect data."
        
        result_data = {
            "Company_Name": original_company_name,  # Keep original name in output
            "Normalized_Company_Name": normalized_company_name if normalized_company_name != original_company_name else "",
            "Official_Website": "",
            "LinkedIn_URL": "",
            "Description": error_description,
            "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "structured_data": {},
            "validation_error": validation_error,
            "resolution_metadata": resolution_metadata,
            "encoding_issues": encoding_issues if encoding_issues else []
        }
        
        # Заполняем остальные поля пустыми значениями
        for field in csv_fields:
            if field not in result_data:
                result_data[field] = ""
        
        logger.info(f"{run_stage_log} - Skipped due to validation error: {validation_error}")
        return result_data
    
    # Проверяем, является ли company_name кортежем, и разделяем на имя и URL, если это так
    homepage_url_from_tuple = None
    if isinstance(company_name, tuple) and len(company_name) >= 2:
        homepage_url_from_tuple = company_name[1]
        company_name = company_name[0]
        
    result_data = {
        "Company_Name": original_company_name,  # Keep original name in output
        "Normalized_Company_Name": normalized_company_name if normalized_company_name != original_company_name else "",
        "Resolved_Company_Name": company_name if resolution_metadata.get("resolution_used", False) else "",
        "Official_Website": None,
        "LinkedIn_URL": None,
        "Description": None,
        "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "HubSpot_Company_ID": "",
        "structured_data": {},
        "resolution_metadata": resolution_metadata,
        "encoding_issues": encoding_issues if encoding_issues else []
    }
    
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
        
        # 2. ЭТАП 1: Поиск URL через Homepage Finder (приоритетный метод)
        google_search_data = None
        if not found_homepage_url and run_standard_homepage_finders:
            logger.info(f"{run_stage_log} - STAGE 1: URL Discovery using Homepage Finder")
            try:
                if "homepage_finder" in finder_instances:
                    homepage_finder = finder_instances["homepage_finder"]
                    homepage_result = await homepage_finder.find(
                        company_name,
                        session=aiohttp_session,
                        serper_api_key=serper_api_key
                    )
                    
                    # Сохраняем данные поиска Google для последующего анализа
                    if homepage_result and "google_search_data" in homepage_result:
                        google_search_data = homepage_result["google_search_data"]
                        logger.info(f"{run_stage_log} - Saved Google search data with {len(google_search_data.get('top_5_results', []))} results")
                    
                    if homepage_result and "result" in homepage_result and homepage_result["result"]:
                        found_homepage_url = homepage_result["result"]
                        logger.info(f"{run_stage_log} - ✅ STAGE 1 SUCCESS: Homepage Finder found URL: {found_homepage_url}")
                    else:
                        logger.warning(f"{run_stage_log} - ❌ STAGE 1 FAILED: Homepage Finder did not return a URL")
                else:
                    logger.warning(f"{run_stage_log} - Homepage finder not available")
            except Exception as e:
                logger.error(f"{run_stage_log} - Error in Homepage Finder stage: {e}", exc_info=True)
        
        # 2.1. ЭТАП 1B: Поиск URL через LLM Deep Search (для сравнения с Homepage Finder)
        llm_deep_search_url = None
        if run_llm_deep_search_pipeline:
            logger.info(f"{run_stage_log} - STAGE 1B: URL Discovery using LLM Deep Search for comparison")
            try:
                if "llm_deep_search_finder" in finder_instances:
                    llm_deep_search_finder = finder_instances["llm_deep_search_finder"]
                    
                    # Передаем конфигурацию перегрузки, если она есть
                    if llm_deep_search_config_override:
                        llm_deep_search_finder.update_config(llm_deep_search_config_override)
                    
                    logger.info(f"{run_stage_log} - Running URL-only search to find company website")
                    url_only_result = await llm_deep_search_finder.find(
                        company_name,
                        url_only_mode=True
                    )
                    
                    if url_only_result and isinstance(url_only_result, dict) and url_only_result.get("extracted_homepage_url"):
                        potential_url = url_only_result["extracted_homepage_url"]
                        logger.info(f"{run_stage_log} - LLM URL discovery found potential URL: {potential_url}")
                        
                        # Проверяем живость URL
                        is_live, final_url = await _validate_and_get_final_url(
                            potential_url, aiohttp_session, sb_client, company_name
                        )
                        
                        if is_live and final_url:
                            llm_deep_search_url = final_url
                            logger.info(f"{run_stage_log} - ✅ STAGE 1B SUCCESS: Found and validated URL: {llm_deep_search_url}")
                        else:
                            logger.warning(f"{run_stage_log} - ❌ STAGE 1B FAILED: URL not live: {potential_url}")
                    else:
                        logger.warning(f"{run_stage_log} - ❌ STAGE 1B FAILED: No URL found in discovery mode")
                else:
                    logger.warning(f"{run_stage_log} - LLM deep search finder not available for URL discovery")
            except Exception as e:
                logger.error(f"{run_stage_log} - Error in LLM URL discovery stage: {e}", exc_info=True)
        
        # 2.2. СРАВНЕНИЕ И ВЫБОР ЛУЧШЕГО URL (если есть результаты от обоих источников)
        if found_homepage_url or llm_deep_search_url:
            logger.info(f"{run_stage_log} - STAGE 1.5: Comparing and selecting best URL")
            try:
                selected_url, url_source = await _compare_and_select_best_url(
                    company_name=company_name,
                    homepage_finder_url=found_homepage_url,
                    google_search_data=google_search_data,
                    llm_deep_search_url=llm_deep_search_url,
                    openai_client=openai_client,
                    run_stage_log=run_stage_log
                )
                
                if selected_url:
                    found_homepage_url = selected_url
                    logger.info(f"{run_stage_log} - ✅ STAGE 1.5 SUCCESS: Selected URL from {url_source}: {found_homepage_url}")
                else:
                    logger.warning(f"{run_stage_log} - ❌ STAGE 1.5 FAILED: No URL selected")
                    
            except Exception as e:
                logger.error(f"{run_stage_log} - Error in URL comparison stage: {e}", exc_info=True)
                # В случае ошибки используем Homepage Finder URL если есть
                if found_homepage_url:
                    logger.info(f"{run_stage_log} - Using Homepage Finder URL due to comparison error: {found_homepage_url}")
                elif llm_deep_search_url:
                    found_homepage_url = llm_deep_search_url
                    logger.info(f"{run_stage_log} - Using LLM Deep Search URL due to comparison error: {found_homepage_url}")
        
        # 3. ЭТАП 2: Полный анализ компании (когда есть URL)
        structured_data = {}
        llm_deep_search_raw_result = None
        
        if found_homepage_url and run_llm_deep_search_pipeline:
            logger.info(f"{run_stage_log} - STAGE 2: Full Company Analysis with URL: {found_homepage_url}")
            try:
                if "llm_deep_search_finder" in finder_instances:
                    llm_deep_search_finder = finder_instances["llm_deep_search_finder"]
                    
                    # Переменная для контроля пропуска deep search
                    skip_deep_search = False
                    
                    # Проверяем URL в HubSpot, если клиент есть
                    if hubspot_client:
                        try:
                            logger.info(f"{run_stage_log} - Checking URL {found_homepage_url} in HubSpot before analysis")
                            hubspot_company = await hubspot_client.search_company_by_domain(found_homepage_url)
                            
                            if hubspot_company and hubspot_client.has_fresh_description(hubspot_company):
                                logger.info(f"{run_stage_log} - Company with domain {found_homepage_url} found in HubSpot with fresh description")
                                properties = hubspot_company.get("properties", {})
                                description_text = properties.get("ai_description", "")
                                if description_text:
                                    logger.info(f"{run_stage_log} - Using existing description from HubSpot")
                                    skip_deep_search = True
                                    # Добавляем базовую информацию для использования в других местах
                                    structured_data = {
                                        "homepage": found_homepage_url,
                                        "extracted_homepage_url": found_homepage_url,
                                        "hubspot_id": hubspot_company.get("id"),
                                        "hubspot_source": True
                                    }
                                    llm_deep_search_raw_result = description_text
                        except Exception as e:
                            logger.error(f"{run_stage_log} - Error checking HubSpot: {e}", exc_info=True)
                    
                    # Выполняем полный LLM Deep Search с найденным URL
                    if not skip_deep_search:
                        logger.info(f"{run_stage_log} - Running full company analysis with validated URL")
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
                            
                            # Обновляем URL в структурированных данных, если он изменился
                            if "homepage" in structured_data:
                                structured_data["homepage"] = found_homepage_url
                            if "extracted_homepage_url" in structured_data:
                                structured_data["extracted_homepage_url"] = found_homepage_url
                            
                            if "linkedin" in structured_data and structured_data["linkedin"] and not linkedin_url:
                                linkedin_url = structured_data["linkedin"]
                                logger.info(f"{run_stage_log} - Found LinkedIn URL in analysis: {linkedin_url}")
                            
                            logger.info(f"{run_stage_log} - ✅ STAGE 2 SUCCESS: Full analysis completed")
                        else:
                            logger.warning(f"{run_stage_log} - ❌ STAGE 2 FAILED: LLM analysis did not return valid data")
                else:
                    logger.warning(f"{run_stage_log} - LLM deep search finder not available for analysis")
            except Exception as e:
                logger.error(f"{run_stage_log} - Error in company analysis stage: {e}", exc_info=True)
        
        # 4. Дополнительные методы поиска URL (если все предыдущие не сработали)
        # Homepage Finder уже запущен на этапе 1, поэтому здесь больше нет дополнительных методов
        
        # 5. Проверка доступности URL (если включена и найден URL)
        if found_homepage_url and run_domain_check_finder:
            logger.info(f"{run_stage_log} - Checking URL liveness for {found_homepage_url}")
            try:
                # Импортируем функцию проверки URL
                from finders.domain_check_finder import check_url_liveness
                
                # Проверяем доступность URL
                is_live = await check_url_liveness(found_homepage_url, aiohttp_session, timeout=5.0)
                
                if is_live:
                    logger.info(f"{run_stage_log} - URL is live: {found_homepage_url}")
                else:
                    logger.warning(f"{run_stage_log} - URL is not accessible: {found_homepage_url}")
                    # Можно попробовать нормализовать URL или использовать альтернативные варианты
                    
            except Exception as e:
                logger.error(f"{run_stage_log} - Error checking URL liveness: {e}", exc_info=True)
        
        # 6. Поиск LinkedIn URL (запасной метод, если LLM Deep Search не нашел)
        if not linkedin_url:
            logger.info(f"{run_stage_log} - Running LinkedIn finder as backup")
            try:
                if "linkedin_finder" in finder_instances:
                    linkedin_finder = finder_instances["linkedin_finder"]
                    linkedin_result = await linkedin_finder.find(
                        company_name, 
                        session=aiohttp_session,
                        serper_api_key=serper_api_key
                    )
                    if linkedin_result and "result" in linkedin_result and linkedin_result["result"]:
                        linkedin_url = linkedin_result["result"]
                        logger.info(f"{run_stage_log} - Backup LinkedIn finder found URL: {linkedin_url}")
                    else:
                        logger.warning(f"{run_stage_log} - Backup LinkedIn finder did not return a URL")
                else:
                    logger.warning(f"{run_stage_log} - LinkedIn finder not available")
            except Exception as e:
                logger.error(f"{run_stage_log} - Error running backup LinkedIn finder: {e}", exc_info=True)
        
        # 7. Генерация описания компании с помощью Description Generator или использование сырых данных
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
        
        # 8. Сохранение результатов в Raw Markdown формате
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
        
        # 9. Извлечение официального сайта из LLM данных
        llm_extracted_url = None
        if structured_data and use_raw_llm_data_as_description:
            # Пытаемся извлечь URL из структурированных данных LLM
            try:
                # Ищем в различных полях структурированных данных
                possible_url_fields = [
                    'official_homepage_url', 'homepage', 'website', 'official_website', 
                    'company_website', 'site', 'url', 'web_address', 'official_site'
                ]
                
                for field in possible_url_fields:
                    if field in structured_data and structured_data[field]:
                        potential_url = structured_data[field]
                        if isinstance(potential_url, str) and potential_url.strip():
                            # Нормализуем URL
                            from src.input_validators import normalize_domain
                            normalized_url = normalize_domain(potential_url)
                            if normalized_url:
                                llm_extracted_url = normalized_url
                                if not llm_extracted_url.startswith(('http://', 'https://')):
                                    llm_extracted_url = 'https://' + llm_extracted_url
                                logger.info(f"{run_stage_log} - Extracted URL from LLM data field '{field}': {llm_extracted_url}")
                                break
                
                # Если не нашли в структурированных полях, пытаемся извлечь из текста описания
                if not llm_extracted_url and llm_deep_search_raw_result:
                    extracted_from_text = await _extract_homepage_from_report_text_async(
                        llm_deep_search_raw_result, company_name, url_only_mode=False
                    )
                    if extracted_from_text:
                        llm_extracted_url = extracted_from_text
                        logger.info(f"{run_stage_log} - Extracted URL from LLM text: {llm_extracted_url}")
                        
            except Exception as e:
                logger.error(f"{run_stage_log} - Error extracting URL from LLM data: {e}")
        
        # 10. Подготовка итогового результата
        
        # Приоритет для финального URL:
        # 1. URL извлеченный из LLM данных (если используем сырые данные LLM)
        # 2. URL найденный через поисковые методы (found_homepage_url)
        final_url = None
        if use_raw_llm_data_as_description and llm_extracted_url:
            final_url = llm_extracted_url
            logger.info(f"{run_stage_log} - Using LLM extracted URL as final result: {final_url}")
        elif found_homepage_url:
            final_url = found_homepage_url
            logger.info(f"{run_stage_log} - Using search found URL as final result: {final_url}")
        
        if not final_url:
            logger.warning(f"{run_stage_log} - No valid URL found for company")
        
        result_data["Official_Website"] = final_url or ""
        result_data["LinkedIn_URL"] = linkedin_url or ""
        result_data["Description"] = description_text or f"Error generating description for {company_name}"
        result_data["structured_data"] = structured_data
        
        # Добавляем данные поиска Google для анализа
        if google_search_data:
            result_data["google_search_data"] = google_search_data
        
        # Если задан output_csv_path, сохраняем результат текущей компании в CSV
        # ---- НАЧАЛО БЛОКА ДЛЯ КОММЕНТИРОВАНИЯ ----
        # if output_csv_path:
        #     try:
        #         # Создаем список с одним результатом для текущей компании
        #         current_result = {key: result_data.get(key, "") for key in csv_fields}
        #         
        #         # Используем portalocker для блокировки файла на Windows
        #         import csv
        #         from contextlib import contextmanager
        #         
        #         @contextmanager
        #         def locked_file(filename, mode):
        #             """Контекстный менеджер для безопасной работы с файлами."""
        #             try:
        #                 # Открываем файл эксклюзивно
        #                 import os
        #                 import time  # Добавляем импорт модуля time
        #                 # Использование опции 'b' для бинарного режима, чтобы избежать проблем с переводами строк
        #                 file_handle = open(filename, mode + 'b', buffering=0)
        #                 try:
        #                     # Пытаемся получить эксклюзивную блокировку
        #                     if os.name == 'nt':  # Windows
        #                         import msvcrt
        #                         msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        #                     else:  # Unix/Linux
        #                         import fcntl
        #                         fcntl.flock(file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        #                 except (IOError, OSError):
        #                     # Не можем получить блокировку, закрываем файл и пробуем снова
        #                     file_handle.close()
        #                     time.sleep(0.1)
        #                     file_handle = open(filename, mode + 'b', buffering=0)
        #                     if os.name == 'nt':
        #                         msvcrt.locking(file_handle.fileno(), msvcrt.LK_LOCK, 1)
        #                     else:
        #                         fcntl.flock(file_handle, fcntl.LOCK_EX)
        #                 
        #                 # Создаем текстовый wrapper для бинарного файла
        #                 import io
        #                 text_file = io.TextIOWrapper(file_handle, encoding='utf-8')
        #                 yield text_file
        #             finally:
        #                 try:
        #                     # Снимаем блокировку и закрываем файл
        #                     text_file.detach()  # Отсоединяем TextIOWrapper, чтобы не закрыть основной файл дважды
        #                     if os.name == 'nt':
        #                         file_handle.seek(0)
        #                         try:
        #                             msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        #                         except:
        #                             pass  # Игнорируем ошибки при разблокировке
        #                     file_handle.close()
        #                 except:
        #                     pass  # Игнорируем ошибки при закрытии
        #         
        #         # Добавляем запись в CSV файл, используя нашу функцию блокировки
        #         try:
        #             with locked_file(output_csv_path, 'a') as f:
        #                 writer = csv.DictWriter(f, fieldnames=csv_fields)
        #                 writer.writerow(current_result)
        #             # logger.info(f"{run_stage_log} - Result saved to {output_csv_path}") # Закомментировано
        #         except Exception as e:
        #             # Запасной план: просто добавляем строку в файл без блокировки
        #             try:
        #                 with open(output_csv_path, 'a', encoding='utf-8', newline='') as f:
        #                     writer = csv.DictWriter(f, fieldnames=csv_fields)
        #                     writer.writerow(current_result)
        #                 # logger.info(f"{run_stage_log} - Result saved to {output_csv_path} (without locking)") # Закомментировано
        #             except Exception as inner_e:
        #                 logger.error(f"{run_stage_log} - Error saving result to CSV (fallback): {inner_e}", exc_info=True)
        #                 raise inner_e
        #     except Exception as e:
        #         logger.error(f"{run_stage_log} - Error saving result to CSV: {e}", exc_info=True)
        # ---- КОНЕЦ БЛОКА ДЛЯ КОММЕНТИРОВАНИЯ ----
        
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
        
        # 10. Проверка качества данных перед сохранением в HubSpot
        def is_valid_for_hubspot(description: str, homepage_url: str, company_name: str) -> Tuple[bool, str]:
            """Проверяет качество данных перед сохранением в HubSpot"""
            
            # Проверка 1: Есть ли описание
            if not description or description.strip() == "":
                return False, "No description generated"
            
            # Проверка 2: Описание не является сообщением об ошибке
            error_indicators = [
                "Error generating description",
                "Недостаточно данных для генерации описания",
                "Error processing",
                "could not locate any specific",
                "After an extensive search, I could not locate",
                "It is possible that the company operates under a different name",
                "does not correspond to a known business entity",
                "appears to be ambiguous",
                "no publicly available information",
                "has not disclosed any",
                "absence of information suggests",
                "information cannot be established",
                "significant gap in understanding",
                "no information provided about",
                "lack of foundational details",
                "business operations and market positioning remain unclear",
                "comprehensive overview cannot be established",
                "no financial details",
                "no information available",
                "cannot be determined",
                "information is not available"
            ]
            
            for error_indicator in error_indicators:
                if error_indicator.lower() in description.lower():
                    return False, f"Description contains error indicator: {error_indicator}"
            
            # Проверка 3: Описание не слишком короткое (менее 100 символов для более строгой проверки)
            if len(description.strip()) < 100:
                return False, "Description too short (less than 100 characters)"
            
            # Проверка 4: Описание содержит достаточно конкретной информации
            # Проверяем наличие конкретных деталей о компании
            concrete_info_indicators = [
                "founded in", "established in", "headquarters in", "based in",
                "specializes in", "provides", "offers", "develops", "creates",
                "revenue", "employees", "clients", "customers", "products",
                "services", "technology", "platform", "software", "solutions"
            ]
            
            concrete_info_count = sum(1 for indicator in concrete_info_indicators 
                                    if indicator.lower() in description.lower())
            
            if concrete_info_count < 2:
                return False, f"Description lacks concrete information (found {concrete_info_count} indicators, need at least 2)"
            
            # Проверка 5: Есть ли валидный URL
            if not homepage_url or homepage_url.strip() == "":
                return False, "No homepage URL found"
            
            # Проверка 6: URL не является поисковиком или общим сайтом
            invalid_domains = [
                "google.com", "bing.com", "yahoo.com", "duckduckgo.com",
                "wikipedia.org", "linkedin.com", "facebook.com", "twitter.com"
            ]
            
            for invalid_domain in invalid_domains:
                if invalid_domain in homepage_url.lower():
                    return False, f"Homepage URL is invalid domain: {invalid_domain}"
            
            # Проверка 6.1: URL не является синтетическим (созданным системой)
            if "dcsg-tech-co.com" in homepage_url.lower() or any(word in homepage_url.lower() for word in ["synthetic", "generated", "placeholder"]):
                return False, "Homepage URL appears to be synthetic/generated"
            
            # Проверка 7: Описание содержит название компании или похожие слова
            company_words = company_name.lower().replace('"', '').split()
            description_lower = description.lower()
            
            # Убираем общие слова
            common_words = {"inc", "llc", "ltd", "corp", "corporation", "company", "co", "gmbh", "kg", "oo", "ooo", "tech", "l.l.c"}
            meaningful_words = [word for word in company_words if word not in common_words and len(word) > 2]
            
            if meaningful_words:
                # Проверяем, есть ли хотя бы одно значимое слово из названия компании в описании
                found_words = [word for word in meaningful_words if word in description_lower]
                if not found_words:
                    return False, f"Description doesn't contain company name words: {meaningful_words}"
            
            return True, "Valid for HubSpot"
        
        # Сохранение в HubSpot только если данные прошли проверку качества
        if hubspot_client:
            is_valid, validation_message = is_valid_for_hubspot(description_text, found_homepage_url, company_name)
            
            if is_valid and found_homepage_url and description_text:
                try:
                    logger.info(f"{run_stage_log} - Data passed quality checks, attempting to upload to HubSpot")
                    # Используем правильный метод save_company_description который возвращает (success, company_id)
                    hubspot_success, hubspot_company_id = await hubspot_client.save_company_description(
                        company_data=None,  # Пусть метод сам найдет компанию по URL
                        company_name=company_name,
                        url=found_homepage_url,
                        description=description_text,
                        linkedin_url=linkedin_url,
                        aiohttp_session=aiohttp_session,  # Добавляем HTTP сессию
                        sb_client=sb_client  # Добавляем ScrapingBee клиент
                    )
                    
                    if hubspot_success:
                        logger.info(f"{run_stage_log} - Data uploaded to HubSpot successfully")
                        # Добавляем информацию о загрузке в HubSpot в результаты
                        result_data.setdefault("integrations", {})["hubspot"] = {
                            "success": True, 
                            "company_id": hubspot_company_id,
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        # Добавляем HubSpot Company ID в основные результаты
                        from src.integrations.hubspot.adapter import format_hubspot_company_id
                        result_data["HubSpot_Company_ID"] = format_hubspot_company_id(hubspot_company_id)
                    else:
                        logger.warning(f"{run_stage_log} - Failed to upload data to HubSpot")
                        result_data.setdefault("integrations", {})["hubspot"] = {
                            "success": False,
                            "error": "Failed to upload data to HubSpot",
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        result_data["HubSpot_Company_ID"] = ""
                except Exception as e:
                    logger.error(f"{run_stage_log} - Error uploading to HubSpot: {e}", exc_info=True)
                    result_data.setdefault("integrations", {})["hubspot"] = {
                        "success": False,
                        "error": str(e),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    result_data["HubSpot_Company_ID"] = ""
            else:
                # Данные не прошли проверку качества
                logger.warning(f"{run_stage_log} - Data failed quality check, skipping HubSpot upload: {validation_message}")
                result_data.setdefault("integrations", {})["hubspot"] = {
                    "success": False,
                    "error": f"Quality check failed: {validation_message}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                result_data["HubSpot_Company_ID"] = ""
        else:
            # Если HubSpot клиент недоступен, добавляем пустое поле
            result_data["HubSpot_Company_ID"] = ""
        
        # logger.info(f"{run_stage_log} - Processing completed successfully") # Закомментировано
        return result_data
    
    except Exception as e:
        logger.error(f"{run_stage_log} - Unhandled error during processing: {e}", exc_info=True)
        result_data["Description"] = f"Error processing {company_name}: {str(e)}"
        return result_data

async def process_companies(
    company_names: List[Union[str, Tuple[str, str]]],
    openai_client: AsyncOpenAI,
    aiohttp_session: aiohttp.ClientSession,
    sb_client: Optional[CustomScrapingBeeClient],
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
    use_raw_llm_data_as_description: bool = False,
    csv_append_mode: bool = False,
    json_append_mode: bool = False,
    already_saved_count: int = 0  # Количество уже сохраненных результатов
) -> List[Dict[str, Any]]:
    """
    Process multiple companies in parallel batches
    
    Args:
        company_names: List of company names
        openai_client: OpenAI client
        aiohttp_session: aiohttp client session
        sb_client: ScrapingBee client
        serper_api_key: Serper API key
        llm_config: LLM configuration
        raw_markdown_output_path: Path to save raw markdown reports
        batch_size: Number of companies to process in parallel
        context_text: Optional context text
        run_llm_deep_search_pipeline_cfg: Whether to run LLM deep search
        run_standard_pipeline_cfg: Whether to run standard homepage finders
        run_domain_check_finder_cfg: Whether to run domain check finder
        broadcast_update: Callback for broadcasting updates
        output_csv_path: Path to save CSV output
        output_json_path: Path to save JSON output
        expected_csv_fieldnames: Expected CSV field names
        llm_deep_search_config_override: Override for LLM deep search config
        second_column_data: Data from the second column (company_name -> url mapping)
        hubspot_client: HubSpot client (optional)
        use_raw_llm_data_as_description: Whether to use raw LLM data as description
        csv_append_mode: Whether to append to CSV file instead of overwriting
        json_append_mode: Whether to append to JSON file instead of overwriting
        already_saved_count: Number of already saved results
        
    Returns:
        List[Dict[str, Any]]: List of results
    """
    # Убедимся, что директория для markdown отчетов существует
    if raw_markdown_output_path:
        os.makedirs(raw_markdown_output_path, exist_ok=True)
    
    # Если есть данные из второй колонки, нормализуем их URLs
    if second_column_data:
        normalized_second_column_data = {}
        for company_name, url in second_column_data.items():
            if url and url.lower() not in ['nan', '']:
                normalized_url = normalize_domain(url)
                normalized_second_column_data[company_name] = normalized_url
                if normalized_url != url:
                    logger.info(f"Normalized URL for '{company_name}': '{url}' -> '{normalized_url}'")
        second_column_data = normalized_second_column_data
    
    # Создаем экземпляры finder'ов для поиска информации
    finder_instances = {}
    
    # Стандартные finders
    if run_standard_pipeline_cfg:
        # HomepageFinder для поиска официального сайта
        finder_instances["homepage_finder"] = HomepageFinder(
            serper_api_key=serper_api_key,
            openai_api_key=openai_client.api_key if openai_client else None
        )
        
        # LinkedInFinder для поиска LinkedIn URL
        finder_instances["linkedin_finder"] = LinkedInFinder(
            serper_api_key=serper_api_key,
            openai_api_key=openai_client.api_key if openai_client else None
        )
    
    # DomainCheckFinder для проверки URL
    if run_domain_check_finder_cfg:
        finder_instances["domain_check_finder"] = DomainCheckFinder()
        
    # LoginDetectionFinder для определения наличия форм логина
    finder_instances["login_detection_finder"] = LoginDetectionFinder(sb_client)
    
    # LLMDeepSearchFinder для глубокого поиска информации
    if run_llm_deep_search_pipeline_cfg:
        # Инициализация LLMDeepSearchFinder
        config_override = llm_deep_search_config_override or {}
        # Получаем openai_api_key из openai_client, если он есть
        current_openai_api_key = openai_client.api_key if openai_client else None
        
        if not current_openai_api_key:
            logger.error("OpenAI API key is not available for LLMDeepSearchFinder. Skipping this finder.")
            finder_instances["llm_deep_search_finder"] = None # или можно не добавлять его вообще
        else:
            llm_deep_search_finder = LLMDeepSearchFinder(
                openai_api_key=current_openai_api_key,
                # scrapingbee_client и serper_api_key не принимаются конструктором LLMDeepSearchFinder
                # Они, вероятно, используются внутри его метода find или передаются через context
                **config_override
            )
            finder_instances["llm_deep_search_finder"] = llm_deep_search_finder
    
    # Создаем экземпляр DescriptionGenerator для генерации описаний
    description_generator = DescriptionGenerator(openai_client)
    
    # Процессинг компаний динамической очередью с семафором
    results = []
    total_companies = len(company_names)
    
    # Создаем семафор для ограничения количества одновременно обрабатываемых компаний
    semaphore = asyncio.Semaphore(batch_size)
    
    # Создаем очередь для управления порядком сохранения результатов
    result_queue = asyncio.Queue()
    company_counter = {"value": 0}  # Счетчик завершенных компаний
    
    async def process_company_with_semaphore(company_input_item, company_index):
        """Обрабатывает одну компанию с использованием семафора"""
        async with semaphore:  # Семафор ограничивает количество одновременных задач
            # Получаем имя компании и второй столбец, если они предоставлены как кортеж или словарь
            local_second_column_data = second_column_data.copy() if second_column_data else {}
            
            if isinstance(company_input_item, dict):
                company_name = company_input_item.get('name')
                company_url = company_input_item.get('url')
                
                # Если URL есть, нормализуем его и добавляем во второй столбец данных
                if company_url:
                    local_second_column_data[company_name] = company_url
            elif isinstance(company_input_item, tuple):
                company_name = company_input_item[0]
                if len(company_input_item) > 1:
                    company_url = company_input_item[1]
                    if company_url:
                        local_second_column_data[company_name] = company_url
            else:
                company_name = company_input_item
            
            try:
                logger.info(f"[{company_index+1}/{total_companies}] Starting processing company: {company_name}")
                
                # Обрабатываем компанию
                result = await _process_single_company_async(
                    company_name=company_name,
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
                    csv_fields=expected_csv_fieldnames or [],
                    company_index=company_index,
                    total_companies=total_companies,
                    context_text=context_text,
                    run_llm_deep_search_pipeline=run_llm_deep_search_pipeline_cfg,
                    run_standard_homepage_finders=run_standard_pipeline_cfg,
                    run_domain_check_finder=run_domain_check_finder_cfg,
                    llm_deep_search_config_override=llm_deep_search_config_override,
                    broadcast_update=broadcast_update,
                    second_column_data=local_second_column_data,
                    hubspot_client=hubspot_client,
                    use_raw_llm_data_as_description=use_raw_llm_data_as_description
                )
                
                logger.info(f"[{company_index+1}/{total_companies}] Successfully processed company: {company_name}")
                
                # Помещаем результат в очередь для сохранения
                await result_queue.put((company_index, result, None))
                
            except Exception as e:
                logger.error(f"[{company_index+1}/{total_companies}] Error processing company {company_name}: {e}", exc_info=True)
                error_result = {
                    "Company_Name": company_name,
                    "Official_Website": None,
                    "LinkedIn_URL": None,
                    "Description": None,
                    "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "HubSpot_Company_ID": "",
                    "error": str(e),
                    "structured_data": {}
                }
                # Помещаем ошибку в очередь для сохранения
                await result_queue.put((company_index, error_result, e))
    
    async def result_saver():
        """Сохраняет результаты по мере их готовности"""
        saved_count = already_saved_count  # Начинаем с уже сохраненных результатов
        logger.info(f"Result saver started, waiting for {total_companies} companies, already saved: {already_saved_count}")
        
        while saved_count < total_companies + already_saved_count:
            try:
                company_index, result, error = await result_queue.get()
                logger.info(f"Received result for company index {company_index}, saved_count: {saved_count}")
                
                # URL уже правильно нормализован в процессе обработки, дополнительная нормализация не нужна
                
                results.append(result)
                
                # Определяем режим сохранения: первая компания создает файл, остальные добавляются
                current_csv_append_mode = csv_append_mode or (saved_count > already_saved_count)
                current_json_append_mode = json_append_mode or (saved_count > already_saved_count)
                
                # Сохраняем результат сразу же
                try:
                    if output_csv_path:
                        save_results_csv(
                            results=[result], 
                            output_path=output_csv_path, 
                            expected_fields=expected_csv_fieldnames,
                            append_mode=current_csv_append_mode
                        )
                        logger.info(f"Saved result to CSV for company: {result.get('Company_Name', 'Unknown')}")
                    
                    if output_json_path:
                        save_results_json(
                            results=[result], 
                            output_path=output_json_path,
                            append_mode=current_json_append_mode
                        )
                        logger.info(f"Saved result to JSON for company: {result.get('Company_Name', 'Unknown')}")
                        
                except Exception as save_error:
                    logger.error(f"Error saving result for company {result.get('Company_Name', 'Unknown')}: {save_error}", exc_info=True)
                
                saved_count += 1
                company_counter["value"] = saved_count - already_saved_count  # Показываем прогресс только для текущей обработки
                logger.info(f"Progress: {saved_count - already_saved_count}/{total_companies} companies processed, total saved: {saved_count}")
                
            except Exception as queue_error:
                logger.error(f"Error in result_saver while processing queue: {queue_error}", exc_info=True)
                break
                
        logger.info(f"Result saver finished, saved {saved_count - already_saved_count} new companies, total: {saved_count}")
    
    # Запускаем задачи для всех компаний
    processing_tasks = []
    logger.info(f"Creating {total_companies} processing tasks with semaphore limit {batch_size}")
    
    for i, company_input_item in enumerate(company_names):
        task = asyncio.create_task(process_company_with_semaphore(company_input_item, i))
        processing_tasks.append(task)
    
    logger.info(f"Created {len(processing_tasks)} processing tasks")
    
    # Запускаем сохранитель результатов
    saver_task = asyncio.create_task(result_saver())
    logger.info("Started result saver task")
    
    # Ждем завершения всех задач обработки
    logger.info("Waiting for all processing tasks to complete...")
    processing_results = await asyncio.gather(*processing_tasks, return_exceptions=True)
    
    # Проверяем результаты обработки
    exceptions_count = sum(1 for result in processing_results if isinstance(result, Exception))
    if exceptions_count > 0:
        logger.warning(f"Processing completed with {exceptions_count} task exceptions")
    else:
        logger.info("All processing tasks completed successfully")
    
    # Ждем завершения сохранения всех результатов
    logger.info("Waiting for result saver to complete...")
    await saver_task
    logger.info("Result saver completed")
            
    return results

async def _extract_homepage_from_report_text_async(report_text: str, company_name: str, url_only_mode: bool = False) -> Optional[str]:
    """
    Извлекает URL официального сайта компании из текста отчета LLM.
    
    Args:
        report_text: Текст отчета от LLM
        company_name: Название компании
        url_only_mode: Режим только для извлечения URL (пропускает парсинг JSON)
        
    Returns:
        str: URL официального сайта или None, если не найден
    """
    if not report_text:
        return None
    
    # Импортируем функцию нормализации URL
    from src.input_validators import normalize_domain
    
    # Первый подход: поиск ключевых паттернов в тексте
    logger.info(f"Extracting homepage URL for {company_name} from report text (mode: {'url_only' if url_only_mode else 'standard'})")
    
    # Начинаем с более агрессивных методов поиска URL в тексте
    # Приоритетные паттерны URL
    url_patterns = [
        # Markdown ссылки: [text](https://example.com)
        r"\[.*?\]\((https?://[^\)]+)\)",
        # Markdown ссылки без протокола: [text](example.com)
        r"\[.*?\]\(([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z0-9\.\-/]+)\)",
        # Официальные поля с URL
        r"(?:Official\s+Homepage\s+URL|Official\s+Website|Company\s+Website|Website|Site|Homepage|Home\s+page|Official\s+Site|Corporate\s+Website|URL|Web\s+address|Web\s+site|Official\s+URL):\s*\*?\*?\s*(?:\[.*?\]\()?(https?://[^\s\)]+)",
        # Официальные поля без протокола
        r"(?:Official\s+Homepage\s+URL|Official\s+Website|Company\s+Website|Website|Site|Homepage|Home\s+page|Official\s+Site|Corporate\s+Website|URL|Web\s+address|Web\s+site|Official\s+URL):\s*\*?\*?\s*(?:\[.*?\]\()?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z0-9\.\-/]+)",
        # Простые URL с протоколом
        r"(https?://[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z0-9\.\-/]+)",
        # Простые домены
        r"([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2})?(?:/[a-zA-Z0-9\.\-/]*)?)"
    ]
    
    # Если включен режим только URL, используем только базовые паттерны
    if url_only_mode:
        url_patterns = [
            # Markdown ссылки: [text](https://example.com)
            r"\[.*?\]\((https?://[^\)]+)\)",
            # Markdown ссылки без протокола: [text](example.com)
            r"\[.*?\]\(([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z0-9\.\-/]+)\)",
            # Простые URL с протоколом
            r"(https?://[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z0-9\.\-/]+)",
            # Простые домены
            r"([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2})?(?:/[a-zA-Z0-9\.\-/]*)?)"
        ]
    
    for pattern in url_patterns:
        matches = re.findall(pattern, report_text, re.IGNORECASE)
        if matches:
            # Используем первый найденный URL
            url = matches[0]
            if isinstance(url, tuple):
                url = url[0]  # Извлекаем домен из группы
            
            # Очищаем URL от лишних символов
            url = url.strip().rstrip(')')
            
            # Если URL уже содержит протокол, используем его как есть
            if url.startswith(('http://', 'https://')):
                logger.info(f"Found complete URL via pattern matching: {url}")
                return url
            else:
                # Нормализуем URL, извлекая только домен
                normalized_url = normalize_domain(url)
                
                if normalized_url:
                    # Если URL не содержит протокол, добавляем https://
                    if not normalized_url.startswith(('http://', 'https://')):
                        normalized_url = 'https://' + normalized_url
                    logger.info(f"Found URL via pattern matching: {url} -> normalized to {normalized_url}")
                    return normalized_url
    
    # Если в режиме URL-only и ничего не нашли через паттерны, возвращаем None
    if url_only_mode:
        return None
    
    # Если не удалось найти URL по паттернам, ищем в структурированных данных JSON
    # Предполагаем, что в отчете может быть JSON-структура с ключами для сайта
    json_start = report_text.find('{')
    json_end = report_text.rfind('}')
    
    if json_start != -1 and json_end != -1 and json_start < json_end:
        try:
            json_str = report_text[json_start:json_end+1]
            data = json.loads(json_str)
            
            # Проверяем разные ключи, которые могут содержать URL
            possible_keys = [
                'website', 'official_website', 'homepage', 'company_website', 
                'official_site', 'site', 'url', 'web_address', 'web_site'
            ]
            
            for key in possible_keys:
                if key in data and data[key]:
                    url = data[key]
                    
                    # Нормализуем URL, извлекая только домен
                    normalized_url = normalize_domain(url)
                    
                    if normalized_url:
                        logger.info(f"Found URL in JSON data: {url} -> normalized to {normalized_url}")
                        # Если URL не содержит протокол, добавляем https://
                        if not normalized_url.startswith(('http://', 'https://')):
                            normalized_url = 'https://' + normalized_url
                        return normalized_url
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from report text for {company_name}")
    
    logger.warning(f"No homepage URL found for {company_name} in report text")
    return None 

async def _compare_and_select_best_url(
    company_name: str,
    homepage_finder_url: Optional[str],
    google_search_data: Optional[dict],
    llm_deep_search_url: Optional[str],
    openai_client: AsyncOpenAI,
    run_stage_log: str
) -> Tuple[Optional[str], str]:
    """
    Сравнивает результаты Homepage Finder и LLM Deep Search для выбора лучшего URL.
    
    Args:
        company_name: Название компании
        homepage_finder_url: URL найденный Homepage Finder
        google_search_data: Данные поиска Google (первые 5 результатов)
        llm_deep_search_url: URL найденный LLM Deep Search
        openai_client: OpenAI клиент
        run_stage_log: Префикс для логирования
        
    Returns:
        Tuple[Optional[str], str]: (выбранный_url, источник)
    """
    # Если есть только один источник, используем его
    if homepage_finder_url and not llm_deep_search_url:
        logger.info(f"{run_stage_log} - Using Homepage Finder URL (only source): {homepage_finder_url}")
        return homepage_finder_url, "homepage_finder"
    
    if llm_deep_search_url and not homepage_finder_url:
        logger.info(f"{run_stage_log} - Using LLM Deep Search URL (only source): {llm_deep_search_url}")
        return llm_deep_search_url, "llm_deep_search"
    
    if not homepage_finder_url and not llm_deep_search_url:
        logger.warning(f"{run_stage_log} - No URLs found from either source")
        return None, "none"
    
    # Если оба источника дали одинаковые URL, используем Homepage Finder (приоритет)
    if homepage_finder_url == llm_deep_search_url:
        logger.info(f"{run_stage_log} - Both sources found same URL: {homepage_finder_url}")
        return homepage_finder_url, "both_same"
    
    # Если URL разные, используем LLM для сравнения
    logger.info(f"{run_stage_log} - Comparing different URLs: HF={homepage_finder_url} vs LLM={llm_deep_search_url}")
    
    try:
        # Подготавливаем данные для сравнения
        google_results_text = ""
        if google_search_data and google_search_data.get("top_5_results"):
            google_results_text = "\n".join([
                f"{i}. {result['title']}\n   URL: {result['url']}\n   Snippet: {result['snippet']}"
                for i, result in enumerate(google_search_data["top_5_results"], 1)
            ])
        
        comparison_prompt = f"""
Analyze these two URLs found for company "{company_name}" and determine which is more likely to be the correct official website:

URL 1 (Homepage Finder): {homepage_finder_url}
URL 2 (LLM Deep Search): {llm_deep_search_url}

Google Search Results Context:
{google_results_text}

Consider:
1. Which URL appears in the Google search results?
2. Which URL seems more official/corporate?
3. Which URL better matches the company name?
4. Domain authority and legitimacy

Respond with ONLY one of these options:
- "URL1" if Homepage Finder URL is better
- "URL2" if LLM Deep Search URL is better
- "UNCLEAR" if cannot determine
"""

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert at evaluating website URLs for companies. Be concise and decisive."},
                {"role": "user", "content": comparison_prompt}
            ],
            max_tokens=10,
            temperature=0
        )
        
        decision = response.choices[0].message.content.strip().upper()
        
        if decision == "URL1":
            logger.info(f"{run_stage_log} - LLM chose Homepage Finder URL: {homepage_finder_url}")
            return homepage_finder_url, "llm_chose_homepage_finder"
        elif decision == "URL2":
            logger.info(f"{run_stage_log} - LLM chose LLM Deep Search URL: {llm_deep_search_url}")
            return llm_deep_search_url, "llm_chose_deep_search"
        else:
            # По умолчанию отдаем приоритет Homepage Finder
            logger.info(f"{run_stage_log} - LLM unclear, defaulting to Homepage Finder: {homepage_finder_url}")
            return homepage_finder_url, "llm_unclear_default_homepage_finder"
            
    except Exception as e:
        logger.error(f"{run_stage_log} - Error in URL comparison: {e}")
        # В случае ошибки отдаем приоритет Homepage Finder
        logger.info(f"{run_stage_log} - Error in comparison, defaulting to Homepage Finder: {homepage_finder_url}")
        return homepage_finder_url, "error_default_homepage_finder"

async def _validate_and_get_final_url(
    url: str,
    aiohttp_session: aiohttp.ClientSession,
    sb_client: Optional[CustomScrapingBeeClient] = None,
    company_name: str = "Unknown"
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет живость URL и возвращает финальный URL после редиректов.
    
    Args:
        url: URL для проверки
        aiohttp_session: HTTP сессия для запросов
        sb_client: ScrapingBee клиент (опционально)
        company_name: Имя компании для логирования
        
    Returns:
        Tuple[bool, Optional[str]]: (is_live, final_url)
    """
    if not url:
        return False, None
        
    try:
        logger.info(f"Validating URL for {company_name}: {url}")
        is_live, final_url, error_msg = await get_url_status_and_final_location_async(
            url, aiohttp_session, timeout=10.0, scrapingbee_client=sb_client
        )
        
        if is_live and final_url:
            if final_url != url:
                logger.info(f"URL redirected for {company_name}: {url} -> {final_url}")
            else:
                logger.info(f"URL validated for {company_name}: {url}")
            return True, final_url
        else:
            logger.warning(f"URL validation failed for {company_name}: {url} - {error_msg}")
            return False, None
            
    except Exception as e:
        logger.error(f"Error validating URL for {company_name}: {url} - {e}")
        return False, None 