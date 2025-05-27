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
from src.input_validators import normalize_domain
from normalize_urls import get_url_status_and_final_location_async

# Finders
from finders.base import Finder
from finders.llm_deep_search_finder.finder import LLMDeepSearchFinder
from finders.linkedin_finder import LinkedInFinder

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
    use_raw_llm_data_as_description: bool = False,
    write_to_hubspot: bool = True
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
        "HubSpot_Company_ID": "",
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
        
        # Официальный сайт должен быть предоставлен во второй колонке
        if not found_homepage_url:
            logger.warning(f"{run_stage_log} - No homepage URL provided in input data")
        
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
                    
                    # Переменная для контроля пропуска deep search
                    skip_deep_search = False
                    
                    # Передаем конфигурацию перегрузки, если она есть
                    if llm_deep_search_config_override:
                        llm_deep_search_finder.update_config(llm_deep_search_config_override)
                    
                    # Проверяем URL в HubSpot, если клиент есть и URL предоставлен
                    skip_deep_search = False
                    if found_homepage_url and hubspot_client:
                        try:
                            logger.info(f"{run_stage_log} - Checking URL {found_homepage_url} in HubSpot before deep search")
                            # Используем правильный метод из HubSpotAdapter
                            description_is_fresh, hubspot_company = await hubspot_client.check_company_description(
                                company_name, found_homepage_url, aiohttp_session, sb_client
                            )
                            
                            if description_is_fresh and hubspot_company:
                                logger.info(f"{run_stage_log} - Company with domain {found_homepage_url} found in HubSpot with fresh description")
                                description_text, timestamp, linkedin_url_from_hubspot = hubspot_client.get_company_details_from_hubspot_data(hubspot_company)
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
                                    # Используем LinkedIn из HubSpot если он есть и у нас его нет
                                    if linkedin_url_from_hubspot and not linkedin_url:
                                        linkedin_url = linkedin_url_from_hubspot
                        except Exception as e:
                            logger.error(f"{run_stage_log} - Error checking HubSpot: {e}", exc_info=True)
                    
                    # Шаг 2: Если первый шаг не пропускаем и нужно выполнить полный поиск
                    if not skip_deep_search:
                        logger.info(f"{run_stage_log} - Running full LLM deep search")
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
                            
                            # Проверяем наличие homepage в структурированных данных
                            if "homepage" in structured_data and structured_data["homepage"] and not found_homepage_url:
                                potential_url = structured_data["homepage"]
                                logger.info(f"{run_stage_log} - Found homepage in LLM deep search, validating: {potential_url}")
                                
                                # Проверяем живость URL
                                is_live, final_url = await _validate_and_get_final_url(
                                    potential_url, aiohttp_session, sb_client, company_name
                                )
                                
                                if is_live and final_url:
                                    found_homepage_url = final_url
                                    logger.info(f"{run_stage_log} - Using validated homepage from LLM deep search: {found_homepage_url}")
                                    # Обновляем URL в структурированных данных на финальный
                                    structured_data["homepage"] = final_url
                                else:
                                    logger.warning(f"{run_stage_log} - Homepage from LLM deep search is not live: {potential_url}")
                            
                            # Проверяем наличие extracted_homepage_url в результате LLMDeepSearchFinder
                            if "extracted_homepage_url" in structured_data and structured_data["extracted_homepage_url"] and not found_homepage_url:
                                potential_url = structured_data["extracted_homepage_url"]
                                logger.info(f"{run_stage_log} - Found extracted homepage URL in LLM deep search, validating: {potential_url}")
                                
                                # Проверяем живость URL
                                is_live, final_url = await _validate_and_get_final_url(
                                    potential_url, aiohttp_session, sb_client, company_name
                                )
                                
                                if is_live and final_url:
                                    found_homepage_url = final_url
                                    logger.info(f"{run_stage_log} - Using validated extracted homepage URL from LLM deep search: {found_homepage_url}")
                                    # Обновляем URL в структурированных данных на финальный
                                    structured_data["extracted_homepage_url"] = final_url
                                else:
                                    logger.warning(f"{run_stage_log} - Extracted homepage URL from LLM deep search is not live: {potential_url}")
                            
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
        
        # Финальная проверка: если URL все еще не найден, используем гарантированный метод
        if not found_homepage_url:
            logger.warning(f"{run_stage_log} - URL not found by any standard methods. Using guaranteed URL finder as last resort")
            try:
                guaranteed_url = await _guaranteed_url_finder(
                    company_name=company_name,
                    openai_client=openai_client,
                    structured_data=structured_data,
                    aiohttp_session=aiohttp_session,
                    sb_client=sb_client
                )
                if guaranteed_url:
                    found_homepage_url = guaranteed_url
                    logger.info(f"{run_stage_log} - Guaranteed URL finder found URL: {found_homepage_url}")
                    
                    # Добавляем URL в структурированные данные
                    structured_data["homepage"] = found_homepage_url
                    structured_data["extracted_homepage_url"] = found_homepage_url
                    structured_data["guaranteed_url_source"] = True
            except Exception as e:
                logger.error(f"{run_stage_log} - Error in guaranteed URL finder: {e}", exc_info=True)
                
            # Если даже гарантированный метод не нашел URL, создаем синтетический URL
            if not found_homepage_url:
                # Создаем синтетический URL на основе имени компании
                synthetic_url = _create_synthetic_url(company_name)
                found_homepage_url = synthetic_url
                logger.warning(f"{run_stage_log} - Using synthetic URL as last resort: {found_homepage_url}")
                
                # Добавляем URL в структурированные данные
                structured_data["homepage"] = found_homepage_url
                structured_data["extracted_homepage_url"] = found_homepage_url
                structured_data["synthetic_url"] = True
        
        result_data["Official_Website"] = found_homepage_url or ""
        result_data["LinkedIn_URL"] = linkedin_url or ""
        result_data["Description"] = description_text or f"Error generating description for {company_name}"
        result_data["structured_data"] = structured_data
        
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
        
        # 8. Сохранение в HubSpot, если клиент доступен и запись разрешена
        if hubspot_client and found_homepage_url and description_text and write_to_hubspot:
            try:
                logger.info(f"{run_stage_log} - Attempting to upload data to HubSpot")
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
            # Если HubSpot клиент недоступен или запись отключена, добавляем пустое поле
            if hubspot_client and not write_to_hubspot:
                logger.info(f"{run_stage_log} - HubSpot write is disabled, skipping upload")
            result_data["HubSpot_Company_ID"] = ""
        
        # logger.info(f"{run_stage_log} - Processing completed successfully") # Закомментировано
        return result_data
    
    except asyncio.CancelledError:
        logger.info(f"{run_stage_log} - Processing was cancelled")
        result_data["Description"] = f"Processing cancelled for {company_name}"
        result_data["error"] = "cancelled"
        raise  # Перебрасываем CancelledError выше
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
    already_saved_count: int = 0,  # Количество уже сохраненных результатов
    write_to_hubspot: bool = True  # Флаг записи в HubSpot
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
        write_to_hubspot: Whether to write results to HubSpot (default: True)
        
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
    
    # LinkedIn finder (единственный оставшийся стандартный finder)
    if True:  # Всегда включен
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
                    run_standard_homepage_finders=False,
                    run_domain_check_finder=run_domain_check_finder_cfg,
                    llm_deep_search_config_override=llm_deep_search_config_override,
                    broadcast_update=broadcast_update,
                    second_column_data=local_second_column_data,
                    hubspot_client=hubspot_client,
                    use_raw_llm_data_as_description=use_raw_llm_data_as_description,
                    write_to_hubspot=write_to_hubspot
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
                
                # Проверяем, что URL официального сайта нормализован
                if not error and result.get("Official_Website"):
                    normalized_url = normalize_domain(result["Official_Website"])
                    if normalized_url != result["Official_Website"]:
                        logger.info(f"Normalized URL in result: '{result['Official_Website']}' -> '{normalized_url}'")
                        result["Official_Website"] = normalized_url
                
                results.append(result)
                
                # Определяем режим сохранения: если уже есть сохраненные результаты, всегда используем append
                current_csv_append_mode = csv_append_mode or (saved_count > 0)
                current_json_append_mode = json_append_mode or (saved_count > 0)
                
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
    try:
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
    except asyncio.CancelledError:
        logger.info("Processing was cancelled, cleaning up tasks...")
        
        # Отменяем все активные задачи
        for task in processing_tasks:
            if not task.done():
                task.cancel()
        
        # Отменяем задачу сохранения
        if not saver_task.done():
            saver_task.cancel()
        
        # Ждем завершения отмены с таймаутом
        try:
            await asyncio.wait_for(
                asyncio.gather(*processing_tasks, saver_task, return_exceptions=True),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for tasks to cancel")
        
        logger.info("Processing cancellation completed")
        raise  # Перебрасываем CancelledError выше

async def _guaranteed_url_finder(
    company_name: str, 
    openai_client: AsyncOpenAI, 
    structured_data: Dict[str, Any] = {},
    aiohttp_session: Optional[aiohttp.ClientSession] = None,
    sb_client: Optional[CustomScrapingBeeClient] = None
) -> Optional[str]:
    """
    Гарантированный поиск URL компании.
    
    Эта функция обеспечивает почти 100% вероятность получения URL для компании.
    Она использует следующие методы в порядке приоритета:
    1. Извлечение URL из структурированных данных, если они уже есть
    2. Генерация URL на основе названия компании
    
    Args:
        company_name: Название компании
        openai_client: Клиент OpenAI для запросов к LLM
        structured_data: Уже собранные структурированные данные
        aiohttp_session: HTTP сессия для проверки живости URL
        sb_client: ScrapingBee клиент для проверки живости URL
        
    Returns:
        str: URL компании (всегда возвращает какой-то URL)
    """
    # Импортируем функцию нормализации URL
    from src.input_validators import normalize_domain
    
    # 1. Попытка извлечь URL из структурированных данных
    url_keys = ['website', 'official_website', 'homepage', 'url', 'official_site']
    for key in url_keys:
        if key in structured_data and structured_data[key]:
            url = structured_data[key]
            # Нормализуем URL
            normalized_url = normalize_domain(url)
            if normalized_url:
                # Добавляем протокол, если его нет
                if not normalized_url.startswith(('http://', 'https://')):
                    normalized_url = 'https://' + normalized_url
                logger.info(f"Found URL in structured data for '{company_name}': {normalized_url}")
                
                # Проверяем живость URL, если доступна HTTP сессия
                if aiohttp_session:
                    is_live, final_url = await _validate_and_get_final_url(
                        normalized_url, aiohttp_session, sb_client, company_name
                    )
                    if is_live and final_url:
                        logger.info(f"Validated URL from structured data for '{company_name}': {final_url}")
                        return final_url
                    else:
                        logger.warning(f"URL from structured data is not live for '{company_name}': {normalized_url}")
                        continue  # Пробуем следующий ключ
                else:
                    return normalized_url
    
    # 2. Попытка спросить LLM о домене компании
    if openai_client:
        try:
            logger.info(f"Asking LLM about domain for '{company_name}'")
            response = await openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that provides domain names for companies. Respond with ONLY the most likely domain name, without http:// or https:// prefixes. If you're unsure, make an educated guess based on the company name."},
                    {"role": "user", "content": f"What is the most likely domain name for the company '{company_name}'? Respond with ONLY the domain name (e.g., 'example.com'), without any explanation or other text."}
                ],
                temperature=0.1,
                max_tokens=30
            )
            
            domain = response.choices[0].message.content.strip()
            
            # Проверяем, что домен содержит точку и не содержит пробелов
            if '.' in domain and ' ' not in domain:
                # Нормализуем домен
                normalized_domain = normalize_domain(domain)
                if normalized_domain:
                    # Добавляем протокол, если его нет
                    if not normalized_domain.startswith(('http://', 'https://')):
                        normalized_domain = 'https://' + normalized_domain
                    logger.info(f"LLM suggested domain for '{company_name}': {normalized_domain}")
                    
                    # Проверяем живость URL, если доступна HTTP сессия
                    if aiohttp_session:
                        is_live, final_url = await _validate_and_get_final_url(
                            normalized_domain, aiohttp_session, sb_client, company_name
                        )
                        if is_live and final_url:
                            logger.info(f"Validated LLM suggested URL for '{company_name}': {final_url}")
                            return final_url
                        else:
                            logger.warning(f"LLM suggested URL is not live for '{company_name}': {normalized_domain}")
                    else:
                        return normalized_domain
        except Exception as e:
            logger.error(f"Error asking LLM about domain for '{company_name}': {e}")
    
    # 3. Если все методы не сработали, создаем синтетический URL
    synthetic_url = _create_synthetic_url(company_name)
    # Нормализуем синтетический URL
    normalized_synthetic = normalize_domain(synthetic_url)
    if normalized_synthetic:
        if not normalized_synthetic.startswith(('http://', 'https://')):
            normalized_synthetic = 'https://' + normalized_synthetic
        
        # Для синтетических URL проверку живости пропускаем, так как они вряд ли будут работать
        # Но возвращаем их как last resort
        logger.warning(f"Using synthetic URL for '{company_name}' (may not be live): {normalized_synthetic}")
        return normalized_synthetic
    return synthetic_url

