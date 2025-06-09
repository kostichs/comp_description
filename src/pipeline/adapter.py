"""
Pipeline Adapter Module

Provides the main adapter class for running the pipeline
"""

import asyncio
import aiohttp
import logging
import os
import yaml
import time
import ssl
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable
from openai import AsyncOpenAI
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient

# Standard pipeline components
from src.config import load_env_vars, load_llm_config
from description_generator import DescriptionGenerator
from finders.base import Finder
from finders.llm_deep_search_finder.finder import LLMDeepSearchFinder
from finders.linkedin_finder import LinkedInFinder

from finders.domain_check_finder import DomainCheckFinder
from finders.login_detection_finder import LoginDetectionFinder
from src.data_io import load_and_prepare_company_names, save_results_csv, save_results_json, load_session_metadata, save_session_metadata

# Импортируем функцию нормализации URL в файле
from normalize_urls import normalize_urls_in_file, remove_duplicates_by_domain, normalize_and_remove_duplicates

# Utils
from src.pipeline.utils.logging import setup_session_logging

logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 2

class PipelineAdapter:
    """
    Main adapter class for running the company description pipeline
    
    This class encapsulates the pipeline configuration, initialization,
    and execution logic.
    """
    
    def __init__(self, config_path: str = "llm_config.yaml", input_file: Optional[str] = None, session_id: Optional[str] = None, use_raw_llm_data_as_description: bool = True):
        """
        Initialize the pipeline adapter
        
        Args:
            config_path: Path to the LLM configuration file
            input_file: Path to the input file with company names
            session_id: Session ID for use in directory and file paths (optional)
            use_raw_llm_data_as_description: Whether to use raw LLM data as description instead of generating a new one
        """
        self.config_path = config_path
        self.input_file = input_file or "test_companies.csv"
        self.company_col_index = 0  # По умолчанию названия компаний в первом столбце
        self.session_id = session_id  # Сохраняем session_id, если он передан
        self.use_raw_llm_data_as_description = use_raw_llm_data_as_description  # Сохраняем флаг
        
        self.llm_config = {}
        self.api_keys = {
            "openai": None,
            "serper": None,
            "scrapingbee": None
        }
        
        # Will be initialized in setup()
        self.openai_client = None
        self.sb_client = None
        self.aiohttp_session = None
        
        # Output paths
        self.output_dir = Path("output")
        self.sessions_dir = None
        self.session_dir_path = None
        self.output_csv_path = None
        self.pipeline_log_path = None
        
    async def setup(self) -> bool:
        """
        Set up the pipeline configuration and dependencies
        
        Returns:
            bool: True if setup was successful
        """
        logger.info("Setting up pipeline")
        
        # Load configuration
        self._load_config()
        
        # Create output directories
        self._setup_directories()
        
        # Set up logging
        setup_session_logging(str(self.pipeline_log_path))
        
        # Initialize clients
        self._init_clients()
        
        return True
        
    async def run(self, expected_csv_fieldnames: Optional[List[str]] = None, write_to_hubspot: bool = True) -> Tuple[int, int, List[Dict[str, Any]]]:
        """
        Run the pipeline with current configuration
        
        Args:
            expected_csv_fieldnames (Optional[List[str]]): List of expected field names for the output CSV.
                                                           Defaults to a standard list if None.

        Returns:
            Tuple with success count, failure count, and results
        """
        await self.setup()
        
        # Создаем коннектор с обычными ограничениями для основного pipeline
        connector = aiohttp.TCPConnector(
            limit=50,  # Обычное количество соединений для основного pipeline
            limit_per_host=10,  # Обычное количество соединений на хост
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        async with aiohttp.ClientSession(connector=connector) as session:
            self.aiohttp_session = session
            
            # Expected CSV field names
            # Используем переданный список или значение по умолчанию
            final_expected_csv_fieldnames = expected_csv_fieldnames or [
                "Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp", "HubSpot_Company_ID"
            ]
            
            # Run pipeline for input file
            success_count, failure_count, results = await self.run_pipeline_for_file(
                input_file_path=self.input_file,
                output_csv_path=self.output_csv_path,
                pipeline_log_path=str(self.pipeline_log_path),
                session_dir_path=self.session_dir_path,
                llm_config=self.llm_config,
                context_text=None, # В базовом адаптере контекст не передается так
                company_col_index=self.company_col_index,
                aiohttp_session=session, # Используем созданную сессию
                sb_client=self.sb_client, # Должен быть инициализирован в setup
                openai_client=self.openai_client, # Должен быть инициализирован в setup
                serper_api_key=self.api_keys.get("serper"), # Берем из self.api_keys
                expected_csv_fieldnames=final_expected_csv_fieldnames, # <--- Передаем актуальный список
                broadcast_update=None, # В базовом адаптере broadcast_update не используется напрямую
                write_to_hubspot=write_to_hubspot # <--- Передаем флаг записи в HubSpot
                # main_batch_size, run_standard_pipeline, run_llm_deep_search_pipeline - специфичны для HubSpotPipelineAdapter.run_pipeline_for_file
                # или должны быть частью конфигурации, если применимо к базовому адаптеру.
            )
        
        # Save session metadata
        session_metadata = {
            "session_id": self.session_id or time.strftime("%Y%m%d_%H%M%S"),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "input_file": str(self.input_file),
            "output_csv": str(self.output_csv_path),
            "session_dir": str(self.session_dir_path),
            "companies_processed": len(results),
            "success_count": success_count,
            "failure_count": failure_count
        }
        all_metadata = load_session_metadata()
        
        # Проверяем, есть ли уже запись о текущей сессии
        session_exists = False
        for i, meta in enumerate(all_metadata):
            if meta.get("session_id") == session_metadata["session_id"]:
                all_metadata[i].update(session_metadata)
                session_exists = True
                break
                
        # Если записи нет, добавляем новую
        if not session_exists:
            all_metadata.append(session_metadata)
            
        save_session_metadata(all_metadata)
        
        logger.info(f"Pipeline finished. Success: {success_count}, Failure: {failure_count}")
        return success_count, failure_count, results
        
    def _load_config(self):
        """Load configuration from files and environment"""
        # Load LLM config
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.llm_config = yaml.safe_load(f)
                logger.info(f"Loaded LLM config from {self.config_path}")
        except Exception as e:
            logger.error(f"Error loading LLM config: {e}")
            self.llm_config = {}
        
        # Load API keys
        scrapingbee_api_key, openai_api_key, serper_api_key, _ = load_env_vars()
        
        # Ensure API keys are loaded (from llm_config or environment)
        self.api_keys["openai"] = self.llm_config.get("openai_api_key") or openai_api_key
        self.api_keys["serper"] = self.llm_config.get("serper_api_key") or serper_api_key
        self.api_keys["scrapingbee"] = self.llm_config.get("scrapingbee_api_key") or scrapingbee_api_key
        
        # Validate required API keys
        if not self.api_keys["openai"]:
            raise ValueError("OpenAI API key not found")
        if not self.api_keys["serper"]:
            raise ValueError("Serper API key not found")
        if not self.api_keys["scrapingbee"]:
            raise ValueError("ScrapingBee API key not found")
            
        # Update llm_config with API keys
        self.llm_config["openai_api_key"] = self.api_keys["openai"]
        self.llm_config["serper_api_key"] = self.api_keys["serper"]
        self.llm_config["scrapingbee_api_key"] = self.api_keys["scrapingbee"]
        
    def _init_clients(self):
        """Initialize API clients"""
        self.openai_client = AsyncOpenAI(api_key=self.api_keys["openai"])
        self.sb_client = CustomScrapingBeeClient(api_key=self.api_keys["scrapingbee"])
        
    def _setup_directories(self):
        """Set up output directories and paths"""
        # Create output directories
        self.output_dir.mkdir(exist_ok=True)
        self.sessions_dir = self.output_dir / "sessions"
        self.sessions_dir.mkdir(exist_ok=True)
        
        # Используем переданный session_id или генерируем новый timestamp
        if self.session_id:
            logger.info(f"Using provided session_id: {self.session_id}")
            # Используем переданный session_id в качестве имени директории
            self.session_dir_path = self.sessions_dir / self.session_id
            self.session_dir_path.mkdir(exist_ok=True, parents=True)
            
            # Устанавливаем пути к результатам, соответствующие ожиданиям бэкенда
            self.output_csv_path = self.session_dir_path / f"{self.session_id}_results.csv"
            
            # Создаем родительские директории, если они не существуют
            if not self.output_csv_path.parent.exists():
                self.output_csv_path.parent.mkdir(exist_ok=True, parents=True)
            
            # Устанавливаем путь к логам
            self.pipeline_log_path = self.session_dir_path / "pipeline.log"
            
            # Создаем родительские директории для логов, если они не существуют
            if not self.pipeline_log_path.parent.exists():
                self.pipeline_log_path.parent.mkdir(exist_ok=True, parents=True)
        else:
            # Генерируем новый timestamp, если session_id не был передан
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            logger.info(f"No session_id provided, generating timestamp: {timestamp}")
            self.session_id = timestamp
            
            # Создаем директорию для сессии
            self.session_dir_path = self.sessions_dir / f"session_{timestamp}"
            self.session_dir_path.mkdir(exist_ok=True, parents=True)
            
            # Устанавливаем пути к результатам
            self.output_csv_path = self.session_dir_path / f"results_{timestamp}.csv"
            
            # Создаем родительские директории, если они не существуют
            if not self.output_csv_path.parent.exists():
                self.output_csv_path.parent.mkdir(exist_ok=True, parents=True)
            
            # Устанавливаем путь к логам
            logs_dir = self.session_dir_path / "logs"
            logs_dir.mkdir(exist_ok=True, parents=True)
            self.pipeline_log_path = logs_dir / f"pipeline_{timestamp}.log"
    
    async def run_pipeline_for_file(self, input_file_path: str | Path, output_csv_path: str | Path, 
                               pipeline_log_path: str, session_dir_path: Path, llm_config: Dict[str, Any],
                               context_text: str | None, company_col_index: int, aiohttp_session: aiohttp.ClientSession,
                               sb_client: Optional[CustomScrapingBeeClient], openai_client: AsyncOpenAI, serper_api_key: str,
                               expected_csv_fieldnames: list[str], broadcast_update: Optional[Callable] = None,
                               main_batch_size: int = DEFAULT_BATCH_SIZE,
                               run_llm_deep_search_pipeline: bool = True,
                               write_to_hubspot: bool = True) -> tuple[int, int, list[dict]]:
        """
        Run the pipeline for a specific input file
        
        Arguments:
            input_file_path: Path to the input CSV file with company names
            output_csv_path: Path to save the output CSV file
            pipeline_log_path: Path to save the pipeline log
            session_dir_path: Path to the session directory
            llm_config: LLM configuration dictionary
            context_text: Optional context text for the pipeline
            company_col_index: Index of the company name column (usually 0)
            aiohttp_session: aiohttp client session
            sb_client: ScrapingBee client
            openai_client: OpenAI client
            serper_api_key: Serper API key
            expected_csv_fieldnames: Expected CSV field names for the output
            broadcast_update: Optional callback for broadcasting updates
            main_batch_size: Batch size for parallel processing

            run_llm_deep_search_pipeline: Whether to run the LLM deep search pipeline
            write_to_hubspot: Whether to write results to HubSpot (default: True)
            
        Returns:
            (success_count, failure_count, results) tuple
        """
        # 1. Подготовка путей для сохранения результатов
        input_file_path = Path(input_file_path)
        output_csv_path = Path(output_csv_path)
        session_dir_path = Path(session_dir_path)
        
        # Создание директорий для результатов
        session_dir_path.mkdir(parents=True, exist_ok=True)
        
        # Создание директорий для JSON и raw data
        structured_data_dir = session_dir_path / "json"
        structured_data_dir.mkdir(exist_ok=True)
        structured_data_json_path = structured_data_dir / f"{self.session_id or 'results'}.json"
        
        raw_data_output_dir = session_dir_path / "raw_data"
        raw_data_output_dir.mkdir(exist_ok=True)
        
        # 1.5. Нормализация URL и удаление дубликатов во входном файле
        # ВАЖНО: Эта логика теперь перенесена в HubSpotPipelineAdapter
        # Отключаем здесь, чтобы избежать дублирования
        # logger.info(f"Normalizing URLs and removing duplicates in input file: {input_file_path}")
        # try:
        #     # Создаем временный файл для обработанных данных
        #     processed_file_path = session_dir_path / f"processed_{input_file_path.name}"
        #     
        #     # Нормализуем URL и удаляем дубликаты в одной операции
        #     processed_file = normalize_and_remove_duplicates(str(input_file_path), str(processed_file_path))
        #     
        #     if processed_file:
        #         logger.info(f"Successfully processed {input_file_path}, saved to {processed_file}")
        #         # Используем обработанный файл вместо исходного
        #         input_file_path = Path(processed_file)
        #     else:
        #         logger.warning(f"Failed to process {input_file_path}, using original file")
        # except Exception as e:
        #     logger.error(f"Error processing {input_file_path}: {e}")
        #     logger.warning("Using original file without normalization and deduplication")
        
        # 2. Загрузка списка компаний
        company_names = load_and_prepare_company_names(input_file_path, company_col_index)
        if not company_names:
            logger.error(f"No company names found in {input_file_path}")
            return 0, 0, []
            
        # Удаляем дубликаты компаний в памяти (по имени и по домену)
        seen_companies = set()
        seen_domains = set()
        unique_companies = []
        
        for company in company_names:
            company_name = company['name'] if isinstance(company, dict) else company
            company_url = company.get('url') if isinstance(company, dict) else None
            
            # Проверяем дубликаты по имени компании
            if company_name in seen_companies:
                logger.info(f"Skipping duplicate company by name: {company_name}")
                continue
                
            # Проверяем дубликаты по домену (если есть URL)
            if company_url and company_url in seen_domains:
                logger.info(f"Skipping duplicate company by domain: {company_name} ({company_url})")
                continue
                
            # Добавляем уникальную компанию в новый список
            unique_companies.append(company)
            seen_companies.add(company_name)
            if company_url:
                seen_domains.add(company_url)
        
        # Заменяем список компаний на список без дубликатов
        company_names = unique_companies
            
        logger.info(f"Loaded {len(company_names)} company names from {input_file_path}")
        
        # Конфигурация выполнения различных частей пайплайна
        run_standard_cfg = False  # Standard pipeline отключен
        run_llm_deep_search_cfg = run_llm_deep_search_pipeline
        run_domain_check_cfg = run_llm_deep_search_pipeline  # Нужен только LLM deep search pipeline
        
        # 3. Обработка компаний
        from src.pipeline.core import process_companies  # Импортируем здесь для избежания циклических импортов
        
        # Process companies
        results = await process_companies(
            company_names=company_names,
            openai_client=openai_client,
            aiohttp_session=aiohttp_session,
            sb_client=sb_client,
            serper_api_key=serper_api_key,
            llm_config=llm_config,
            raw_markdown_output_path=raw_data_output_dir,
            batch_size=main_batch_size,
            context_text=context_text,
            run_llm_deep_search_pipeline_cfg=run_llm_deep_search_cfg,
            run_standard_pipeline_cfg=run_standard_cfg,
            run_domain_check_finder_cfg=run_domain_check_cfg,
            broadcast_update=broadcast_update,
            output_csv_path=str(output_csv_path),
            output_json_path=str(structured_data_json_path),
            expected_csv_fieldnames=expected_csv_fieldnames,
            use_raw_llm_data_as_description=self.use_raw_llm_data_as_description,
            csv_append_mode=False,
            json_append_mode=False,
            write_to_hubspot=write_to_hubspot
        )
        
        # 4. Подсчет успехов/ошибок
        success_count = len([r for r in results if not r.get("error")])
        failure_count = len(results) - success_count
        
        return success_count, failure_count, results 