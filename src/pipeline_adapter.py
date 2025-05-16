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
import ssl # <--- НОВЫЙ ИМПОРТ
import urllib.parse
import re

# Import new components
from description_generator import DescriptionGenerator
from finders.base import Finder
from finders.llm_deep_search_finder.finder import LLMDeepSearchFinder
from finders.linkedin_finder import LinkedInFinder
from finders.homepage_finder.finder import HomepageFinder
from finders.domain_check_finder import DomainCheckFinder, check_url_liveness
from src.data_io import load_and_prepare_company_names, save_results_csv, save_results_json, load_session_metadata, save_session_metadata, save_structured_data_incrementally

# Setup logging
logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 5

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
        raw_data_parts = [f"# Raw Data Report for {company_name}\n"]
        for i, finding in enumerate(company_findings):
            source_name = finding.get("source", f"Unknown_Source_{i+1}")
            finder_type = finding.get("_finder_instance_type", source_name) 
            report_text_data = finding.get("result")
            error_data = finding.get("error")
            sources_list = finding.get("sources") 
            raw_data_parts.append(f"\n## Source: {source_name} (Type: {finder_type})\n")
            if error_data: raw_data_parts.append(f"**Error:**\n```\n{error_data}\n```\n")
            if report_text_data:
                raw_data_parts.append(f"**Report/Result Data:**\n")
                if isinstance(report_text_data, dict):
                    raw_data_parts.append(f"```json\n{json.dumps(report_text_data, indent=2, ensure_ascii=False)}\n```\n")
                else: raw_data_parts.append(f"```text\n{str(report_text_data)}\n```\n")
            if sources_list and isinstance(sources_list, list):
                raw_data_parts.append(f"**Extracted Sources from this source:**\n")
                for src_item in sources_list:
                    title = src_item.get('title', 'N/A'); url = src_item.get('url', 'N/A')
                    raw_data_parts.append(f"- [{title}]({url})\n")
            if not error_data and not report_text_data and not (sources_list and isinstance(sources_list, list)):
                 raw_data_parts.append("_No specific data, error, or sources reported by this finder._\n")
        raw_data_for_llm_prompt = "".join(raw_data_parts)
        if not raw_data_for_llm_prompt.strip() or len(raw_data_for_llm_prompt) < 50:
            logger.warning(f"No substantial raw data to format for {company_name}. Saving raw dump.")
            md_path = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data_dump.md"
            markdown_output_path.mkdir(parents=True, exist_ok=True); 
            with open(md_path, "w", encoding="utf-8") as f: f.write(raw_data_for_llm_prompt)
            logger.info(f"Saved raw dump for {company_name} to {md_path}"); return
        model_config = llm_config.get("raw_markdown_formatter_config", {})
        model = model_config.get("model", "gpt-4o-mini")
        temp = model_config.get("temperature", 0.1)
        max_tokens = model_config.get("max_tokens", 4000)
        system_prompt = (
            "You are an AI assistant. Your task is to take a collection of raw data entries for a company, each from a different named source, "
            "and format this information into a single, coherent, well-structured Markdown report. "
            "Preserve all information, including report texts, lists of URLs/sources, and any reported errors. "
            "Use Markdown headings for each original source. If a source provided a list of URLs (sources), list them clearly under that source's section. "
            "Do not summarize, omit, or interpret the data, simply reformat it for readability."
        )
        user_prompt = (
            f"Please format the following raw data collection for the company '{company_name}' into a single, structured Markdown report. "
            "Make sure all details, including any explicitly listed URLs/sources from each original data block, are preserved and clearly presented under their respective original source headings.\n\n"
            f"Raw Data Collection:\n```markdown\n{raw_data_for_llm_prompt}\n```"
        )
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        logger.info(f"Generating formatted Markdown for {company_name} using {model}. Input length: {len(raw_data_for_llm_prompt)}")
        try:
            response = await openai_client.chat.completions.create(model=model, messages=messages, temperature=temp, max_tokens=max_tokens)
            if response.choices and response.choices[0].message and response.choices[0].message.content:
                md_content = response.choices[0].message.content.strip()
                md_path = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data_formatted.md"
                markdown_output_path.mkdir(parents=True, exist_ok=True); 
                with open(md_path, "w", encoding="utf-8") as f: f.write(md_content)
                logger.info(f"Saved formatted Markdown for {company_name} to {md_path}")
            else:
                logger.warning(f"LLM did not generate content for Markdown report for {company_name}. Saving unformatted dump.")
                md_path_dump = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data_unformatted_llm_empty.md"
                with open(md_path_dump, "w", encoding="utf-8") as f: f.write(raw_data_for_llm_prompt)
                logger.info(f"Saved unformatted dump to {md_path_dump}")
        except Exception as e_llm:
            logger.error(f"Error during LLM formatting for {company_name}: {e_llm}. Saving unformatted dump.", exc_info=True)
            md_path_error = markdown_output_path / f"{company_name.replace(' ', '_').replace('/', '_')}_raw_data_unformatted_llm_error.md"
            with open(md_path_error, "w", encoding="utf-8") as f: f.write(raw_data_for_llm_prompt)
            logger.info(f"Saved unformatted dump due to LLM error to {md_path_error}")
    except Exception as e:
        logger.error(f"General error in _generate_and_save_raw_markdown_report_async for {company_name}: {e}", exc_info=True)

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
    broadcast_update: Optional[Callable] = None
) -> Dict[str, Any]:
    
    logger.info(f"Starting processing for company {company_index + 1}/{total_companies}: {company_name}")
    
    company_findings = []
    # Переменные для итогового homepage и его источника
    final_homepage_url: Optional[str] = None
    final_homepage_source: Optional[str] = None
    linkedin_url_result: Optional[str] = None # Для LinkedIn URL

    # --- Этап 1: LLM Deep Search (если включен) ---
    if broadcast_update: await broadcast_update({"type": "progress", "company": company_name, "current": company_index + 1, "total": total_companies, "status": "processing_llm_deep_search"})
    llm_deep_search_finder = finder_instances.get('LLMDeepSearchFinder')
    if run_llm_deep_search_pipeline and llm_deep_search_finder:
        try:
            context = {
                'session': aiohttp_session, 'serper_api_key': serper_api_key,
                'openai_client': openai_client, 'sb_client': sb_client,
                'context_text': context_text, 'user_context': context_text,
            }
            current_llm_deep_search_config = llm_deep_search_config_override or llm_config.get('llm_deep_search_config', {})
            context['specific_aspects'] = current_llm_deep_search_config.get('specific_aspects_for_report_guidance', [])
            
            logger.debug(f"Calling LLMDeepSearchFinder for {company_name}")
            finding = await llm_deep_search_finder.find(company_name, **context)
            company_findings.append(finding)
            
            # Детальное логирование всего содержимого finding
            logger.info(f"LLMDeepSearchFinder result keys: {list(finding.keys())}")
            for key, value in finding.items():
                if key == "result" and value:
                    logger.info(f"LLMDeepSearch result text length: {len(value)} chars")
                elif key == "sources" and value:
                    logger.info(f"LLMDeepSearch sources: {len(value)} sources found")
                    for i, source in enumerate(value[:2]):
                        logger.info(f"  Source {i+1}: {source.get('title', 'No Title')} - {source.get('url', 'No URL')}")
                    if len(value) > 2:
                        logger.info(f"  ... and {len(value)-2} more sources")
                elif key == "extracted_homepage_url":
                    logger.info(f"LLMDeepSearch extracted_homepage_url: '{value}'")
                elif key not in ["result", "sources"] or not value:
                    logger.info(f"LLMDeepSearch {key}: {value}")
            
            if not finding.get("error") and finding.get("extracted_homepage_url"):
                candidate_url = finding["extracted_homepage_url"]
                # Нормализация URL - удаление завершающего слеша
                if candidate_url.endswith('/'):
                    candidate_url = candidate_url.rstrip('/')
                    logger.info(f"Normalized URL by removing trailing slash: {candidate_url}")
                
                logger.info(f"LLMDeepSearchFinder found homepage candidate for {company_name}: {candidate_url}")
                # Принимаем URL без проверки живости
                final_homepage_url = candidate_url
                final_homepage_source = "llm_deep_search_extracted"
                logger.info(f"Homepage from LLMDeepSearch for {company_name} ({final_homepage_url}) принят без проверки живости.")
            elif finding.get("error"):
                 logger.warning(f"LLMDeepSearchFinder for {company_name} returned error: {finding.get('error')}")
            else:
                logger.info(f"LLMDeepSearchFinder for {company_name} did not find/extract a homepage URL.")
        except Exception as e:
            logger.error(f"Exception in LLMDeepSearchFinder for {company_name}: {e}", exc_info=True)
            company_findings.append({"source": "llm_deep_search", "result": None, "error": str(e), "_finder_instance_type": "LLMDeepSearchFinder"})
    logger.info(f"After LLMDeepSearch, current homepage for {company_name}: {final_homepage_url} (Source: {final_homepage_source})")

    # --- Этап 2: HomepageFinder (Wikidata, Google->Wiki) ---
    if broadcast_update: await broadcast_update({"type": "progress", "company": company_name, "current": company_index + 1, "total": total_companies, "status": "processing_homepage_finders"})
    homepage_finder = finder_instances.get('HomepageFinder')
    logger.debug(f"Checking conditions for HomepageFinder for {company_name}: run_standard_homepage_finders={run_standard_homepage_finders}, finder_exists={homepage_finder is not None}, final_homepage_url_is_None={(final_homepage_url is None)}")
    if run_standard_homepage_finders and homepage_finder and not final_homepage_url: # <--- Ключевое условие
        try:
            context = {'session': aiohttp_session}
            logger.info(f"Calling HomepageFinder for {company_name} (as previous steps did not yield a live homepage)")
            finding = await homepage_finder.find(company_name, **context)
            company_findings.append(finding)
            if not finding.get("error") and finding.get("result"):
                candidate_hp_url = finding["result"]
                
                # Нормализация URL - удаление завершающего слеша
                if candidate_hp_url.endswith('/'):
                    candidate_hp_url = candidate_hp_url.rstrip('/')
                    logger.info(f"Normalized URL by removing trailing slash: {candidate_hp_url}")
                
                logger.info(f"HomepageFinder found candidate for {company_name}: {candidate_hp_url} (source: {finding.get('source')})")
                is_live = await check_url_liveness(candidate_hp_url, aiohttp_session)
                logger.info(f"Liveness check for HomepageFinder URL '{candidate_hp_url}': {is_live}")
                if is_live:
                    final_homepage_url = candidate_hp_url
                    final_homepage_source = finding.get("source", "homepage_finder") # Источник от HomepageFinder
                    logger.info(f"Homepage from HomepageFinder for {company_name} ({final_homepage_url}) is LIVE and accepted. (Source: {final_homepage_source})")
                else:
                    logger.warning(f"Homepage from HomepageFinder for {company_name} ({candidate_hp_url}) is NOT LIVE. Discarding.")
            elif finding.get("error"):
                 logger.warning(f"HomepageFinder for {company_name} returned error: {finding.get('error')}")
            else:
                logger.info(f"HomepageFinder for {company_name} did not find a homepage URL.")
        except Exception as e:
            logger.error(f"Exception in HomepageFinder for {company_name}: {e}", exc_info=True)
            company_findings.append({"source": "homepage_finder", "result": None, "error": str(e), "_finder_instance_type": "HomepageFinder"})
    logger.info(f"After HomepageFinder, current homepage for {company_name}: {final_homepage_url} (Source: {final_homepage_source})")

    # --- Этап 3: LinkedIn Finder ---
    if broadcast_update: await broadcast_update({"type": "progress", "company": company_name, "current": company_index + 1, "total": total_companies, "status": "processing_linkedin_finder"})
    linkedin_finder = finder_instances.get('LinkedInFinder')
    if linkedin_finder:
        try:
            context = {
                'session': aiohttp_session, 
                'serper_api_key': serper_api_key, 
                'openai_api_key': llm_config.get("openai_api_key") 
            }
            logger.debug(f"Calling LinkedInFinder for {company_name}")
            finding = await linkedin_finder.find(company_name, **context)
            company_findings.append(finding)
            if not finding.get("error") and finding.get("result"):
                linkedin_url_result = finding["result"]
                
                # Нормализация LinkedIn URL - удаление завершающего слеша
                if linkedin_url_result and linkedin_url_result.endswith('/'):
                    linkedin_url_result = linkedin_url_result.rstrip('/')
                    logger.info(f"Normalized LinkedIn URL by removing trailing slash: {linkedin_url_result}")
                
                logger.info(f"LinkedInFinder found URL for {company_name}: {linkedin_url_result}")
            elif finding.get("error"):
                 logger.warning(f"LinkedInFinder for {company_name} returned error: {finding.get('error')}")
        except Exception as e:
            logger.error(f"Exception in LinkedInFinder for {company_name}: {e}", exc_info=True)
            company_findings.append({"source": "linkedin_finder", "result": None, "error": str(e), "_finder_instance_type": "LinkedInFinder"})

    # --- Этап 4: DomainCheckFinder (если все еще нет homepage) ---
    if broadcast_update: await broadcast_update({"type": "progress", "company": company_name, "current": company_index + 1, "total": total_companies, "status": "processing_domain_check"})
    domain_check_finder = finder_instances.get('DomainCheckFinder')
    logger.debug(f"Checking conditions for DomainCheckFinder for {company_name}: run_domain_check_finder={run_domain_check_finder}, finder_exists={domain_check_finder is not None}, final_homepage_url_is_None={(final_homepage_url is None)}")
    if run_domain_check_finder and domain_check_finder and not final_homepage_url: # <--- Ключевое условие
        try:
            context = {'session': aiohttp_session}
            logger.info(f"Calling DomainCheckFinder for {company_name} as fallback (no live homepage found yet)")
            finding = await domain_check_finder.find(company_name, **context)
            company_findings.append(finding)
            if not finding.get("error") and finding.get("result"):
                candidate_dc_url = finding["result"]
                
                # Нормализация URL - удаление завершающего слеша
                if candidate_dc_url.endswith('/'):
                    candidate_dc_url = candidate_dc_url.rstrip('/')
                    logger.info(f"Normalized URL by removing trailing slash: {candidate_dc_url}")
                
                logger.info(f"DomainCheckFinder found candidate for {company_name}: {candidate_dc_url}")
                is_live = await check_url_liveness(candidate_dc_url, aiohttp_session)
                logger.info(f"Liveness check for DomainCheckFinder URL '{candidate_dc_url}': {is_live}")
                if is_live:
                    final_homepage_url = candidate_dc_url
                    final_homepage_source = "domain_check_finder"
                    logger.info(f"Homepage from DomainCheckFinder for {company_name} ({final_homepage_url}) is LIVE and accepted.")
                else:
                    logger.warning(f"Homepage from DomainCheckFinder for {company_name} ({candidate_dc_url}) is NOT LIVE. Discarding.")
            elif finding.get("error"):
                 logger.warning(f"DomainCheckFinder for {company_name} returned error: {finding.get('error')}")
            else:
                logger.info(f"DomainCheckFinder for {company_name} did not find a homepage URL.")
        except Exception as e:
            logger.error(f"Exception in DomainCheckFinder for {company_name}: {e}", exc_info=True)
            company_findings.append({"source": "domain_check_finder", "result": None, "error": str(e), "_finder_instance_type": "DomainCheckFinder"})
    logger.info(f"Final decision for {company_name} homepage: {final_homepage_url if final_homepage_url else 'Not found'} (Source: {final_homepage_source if final_homepage_source else 'N/A'})")

    if broadcast_update: await broadcast_update({"type": "progress", "company": company_name, "current": company_index + 1, "total": total_companies, "status": "generating_markdown"})
    if company_findings:
        await _generate_and_save_raw_markdown_report_async(company_name, company_findings, openai_client, llm_config, raw_markdown_output_path)
    
    if broadcast_update: await broadcast_update({"type": "progress", "company": company_name, "current": company_index + 1, "total": total_companies, "status": "generating_description"})
    structured_data = None
    description = f"Error: Could not generate final description for {company_name}."
    try:
        logger.info(f"Calling description_generator.generate_description for {company_name}")
        generated_result = await description_generator.generate_description(company_name, company_findings)
        logger.info(f"Received result from description_generator for {company_name}, type: {type(generated_result).__name__}")
        if isinstance(generated_result, dict):
            logger.info(f"Result keys: {list(generated_result.keys())}")
        
        if isinstance(generated_result, str) or (isinstance(generated_result, dict) and generated_result.get("error")):
            error_message = generated_result if isinstance(generated_result, str) else generated_result.get("error")
            description = f"Error generating structured data: {error_message}"
            logger.warning(f"Could not generate structured data for {company_name}. Reason: {error_message}")
        elif isinstance(generated_result, dict):
            description = generated_result.get("description", f"No text description generated for {company_name}.")
            structured_data = generated_result
            logger.info(f"Set structured_data for {company_name}, has keys: {list(structured_data.keys() if structured_data else [])}")
        else:
            logger.warning(f"Unexpected result type from description_generator for {company_name}: {type(generated_result)}")
    except Exception as e:
        logger.error(f"Exception in description_generator for {company_name}: {e}", exc_info=True)
        description = f"Exception during final description generation: {str(e)}"

    # Финальная нормализация homepage_url, удаление слеша в конце если есть
    if final_homepage_url and final_homepage_url.endswith('/'):
        final_homepage_url = final_homepage_url.rstrip('/')
        logger.info(f"Final normalization: removed trailing slash from homepage URL: {final_homepage_url}")

    result = {
    "Company_Name": company_name,
    "Official_Website": final_homepage_url or "Not found",
    "LinkedIn_URL": linkedin_url_result or "Not found",
    "Description": description,
    "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "structured_data": structured_data
    }

    
    logger.debug(
        f"Final CSV data for {company_name}: "
        f"Company_Name='{result['Company_Name']}', "
        f"Official_Website='{result['Official_Website']}', "
        f"LinkedIn_URL='{result['LinkedIn_URL']}', "
        f"desc_len={len(result['Description']) if result['Description'] else 0}"
    )
    if output_csv_path:
        file_exists = os.path.exists(output_csv_path)
        try:
            csv_row = {key: result.get(key) for key in csv_fields}
            save_results_csv([csv_row], output_csv_path, csv_fields, append_mode=file_exists)
            logger.info(f"Saved CSV row for {company_name} to {output_csv_path}")
        except Exception as e: logger.error(f"Error saving CSV for {company_name}: {e}", exc_info=True)
    
    if output_json_path and structured_data and not (isinstance(structured_data, dict) and structured_data.get("error")):
        try:
            save_structured_data_incrementally(result, output_json_path) 
            logger.info(f"Saved structured JSON for {company_name} to {output_json_path}")
        except Exception as e: logger.error(f"Error saving structured JSON for {company_name}: {e}", exc_info=True)
    
    if broadcast_update: await broadcast_update({"type": "company_completed", "company": company_name, "current": company_index + 1, "total": total_companies, "status": "completed", "result": {key: result.get(key) for key in csv_fields}})
    return result

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
    llm_deep_search_config_override: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    logger.info(f"Processing {len(company_names)} companies in batches of {batch_size}")
    
    finder_instances: Dict[str, Finder] = {}
    if llm_config.get("openai_api_key"): 
        finder_instances['HomepageFinder'] = HomepageFinder(serper_api_key, openai_api_key=llm_config["openai_api_key"], verbose=llm_config.get("verbose_finders", False))
        finder_instances['LinkedInFinder'] = LinkedInFinder(serper_api_key, openai_api_key=llm_config.get("openai_api_key"), verbose=llm_config.get("verbose_finders", False))
    else:
        finder_instances['HomepageFinder'] = HomepageFinder(serper_api_key, verbose=llm_config.get("verbose_finders", False))
        finder_instances['LinkedInFinder'] = LinkedInFinder(serper_api_key, verbose=llm_config.get("verbose_finders", False))
    
    if run_llm_deep_search_pipeline_cfg:
        finder_instances['LLMDeepSearchFinder'] = LLMDeepSearchFinder(openai_client.api_key, verbose=llm_config.get("verbose_finders", False))
    
    if run_domain_check_finder_cfg:
        finder_instances['DomainCheckFinder'] = DomainCheckFinder(custom_tlds=llm_config.get("domain_check_tlds"), verbose=llm_config.get("verbose_finders", False))

    description_generator = DescriptionGenerator(openai_client.api_key, model_config=llm_config.get('description_generator_model_config'))
    
    all_results = []
    csv_fields = ["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp"]
    total_companies_count = len(company_names)

    for i in range(0, total_companies_count, batch_size):
        batch_company_names = company_names[i:i + batch_size]
        logger.info(f"Processing batch {i//batch_size + 1}/{(total_companies_count + batch_size - 1)//batch_size}: {batch_company_names}")
        
        tasks = []
        for j, company_name_in_batch in enumerate(batch_company_names):
            global_company_index = i + j
            task = asyncio.create_task(
                _process_single_company_async(
                    company_name=company_name_in_batch, openai_client=openai_client,
                    aiohttp_session=aiohttp_session, sb_client=sb_client, serper_api_key=serper_api_key,
                    finder_instances=finder_instances,
                    description_generator=description_generator, 
                    llm_config=llm_config,
                    raw_markdown_output_path=raw_markdown_output_path, 
                    output_csv_path=output_csv_path,
                    output_json_path=output_json_path, 
                    csv_fields=csv_fields,
                    company_index=global_company_index, 
                    total_companies=total_companies_count, 
                    context_text=context_text, 
                    run_llm_deep_search_pipeline=run_llm_deep_search_pipeline_cfg,
                    run_standard_homepage_finders=run_standard_pipeline_cfg,
                    run_domain_check_finder=run_domain_check_finder_cfg,
                    llm_deep_search_config_override=llm_deep_search_config_override,
                    broadcast_update=broadcast_update
                )
            )
            tasks.append(task)
        
        batch_results_with_exceptions = await asyncio.gather(*tasks, return_exceptions=True)
        for res_or_exc in batch_results_with_exceptions:
            if isinstance(res_or_exc, Exception): logger.error(f"Error processing company in batch: {res_or_exc}", exc_info=res_or_exc)
            elif isinstance(res_or_exc, dict): all_results.append(res_or_exc)
            else: logger.warning(f"Unexpected result type from batch: {type(res_or_exc)} - {res_or_exc}")
        logger.info(f"Finished processing batch {i//batch_size + 1}")
    
    if output_json_path and all_results:
        valid_results = [r for r in all_results if r.get("structured_data") and not (isinstance(r.get("structured_data"), dict) and r.get("structured_data").get("error"))]
        if valid_results: 
            try: save_results_json(valid_results, output_json_path, append_mode=False); logger.info(f"Saved all {len(valid_results)} structured data to {output_json_path}")
            except Exception as e: logger.error(f"Error saving all structured data to JSON: {e}", exc_info=True)
        else: logger.info(f"No valid structured data to save in final JSON for {output_json_path}")
    return all_results

