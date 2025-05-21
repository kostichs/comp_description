"""
HubSpot Pipeline Adapter Module

Extends the base PipelineAdapter to include HubSpot integration
"""

import logging
import os
from typing import Dict, List, Any, Optional, Tuple, Callable
from pathlib import Path
import aiohttp
from openai import AsyncOpenAI
from scrapingbee import ScrapingBeeClient

from src.pipeline.adapter import PipelineAdapter
from src.pipeline.core import process_companies
from src.integrations.hubspot.service import HubSpotIntegrationService
from src.data_io import load_and_prepare_company_names, save_results_csv

logger = logging.getLogger(__name__)

class HubSpotPipelineAdapter(PipelineAdapter):
    """
    Pipeline adapter with HubSpot integration
    
    This class extends the base PipelineAdapter to include
    functionality for checking and updating data in HubSpot.
    """
    
    def __init__(self, config_path: str = "llm_config.yaml", input_file: Optional[str] = None):
        """
        Initialize the HubSpot pipeline adapter
        
        Args:
            config_path: Path to the LLM configuration file
            input_file: Path to the input file with company names
        """
        super().__init__(config_path, input_file)
        self.hubspot_service = None
        self.use_hubspot_integration = True
    
    async def setup(self) -> bool:
        """
        Set up the pipeline configuration and dependencies
        
        Returns:
            bool: True if setup was successful
        """
        # Set up base pipeline
        result = await super().setup()
        
        # Set up HubSpot integration
        hubspot_api_key = self.llm_config.get("hubspot_api_key") or os.getenv("HUBSPOT_API_KEY")
        self.use_hubspot_integration = self.llm_config.get("use_hubspot_integration", True)
        max_age_months = self.llm_config.get("hubspot_description_max_age_months", 6)
        
        if hubspot_api_key and self.use_hubspot_integration:
            self.hubspot_service = HubSpotIntegrationService(
                api_key=hubspot_api_key,
                max_age_months=max_age_months
            )
            logger.info(f"HubSpot integration enabled with max age {max_age_months} months")
        else:
            logger.warning("HubSpot integration disabled or API key not provided")
            self.use_hubspot_integration = False
        
        return result
    
    async def run_pipeline_for_file(self, input_file_path: str | Path, output_csv_path: str | Path, 
                                   pipeline_log_path: str, session_dir_path: Path, llm_config: Dict[str, Any],
                                   context_text: str | None, company_col_index: int, aiohttp_session: aiohttp.ClientSession,
                                   sb_client: ScrapingBeeClient, openai_client: AsyncOpenAI, serper_api_key: str,
                                   expected_csv_fieldnames: list[str], broadcast_update: callable = None,
                                   main_batch_size: int = 5, run_standard_pipeline: bool = True,
                                   run_llm_deep_search_pipeline: bool = True) -> tuple[int, int, list[dict]]:
        """
        Run the pipeline with HubSpot integration
        
        Args:
            Same as in PipelineAdapter.run_pipeline_for_file
            
        Returns:
            Tuple with success count, failure count, and results
        """
        company_data = load_and_prepare_company_names(input_file_path, company_col_index)
        if not company_data: 
            logger.error(f"No valid company names in {input_file_path}")
            return 0, 0, []
        
        # Проверяем, был ли загружен второй столбец (данные в виде списка кортежей)
        has_second_column = False
        if company_data and isinstance(company_data[0], tuple) and len(company_data[0]) >= 2:
            has_second_column = True
            logger.info(f"Loaded {len(company_data)} companies with second column data from {input_file_path}")
            # Извлекаем только названия компаний для обработки
            company_names = [item[0] for item in company_data]
            # Сохраняем данные второго столбца для дальнейшего использования
            second_column_data = {item[0]: item[1] for item in company_data}
            
            # Проверка компаний в HubSpot
            if self.hubspot_service and has_second_column:
                logger.info("Checking companies in HubSpot before processing")
                all_results = []
                
                for company_name, website in second_column_data.items():
                    # Проверяем компанию в HubSpot
                    if website and self.use_hubspot_integration:
                        hubspot_data = await self.hubspot_service.get_company_data(website)
                        
                        if hubspot_data and hubspot_data.get("description"):
                            # Проверяем свежесть описания
                            is_fresh = await self.hubspot_service.should_process_company(website) == False
                            
                            if is_fresh:
                                # Используем данные из HubSpot и пропускаем обработку
                                logger.info(f"Using existing HubSpot data for {company_name}")
                                
                                result = {
                                    "Company_Name": company_name,
                                    "Official_Website": website,
                                    "LinkedIn_URL": hubspot_data.get("linkedin_url") or "Not found",
                                    "Description": hubspot_data.get("description"),
                                    "Timestamp": hubspot_data.get("timestamp"),
                                    "Data_Source": "HubSpot"
                                }
                                
                                # Сохраняем результат в CSV
                                if output_csv_path:
                                    # Проверяем существование файла
                                    import os
                                    file_exists = os.path.exists(output_csv_path)
                                    
                                    # Дополняем csv_fields полем Data_Source, если его там еще нет
                                    extended_csv_fields = list(expected_csv_fieldnames)
                                    if "Data_Source" not in extended_csv_fields:
                                        extended_csv_fields.append("Data_Source")
                                        
                                    # Сохраняем в CSV
                                    csv_row = {key: result.get(key) for key in extended_csv_fields if key in result}
                                    save_results_csv([csv_row], output_csv_path, extended_csv_fields, append_mode=file_exists)
                                    logger.info(f"Saved HubSpot data for {company_name} to {output_csv_path}")
                                
                                # Добавляем в результаты
                                all_results.append(result)
                                
                                # Отправляем обновление, если есть callback
                                if broadcast_update:
                                    await broadcast_update({
                                        "type": "company_completed", 
                                        "company": company_name,
                                        "status": "completed_from_hubspot",
                                        "result": result
                                    })
                                
                                # Удаляем компанию из списка для обработки
                                company_names.remove(company_name)
                                
                if not company_names:
                    # Все компании были найдены в HubSpot с актуальными данными
                    logger.info("All companies found in HubSpot with fresh data, no processing needed")
                    return len(all_results), 0, all_results
                
                logger.info(f"{len(all_results)} companies found in HubSpot with fresh data, {len(company_names)} need processing")
            
            if not run_standard_pipeline:
                logger.info("Standard homepage pipeline disabled because second column contains URLs")
        else:
            logger.info(f"Loaded {len(company_data)} companies from {input_file_path}")
            company_names = company_data
            second_column_data = {}
        
        # Если у нас остались компании для обработки, вызываем базовый метод
        if company_names:
            # Вызов базовой реализации
            return await super().run_pipeline_for_file(
                input_file_path=input_file_path,
                output_csv_path=output_csv_path,
                pipeline_log_path=pipeline_log_path,
                session_dir_path=session_dir_path,
                llm_config=llm_config,
                context_text=context_text,
                company_col_index=company_col_index,
                aiohttp_session=aiohttp_session,
                sb_client=sb_client,
                openai_client=openai_client,
                serper_api_key=serper_api_key,
                expected_csv_fieldnames=expected_csv_fieldnames,
                broadcast_update=broadcast_update,
                main_batch_size=main_batch_size,
                run_standard_pipeline=run_standard_pipeline,
                run_llm_deep_search_pipeline=run_llm_deep_search_pipeline
            )
        
        # Если все компании были обработаны из HubSpot
        return len(all_results), 0, all_results 