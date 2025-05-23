"""
HubSpot Pipeline Adapter Module

Extends the base PipelineAdapter to include HubSpot integration
"""

import logging
import os
import datetime # Добавлено для HubSpotAdapter
from typing import Dict, List, Any, Optional, Tuple, Callable, Union
from pathlib import Path
import aiohttp
from openai import AsyncOpenAI
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient
from dotenv import load_dotenv
from urllib.parse import urlparse # Добавлено для HubSpotAdapter
import asyncio # Добавляем импорт asyncio

from src.pipeline.adapter import PipelineAdapter
from src.pipeline.core import process_companies
from src.data_io import load_and_prepare_company_names, save_results_csv, load_session_metadata, save_session_metadata
from .client import HubSpotClient

logger = logging.getLogger(__name__)

class HubSpotAdapter:
    """
    Адаптер для интеграции HubSpot с основным пайплайном обработки компаний.
    
    Обеспечивает:
    - Проверку существования компании в HubSpot по домену
    - Извлечение существующего описания, если оно актуально
    - Сохранение новых описаний в HubSpot
    """
    
    def __init__(self, api_key: Optional[str] = None, max_age_months: int = 6):
        """
        Инициализация адаптера.
        
        Args:
            api_key (str, optional): API ключ для HubSpot. Если не указан, 
                                     будет взят из переменной окружения HUBSPOT_API_KEY.
            max_age_months (int): Максимальный возраст описания в месяцах.
                                  Описания старше этого возраста будут считаться устаревшими.
        """
        # Загружаем переменные окружения, если api_key не передан явно и нет в .env
        if api_key is None:
            load_dotenv() # Убедимся, что .env загружен
            api_key = os.getenv("HUBSPOT_API_KEY")

        self.client = HubSpotClient(api_key=api_key) # Передаем api_key клиенту
        self.max_age_months = max_age_months
        logger.info(f"HubSpot Adapter initialized with max age: {max_age_months} months. API key {'present' if api_key else 'MISSING'}.")
    
    async def check_company_description(self, company_name: str, url: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка наличия актуального описания компании в HubSpot.
        
        Args:
            company_name (str): Название компании
            url (str): URL компании
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: 
                - Первый элемент (description_is_fresh): True если найдено актуальное описание (пропускаем обработку), иначе False.
                - Второй элемент: Словарь с данными о компании, если найдена, иначе None.
        """
        if not self.client.api_key:
            logger.warning("HubSpot API key not available in HubSpotAdapter. Skipping check.")
            return False, None # Не пропускаем, нет ключа

        if not url:
            logger.info(f"No URL provided for company '{company_name}', skipping HubSpot check")
            return False, None # Не пропускаем, нет URL
        
        try:
            domain = self._extract_domain_from_url(url)
            if not domain:
                logger.warning(f"Could not extract domain from URL '{url}' for company '{company_name}'")
                return False, None # Не пропускаем, нет домена
            
            logger.info(f"Checking HubSpot for company '{company_name}' with domain '{domain}'")
            company = await self.client.search_company_by_domain(domain)
            
            if not company:
                logger.info(f"Company '{company_name}' with domain '{domain}' not found in HubSpot")
                return False, None # Не пропускаем, компания не найдена
            
            properties = company.get("properties", {})
            description = properties.get("ai_description") 
            updated_timestamp = properties.get("ai_description_updated")
            linkedin_page = properties.get("linkedin_company_page") # Извлекаем LinkedIn URL
            
            logger.info(
                f"Found company in HubSpot: {properties.get('name')}, "
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
                    # Найдено свежее описание, поэтому возвращаем True (пропускаем обработку)
                    # Возвращаем company, чтобы иметь доступ к linkedin_page в вызывающем коде
                    return True, company 
                else:
                    logger.info(
                        f"Description for '{company_name}' in HubSpot is outdated. "
                        f"Last updated: {updated_timestamp}"
                    )
                    # Описание устарело, не пропускаем обработку
                    return False, company 
            else:
                logger.info(f"No AI description or timestamp found for '{company_name}' in HubSpot")
                # Нет описания/даты, не пропускаем обработку
                return False, company
        
        except Exception as e:
            logger.error(f"Error checking company '{company_name}' in HubSpot: {e}", exc_info=True)
            return False, None # Ошибка, не пропускаем обработку
    
    async def create_company(
        self, 
        company_name: str, 
        url: str, 
        description: str,
        linkedin_url: Optional[str] = None  # Добавляем LinkedIn URL
    ) -> Optional[Dict[str, Any]]:
        """
        Создание новой компании в HubSpot.
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
                "ai_description": description, # Используем кастомное поле HubSpot
                "ai_description_updated": now # Используем кастомное поле HubSpot
            }
            if linkedin_url: # Добавляем LinkedIn если есть
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
        linkedin_url: Optional[str] = None # Добавляем LinkedIn URL
    ) -> Tuple[bool, Optional[str]]:
        """
        Сохранение описания компании в HubSpot.
        Возвращает кортеж (успех, ID компании в HubSpot или None).
        """
        if not self.client.api_key:
            logger.warning("HubSpot API key not available in HubSpotAdapter. Skipping save.")
            return False, None # Возвращаем ID как None

        company_id_to_return: Optional[str] = None
        try:
            if not company_data and url: # Если компания не найдена ранее, ищем снова
                domain = self._extract_domain_from_url(url)
                if domain:
                    company_data = await self.client.search_company_by_domain(domain)
            
            if company_data:
                company_id = company_data.get("id")
                company_id_to_return = company_id # Сохраняем ID для возврата
                now = datetime.datetime.now().strftime("%Y-%m-%d")
                properties_to_update = {
                    "ai_description": description, # Используем кастомное поле HubSpot
                    "ai_description_updated": now # Используем кастомное поле HubSpot
                }
                if linkedin_url: # Добавляем LinkedIn если есть
                    properties_to_update["linkedin_company_page"] = linkedin_url
                
                logger.info(f"Updating description and LinkedIn for company '{company_name}' (ID: {company_id}) in HubSpot. LinkedIn: {linkedin_url}")
                result = await self.client.update_company_properties(company_id, properties_to_update)
                
                if result:
                    logger.info(f"Successfully updated description for '{company_name}' in HubSpot")
                    return True, company_id_to_return # Возвращаем ID
                else:
                    logger.error(f"Failed to update description for '{company_name}' in HubSpot")
                    return False, None # Возвращаем ID как None
            else: # Компания не найдена, создаем новую
                logger.info(f"Company '{company_name}' not found in HubSpot, creating new entry.")
                new_company = await self.create_company(company_name, url, description, linkedin_url)
                if new_company:
                    company_id_to_return = new_company.get("id")
                    return True, company_id_to_return # Возвращаем ID новой компании
                return False, None # Возвращаем ID как None
        
        except Exception as e:
            logger.error(f"Error saving description for '{company_name}' in HubSpot: {e}", exc_info=True)
            return False, None # Возвращаем ID как None
    
    def _extract_domain_from_url(self, url: str) -> str:
        """
        Извлечение домена из URL.
        """
        return self.client._normalize_domain(url) # Используем метод из HubSpotClient
    
    def get_company_details_from_hubspot_data(self, company_data: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
        """
        Извлечение описания, временной метки и URL LinkedIn из данных о компании HubSpot.
        """
        properties = company_data.get("properties", {})
        description = properties.get("ai_description", "") 
        timestamp = properties.get("ai_description_updated", "") 
        linkedin_url = properties.get("linkedin_company_page") # Может быть None
        return description, timestamp, linkedin_url

class HubSpotPipelineAdapter(PipelineAdapter):
    """
    Pipeline adapter with HubSpot integration
    
    This class extends the base PipelineAdapter to include
    functionality for checking and updating data in HubSpot.
    """
    
    def __init__(self, config_path: str = "llm_config.yaml", input_file: Optional[str] = None, session_id: Optional[str] = None):
        super().__init__(config_path, input_file, session_id) # Передаем session_id
        self.hubspot_adapter: Optional[HubSpotAdapter] = None
        # use_hubspot и max_age_months будут инициализированы в self.setup() из llm_config
        # self.use_hubspot = True # Будет определено в setup
        # self.max_age_months = 6 # Будет определено в setup
        
        # Атрибут для хранения информации о дедупликации
        self.deduplication_info = None
    
    async def setup(self) -> bool:
        """
        Set up the pipeline configuration and dependencies, including HubSpot.
        """
        # Сначала выполняем базовую настройку из PipelineAdapter
        setup_successful = await super().setup()
        if not setup_successful:
            return False

        # Затем настраиваем HubSpot интеграцию
        # API ключ должен быть в self.api_keys['hubspot'], загруженный в processing_runner.py
        hubspot_api_key = self.api_keys.get("hubspot")
        
        # use_hubspot_integration берется из llm_config.yaml
        self.use_hubspot = self.llm_config.get("use_hubspot_integration", False) # По умолчанию False, если не указано
        self.max_age_months = self.llm_config.get("hubspot_description_max_age_months", 6)
        
        if self.use_hubspot:
            if hubspot_api_key:
                self.hubspot_adapter = HubSpotAdapter(api_key=hubspot_api_key, max_age_months=self.max_age_months)
                logger.info(f"HubSpot integration enabled via config. Max description age: {self.max_age_months} months.")
            else:
                logger.warning("HubSpot integration is enabled in config, but HUBSPOT_API_KEY is missing. HubSpot will not be used.")
                self.use_hubspot = False # Отключаем, если нет ключа
        else:
            logger.info("HubSpot integration is disabled via config or HUBSPOT_API_KEY.")
            
        return True # Возвращаем True, если базовая настройка прошла успешно

    async def run_pipeline_for_file(self, input_file_path: str | Path, output_csv_path: str | Path, 
                                   pipeline_log_path: Path, # Изменен тип на Path
                                   session_dir_path: Path, llm_config: Dict[str, Any],
                                   context_text: str | None, company_col_index: int, 
                                   aiohttp_session: aiohttp.ClientSession,
                                   sb_client: CustomScrapingBeeClient, openai_client: AsyncOpenAI,
                                   serper_api_key: str, # Оставляем, т.к. используется в process_companies
                                   expected_csv_fieldnames: list[str], broadcast_update: Optional[Callable] = None,
                                   main_batch_size: int = 5, run_standard_pipeline: bool = True,
                                   run_llm_deep_search_pipeline: bool = True) -> tuple[int, int, list[dict]]:
        """
        Run the pipeline for a specific input file with HubSpot integration
        """
        # Запускаем стандартную обработку файла с нормализацией URL и удалением дубликатов
        logger.info(f"Normalizing URLs and removing duplicates in input file: {input_file_path}")
        
        try:
            # Создаем временный файл для обработанных данных
            processed_file_path = session_dir_path / f"processed_{Path(input_file_path).name}"
            
            # Импортируем функцию нормализации и удаления дубликатов
            from normalize_urls import normalize_and_remove_duplicates
            
            # Вызываем асинхронную функцию normalize_and_remove_duplicates
            # Убедимся, что передаем session_id
            normalized_file, dedup_info = await normalize_and_remove_duplicates(
                str(input_file_path), 
                str(processed_file_path),
                session_id_for_metadata=self.session_id, # Передаем session_id
                scrapingbee_client=sb_client # <--- Добавляем sb_client сюда
            )
            
            if normalized_file:
                logger.info(f"Successfully processed {input_file_path} (URL check, dedup), saved to {normalized_file}")
                logger.info(f"Processing details: {dedup_info}")
                # Используем обработанный файл вместо исходного
                input_file_path = normalized_file
                
                # Сохраняем информацию о дедупликации и проверке URL для последующего использования
                # self.deduplication_info теперь может содержать более расширенную информацию из dedup_info
                self.deduplication_info = dedup_info 
                
                # Дополнительно, если нужно обновить метаданные сессии на этом этапе (хотя normalize_and_remove_duplicates это уже делает)
                # Можно рассмотреть, нужно ли дублировать логику или положиться на внутреннее обновление в normalize_and_remove_duplicates.
                # Пока что self.deduplication_info сохраняется для возможного использования в других частях HubSpotPipelineAdapter.

            elif dedup_info and dedup_info.get("error"):
                logger.error(f"Failed to process {input_file_path} (URL check, dedup): {dedup_info.get('error')}. Using original file.")
                # В случае ошибки, можно также сохранить dedup_info в метаданные сессии, если это необходимо
                # Например, добавив их в self.session_data или специальное поле.
            else:
                logger.warning(f"Processing {input_file_path} (URL check, dedup) did not return a file. Using original file.")
        except Exception as e:
            logger.error(f"Error processing {input_file_path}: {e}")
            logger.warning("Using original file without normalization and deduplication")
            
        # Создаем необходимые директории
        input_file_path = Path(input_file_path)
        output_csv_path = Path(output_csv_path)
        structured_data_dir = session_dir_path / "json"
        structured_data_dir.mkdir(exist_ok=True)
        structured_data_json_path = structured_data_dir / f"{self.session_id or 'results'}.json"
        
        # Создаем директорию для результатов Markdown
        raw_markdown_output_dir = session_dir_path / "markdown"
        raw_markdown_output_dir.mkdir(exist_ok=True)

        # Загрузка данных о компаниях остается прежней
        company_data_list = load_and_prepare_company_names(input_file_path, company_col_index)
        if not company_data_list:
            logger.error(f"No valid company names in {input_file_path}")
            return 0, 0, []
            
        # Создаем или очищаем CSV файл перед началом обработки
        save_results_csv([], output_csv_path, expected_csv_fieldnames, append_mode=False)
        logger.info(f"Created empty CSV file with headers at {output_csv_path}")

        all_results: List[Dict[str, Any]] = []
        success_count = 0
        failure_count = 0
        
        companies_to_process_standard: List[Dict[str, Any]] = []
        
        # Предварительная проверка компаний в HubSpot
        if self.use_hubspot and self.hubspot_adapter:
            logger.info("HubSpot integration is active. Checking companies before processing...")
            for i, company_info_dict in enumerate(company_data_list):
                company_name = company_info_dict["name"]
                company_url = company_info_dict.get("url")

                # description_is_fresh будет True, если найдено свежее описание и обработку можно пропустить
                description_is_fresh, hubspot_company_data = await self.hubspot_adapter.check_company_description(company_name, company_url)
                
                # ИСПРАВЛЕНО: если description_is_fresh == True, значит, описание свежее и компания есть в HubSpot
                if description_is_fresh and hubspot_company_data: 
                    logger.info(f"Company '{company_name}' has a fresh description in HubSpot. Skipping processing.")
                    description, timestamp, linkedin_url = self.hubspot_adapter.get_company_details_from_hubspot_data(hubspot_company_data)
                    hubspot_id = hubspot_company_data.get("id") # <--- Получаем ID
                    result_from_hubspot = {
                        "Company_Name": company_name,
                        "Official_Website": company_url or hubspot_company_data.get("properties",{}).get("domain",""), 
                        "LinkedIn_URL": linkedin_url or "", 
                        "Description": description,
                        "Timestamp": timestamp,
                        "Data_Source": "HubSpot",
                        "HubSpot_Company_ID": hubspot_id or "" # <--- Добавляем ID в результат
                    }
                    
                    for field in expected_csv_fieldnames:
                        if field not in result_from_hubspot:
                            result_from_hubspot[field] = ""

                    all_results.append(result_from_hubspot)
                    save_results_csv([result_from_hubspot], output_csv_path, expected_csv_fieldnames, append_mode=True)
                    success_count +=1
                    if broadcast_update:
                        # Учитываем уже обработанные компании для корректного прогресс-бара
                        total_companies_count = len(company_data_list)
                        processed_count = len(all_results) # Используем длину all_results как количество обработанных
                        await broadcast_update(self.session_id, {"status": "processing", "progress": (processed_count / total_companies_count) * 100, "message": f"Processed {company_name} (from HubSpot)"})
                else: 
                    # Лог из check_company_description уже сказал, почему не пропускаем (не найдено, устарело, ошибка)
                    # logger.info(f"Company '{company_name}' needs processing or is not fresh in HubSpot.") # Этот лог дублируется или неточен теперь
                    company_info_dict["hubspot_data"] = hubspot_company_data # Сохраняем данные HubSpot для обновления, даже если описание устарело
                    companies_to_process_standard.append(company_info_dict)
            logger.info(f"{len(companies_to_process_standard)} companies require standard processing after HubSpot check.")
        else: 
            # HubSpot не используется, все компании идут на стандартную обработку
            logger.info("HubSpot integration is not active. All companies will be processed by the standard pipeline.")
            companies_to_process_standard = list(company_data_list)

        # Если остались компании для стандартной обработки
        if companies_to_process_standard:
            # Определяем, нужно ли дописывать в CSV/JSON
            # Если all_results уже содержит что-то (из HubSpot), то нужно дописывать.
            should_append_csv = len(all_results) > 0
            should_append_json = len(all_results) > 0 # Аналогично для JSON, если он используется таким же образом

            # Преобразуем companies_to_process_standard в формат, ожидаемый process_companies
            # List[Union[str, Tuple[str, str]]]
            company_names_for_core_processing = []
            for company_dict in companies_to_process_standard:
                name = company_dict['name']
                url = company_dict.get('url')
                if url:
                    company_names_for_core_processing.append((name, url))
                else:
                    company_names_for_core_processing.append(name)

            # Пути для raw markdown и JSON output в process_companies
            # (они могут быть перезаписаны или не использоваться в зависимости от конфигурации process_companies)
            raw_markdown_reports_path = session_dir_path / "raw_markdown_reports"
            raw_markdown_reports_path.mkdir(exist_ok=True) # Убедимся, что директория существует
            
            # Имя JSON файла можно сделать аналогичным CSV
            output_json_filename = output_csv_path.stem.replace("_results", "") + "_structured_results.json"
            output_json_path_for_core = session_dir_path / output_json_filename

            # Вызываем process_companies из src.pipeline.core
            # Убедимся, что передаем все необходимые и корректные аргументы
            std_results = await process_companies( # process_companies возвращает только список результатов
                company_names=company_names_for_core_processing,
                openai_client=openai_client,
                aiohttp_session=aiohttp_session,
                sb_client=sb_client,
                serper_api_key=self.api_keys.get("serper"), # Берем из self.api_keys
                llm_config=llm_config,
                raw_markdown_output_path=raw_markdown_reports_path,
                batch_size=main_batch_size, # Используем main_batch_size
                context_text=context_text,
                run_llm_deep_search_pipeline_cfg=run_llm_deep_search_pipeline, # Передаем флаг
                run_standard_pipeline_cfg=run_standard_pipeline, # Передаем флаг
                # run_domain_check_finder_cfg остается по умолчанию True в process_companies, если нужен другой контроль - добавить
                broadcast_update=broadcast_update,
                output_csv_path=str(output_csv_path), # Передаем путь к CSV для инкрементальной записи
                output_json_path=str(output_json_path_for_core), # Передаем путь к JSON
                expected_csv_fieldnames=expected_csv_fieldnames,
                # llm_deep_search_config_override - можно добавить, если есть в self
                # second_column_data - не передаем, т.к. URL уже в company_names_for_core_processing
                hubspot_client=self.hubspot_adapter if self.use_hubspot else None, # Передаем HubSpot адаптер
                use_raw_llm_data_as_description=self.llm_config.get('use_raw_llm_data_as_description', True), # Берем из llm_config
                csv_append_mode=should_append_csv, # Используем флаг для CSV
                json_append_mode=should_append_json # Используем флаг для JSON
            )
            
            # process_companies возвращает только список результатов.
            # success_count и failure_count нужно будет определить на основе std_results,
            # или модифицировать process_companies, чтобы она их возвращала.
            # Пока что, для простоты, будем считать все вернувшиеся результаты успешными, если они есть.
            # В идеале, каждый элемент в std_results должен иметь поле типа "status" или "error".
            
            std_success = len([res for res in std_results if res.get("Description")]) # Примерный подсчет успешных
            std_failure = len(std_results) - std_success # Примерный подсчет неуспешных

            success_count += std_success
            failure_count += std_failure
            
            all_results.extend(std_results)
            # Результаты уже сохранены в CSV внутри process_companies_batch

        logger.info(f"HubSpotPipelineAdapter finished. Total successes: {success_count}, Total failures: {failure_count}")
        return success_count, failure_count, all_results

async def test_hubspot_pipeline_adapter():
    # Пример простой тестовой функции (потребует настройки окружения и файлов)
    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    # Создаем временный input_file.xlsx
    import pandas as pd
    temp_input_data = {'Company Name': ['Test Company 1', 'HubSpot'], 'Website': ['www.testcompany1.com', 'hubspot.com']}
    temp_input_df = pd.DataFrame(temp_input_data)
    temp_input_path = Path("temp_input_test.xlsx")
    temp_input_df.to_excel(temp_input_path, index=False)
    
    # Создаем временный llm_config.yaml
    temp_llm_config_data = {
        "model": "gpt-3.5-turbo", # или другая модель
        "temperature": 0.1,
        "use_hubspot_integration": True, # Включаем HubSpot
        "hubspot_description_max_age_months": 1, # Ставим маленький срок для теста
        "messages": [ # Минимально необходимые сообщения
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": "Provide info about {company}."}
        ]
    }
    temp_llm_config_path = Path("temp_llm_config_test.yaml")
    import yaml
    with open(temp_llm_config_path, 'w') as f:
        yaml.dump(temp_llm_config_data, f)

    adapter = HubSpotPipelineAdapter(config_path=str(temp_llm_config_path), input_file=str(temp_input_path), session_id="test_session_hubspot")
    
    # Для setup нужны api_keys
    adapter.api_keys = {
        "openai": os.getenv("OPENAI_API_KEY"),
        "serper": os.getenv("SERPER_API_KEY"),
        "scrapingbee": os.getenv("SCRAPINGBEE_API_KEY"),
        "hubspot": os.getenv("HUBSPOT_API_KEY") # Убедитесь, что ключ есть
    }
    adapter.llm_config = temp_llm_config_data # Передаем конфиг напрямую для теста setup

    if not adapter.api_keys["hubspot"]:
        logger.error("HUBSPOT_API_KEY not found in environment variables. Test cannot run.")
        if temp_input_path.exists(): os.remove(temp_input_path)
        if temp_llm_config_path.exists(): os.remove(temp_llm_config_path)
        return

    await adapter.setup() # Вызываем setup для инициализации hubspot_adapter

    if adapter.use_hubspot and adapter.hubspot_adapter:
        logger.info("HubSpot adapter initialized in PipelineAdapter.")
        # Можно добавить вызов run, но он требует много зависимостей
        # success, failure, results = await adapter.run()
        # logger.info(f"Test run completed. Success: {success}, Failure: {failure}")
        # logger.info(f"Results: {results}")
    else:
        logger.warning("HubSpot adapter was NOT initialized in PipelineAdapter. Check config and API key.")

    # Очистка временных файлов
    if temp_input_path.exists():
        os.remove(temp_input_path)
    if temp_llm_config_path.exists():
        os.remove(temp_llm_config_path)

if __name__ == "__main__":
    # asyncio.run(test_hubspot_adapter()) # Для базовой проверки HubSpotAdapter
    asyncio.run(test_hubspot_pipeline_adapter()) # Для проверки HubSpotPipelineAdapter 