async def run_pipeline_for_file(
    input_file_path: str | Path,
    output_csv_path: str | Path,
    pipeline_log_path: str,
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
    if not company_names: logger.error(f"No valid company names in {input_file_path}"); return 0, 0, []
    logger.info(f"Loaded {len(company_names)} companies from {input_file_path}")
    current_expected_csv_fieldnames = ["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp"]
    structured_data_dir = session_dir_path / "structured_data"; structured_data_dir.mkdir(exist_ok=True)
    structured_data_json_path = structured_data_dir / "company_profiles.json"
    raw_markdown_output_dir = session_dir_path / "raw_markdown_reports"; raw_markdown_output_dir.mkdir(exist_ok=True)
    llm_deep_search_config_specific = llm_config.get('llm_deep_search_config')
    
    run_llm_deep_search_cfg = llm_config.get('run_llm_deep_search_pipeline', run_llm_deep_search_pipeline)
    run_standard_cfg = llm_config.get('run_standard_pipeline', run_standard_pipeline)
    run_domain_check_cfg = llm_config.get('run_domain_check_finder', True)

    results = await process_companies(
        company_names, openai_client, aiohttp_session, sb_client, serper_api_key,
        llm_config=llm_config, raw_markdown_output_path=raw_markdown_output_dir,
        batch_size=main_batch_size, context_text=context_text,
        run_llm_deep_search_pipeline_cfg=run_llm_deep_search_cfg,
        run_standard_pipeline_cfg=run_standard_cfg,
        run_domain_check_finder_cfg=run_domain_check_cfg,
        broadcast_update=broadcast_update, output_csv_path=str(output_csv_path),
        output_json_path=str(structured_data_json_path), llm_deep_search_config_override=llm_deep_search_config_specific
    )
    if results:
        try:
            csv_results = []
            for r in results: csv_results.append({key: r.get(key) for key in current_expected_csv_fieldnames})
            save_results_csv(csv_results, output_csv_path, current_expected_csv_fieldnames)
            logger.info(f"Results saved to {output_csv_path}")
        except Exception as e: logger.error(f"Error saving results to CSV: {e}", exc_info=True)
    # Улучшенный алгоритм подсчета успешных обработок
    # Считаем успешными обработки, где есть structured_data
    logger.info(f"Checking results for validation with {len(results)} entries")
    for r in results:
        company_name = r.get('Company_Name', 'Unknown')
        # Проверяем описание в результате
        has_description = r.get("Description") is not None and len(r.get("Description", "")) > 0
        # Проверяем, начинается ли description с "Error"
        starts_with_error = r.get("Description", "").startswith("Error") if has_description else True
        # Проверяем наличие structured_data
        has_structured_data = r.get("structured_data") is not None
        
        logger.info(f"Validation for {company_name}: has_desc={has_description}, starts_with_error={starts_with_error}, has_structured_data={has_structured_data}")
        
        if has_structured_data:
            struct_keys = list(r.get("structured_data").keys())
            logger.info(f"  Structured data keys: {struct_keys}")
            # Проверяем, есть ли в structured_data свое description
            has_desc_in_struct = 'description' in struct_keys
            struct_desc_len = len(r.get("structured_data", {}).get("description", "")) if has_desc_in_struct else 0
            logger.info(f"  Has description in structured data: {has_desc_in_struct}, length: {struct_desc_len}")

    # Условие для успешной обработки: либо есть Description не начинающийся с Error, либо есть structured_data
    success_count = sum(1 for r in results if 
                       (r.get("Description") and not r.get("Description", "").startswith("Error")) or
                       (r.get("structured_data") and isinstance(r.get("structured_data"), dict) and not r.get("structured_data").get("error")))
    failure_count = len(results) - success_count
    return success_count, failure_count, results

def setup_session_logging(pipeline_log_path: str):
    """
    Setup logging for a session.
    
    Args:
        pipeline_log_path: Path to save pipeline logs
    """
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s:%(module)s:%(funcName)s:%(lineno)d] - %(message)s'
    )
    
    root_logger = logging.getLogger() 
    
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler) and \
           (handler.baseFilename == pipeline_log_path):
            root_logger.removeHandler(handler)
            handler.close()

    pipeline_handler = logging.FileHandler(pipeline_log_path, mode='w', encoding='utf-8')
    pipeline_handler.setFormatter(detailed_formatter)
    pipeline_handler.setLevel(logging.INFO) 
    root_logger.addHandler(pipeline_handler)
    
    root_logger.setLevel(logging.INFO) 

    logger.info("Session logging setup complete with detailed formatter and INFO level for file.")
    # Удаляем отладочное логирование
    # logging.getLogger().debug("Root logger DEBUG level test message for session log.")
    
    # Отключаем подробное логирование для библиотек HTTP-клиентов
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

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
    
    setup_session_logging(str(pipeline_log_path))
    
    # Создаем SSL контекст, который не проверяет сертификаты
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    # Создаем коннектор с этим SSL контекстом
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(connector=connector) as session: # <--- Используем коннектор
        initial_expected_csv_fieldnames = ["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp"]
        
        success_count, failure_count, results = await run_pipeline_for_file(
            input_file_path=input_file_path, output_csv_path=output_csv_path,
            pipeline_log_path=str(pipeline_log_path),
            session_dir_path=session_dir_path,
            llm_config=llm_config,
            context_text=None, company_col_index=company_col_index,
            aiohttp_session=session, # Передаем сессию с настроенным коннектором
            sb_client=sb_client, openai_client=openai_client,
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