def _validate_url_format(url: str) -> bool:
    """
    Проверяет, что строка выглядит как валидный URL.
    
    Args:
        url: Строка для проверки
        
    Returns:
        bool: True, если строка похожа на URL, иначе False
    """
    if not url:
        return False
    
    # Базовая проверка на формат URL
    url_pattern = r'https?://[\w\.-]+\.[a-zA-Z]{2,}(?:/[\w\.\-\%_]*)*'
    if re.match(url_pattern, url):
        return True
    
    # Проверка на доменное имя без протокола
    domain_pattern = r'(?:www\.)?[a-zA-Z0-9][\w\-]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2})?'
    if re.match(domain_pattern, url) and '.' in url and ' ' not in url:
        return True
    
    return False

def _create_synthetic_url(company_name: str) -> str:
    """
    Создает синтетический URL на основе имени компании.
    Используется как самый последний вариант, когда все другие методы не сработали.
    
    Args:
        company_name: Название компании
        
    Returns:
        str: Синтетический URL
    """
    # Очищаем имя компании от специальных символов и приводим к нижнему регистру
    clean_name = re.sub(r'[^\w\s]', '', company_name.lower())
    
    # Заменяем пробелы на дефисы
    domain_name = re.sub(r'\s+', '-', clean_name.strip())
    
    # Удаляем слова, которые могут быть лишними (например, "Inc", "LLC", "Ltd")
    domain_name = re.sub(r'(-inc|-llc|-ltd|-corp|-corporation|-limited)$', '', domain_name)
    
    # Создаем URL с https:// и .com
    synthetic_url = f"https://www.{domain_name}.com"
    
    logger.warning(f"Created synthetic URL for '{company_name}': {synthetic_url}")
    return synthetic_url

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
        r"(?:Official Website|Company Website|Website|Site|Homepage|Home page|Official Site|Corporate Website|URL|Web address|Web site|Official URL):\s*(?:https?:\/\/)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[-a-zA-Z0-9.]+(?:\/[-a-zA-Z0-9%_.~#?&=]*)?)",
        r"(?:https?:\/\/)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[-a-zA-Z0-9.]+(?:\/[-a-zA-Z0-9%_.~#?&=]*)?)",
        r"\[([a-zA-Z0-9][-a-zA-Z0-9]*\.[-a-zA-Z0-9.]+)\]",
        r"domain(?:\s+name)?:\s*([a-zA-Z0-9][-a-zA-Z0-9]*\.[-a-zA-Z0-9.]+)"
    ]
    
    # Если включен режим только URL, используем только базовые паттерны
    if url_only_mode:
        url_patterns = [
            r"(?:https?:\/\/)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[-a-zA-Z0-9.]+(?:\/[-a-zA-Z0-9%_.~#?&=]*)?)",
            r"\[([a-zA-Z0-9][-a-zA-Z0-9]*\.[-a-zA-Z0-9.]+)\]",
            r"([a-zA-Z0-9][-a-zA-Z0-9]*\.[-a-zA-Z0-9.]+)"
        ]
    
    for pattern in url_patterns:
        matches = re.findall(pattern, report_text, re.IGNORECASE)
        if matches:
            # Используем первый найденный URL
            url = matches[0]
            if isinstance(url, tuple):
                url = url[0]  # Извлекаем домен из группы
                
            # Нормализуем URL, извлекая только домен
            normalized_url = normalize_domain(url)
            
            if normalized_url:
                logger.info(f"Found URL via pattern matching: {url} -> normalized to {normalized_url}")
                # Если URL не содержит протокол, добавляем https://
                if not normalized_url.startswith(('http://', 'https://')):
                    normalized_url = 'https://' + normalized_url
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