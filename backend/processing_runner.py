import asyncio
import logging
import os
import sys
import traceback
from pathlib import Path

# Adjust sys.path to allow importing from src
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline import run_pipeline_for_file, setup_session_logging # Import core function and logging setup
from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR # Import session helpers
from src.config import load_env_vars, load_llm_config # Import config loaders
from openai import AsyncOpenAI
from scrapingbee import ScrapingBeeClient
import aiohttp

async def run_session_pipeline(session_id: str, broadcast_update=None):
    """
    Runs the full data processing pipeline for a given session ID in the background.
    Updates the session metadata with status (running, completed, error).
    """
    session_logger = logging.getLogger(f"pipeline.session.{session_id}") # Создаем или получаем логгер сессии
    session_logger.info(f"Background task started for session: {session_id}")
    
    # --- 1. Load Session Metadata --- 
    try:
        all_metadata = load_session_metadata()
        session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
        if not session_data:
            session_logger.error(f"[BG Task {session_id}] Session metadata not found. Aborting.")
            return # Cannot proceed without metadata

        # ++ Читаем флаги выбора пайплайнов из метаданных ++
        run_standard_pipeline = session_data.get("run_standard_pipeline", True) # По умолчанию True
        run_llm_deep_search_pipeline = session_data.get("run_llm_deep_search_pipeline", False) # По умолчанию False
        session_logger.info(f"[BG Task {session_id}] Standard pipeline: {run_standard_pipeline}, LLM Deep Search: {run_llm_deep_search_pipeline}")

    except Exception as e:
        session_logger.error(f"[BG Task {session_id}] Error loading session metadata: {e}. Aborting.")
        return
        
    # --- 2. Prepare Paths and Context --- 
    try:
        # Construct absolute paths from relative paths stored in metadata
        input_file_path_rel = session_data.get("input_file_path")
        if not input_file_path_rel:
            raise ValueError("input_file_path missing in session metadata.")
        input_file_path = PROJECT_ROOT / input_file_path_rel
        
        session_dir = PROJECT_ROOT / "output" / "sessions" / session_id
        output_csv_path = session_dir / "results.csv"
        pipeline_log_path = session_dir / "pipeline.log"
        scoring_log_path = session_dir / "scoring.log"
        
        # Load context if path exists
        context_text = None
        context_file_path_rel = session_data.get("context_used_path")
        if context_file_path_rel:
            context_file_path = PROJECT_ROOT / context_file_path_rel
            if context_file_path.exists():
                try:
                    with open(context_file_path, 'r', encoding='utf-8') as cf:
                        context_text = cf.read().strip() or None
                except Exception as e_ctx:
                    session_logger.warning(f"[BG Task {session_id}] Failed to read context file {context_file_path}: {e_ctx}")
            else:
                session_logger.warning(f"[BG Task {session_id}] Context file path in metadata but file not found: {context_file_path}")

        # Update metadata with concrete paths (useful for UI later?)
        session_data['output_csv_path'] = str(output_csv_path.relative_to(PROJECT_ROOT))
        session_data['pipeline_log_path'] = str(pipeline_log_path.relative_to(PROJECT_ROOT))
        session_data['scoring_log_path'] = str(scoring_log_path.relative_to(PROJECT_ROOT))
        
    except Exception as e_path:
        session_logger.error(f"[BG Task {session_id}] Error preparing file paths: {e_path}. Aborting.")
        # Update status to error before returning
        session_data['status'] = 'error'
        session_data['error_message'] = f"Error preparing paths: {e_path}"
        save_session_metadata(all_metadata)
        return

    # --- 3. Setup Logging for this Session --- 
    try:
        # Перемещаем setup_session_logging сюда, чтобы пути были уже определены
        # Убедимся, что директория для логов сессии существует
        pipeline_log_path.parent.mkdir(parents=True, exist_ok=True)
        setup_session_logging(str(pipeline_log_path), str(scoring_log_path))
        session_logger.info(f"--- Starting Background Processing for Session: {session_id} ---")
        session_logger.info(f"Input file: {input_file_path}")
        session_logger.info(f"Context provided: {bool(context_text)}")
        session_logger.info(f"Output CSV: {output_csv_path}")
        session_logger.info(f"Pipeline Log: {pipeline_log_path}")
        session_logger.info(f"Scoring Log: {scoring_log_path}")
    except Exception as e_log:
        # Используем глобальный logger, если session_logger еще не настроен
        logging.error(f"[BG Task {session_id}] Error setting up session logging: {e_log}. Aborting.")
        session_data['status'] = 'error'
        session_data['error_message'] = f"Error setting up logging: {e_log}"
        save_session_metadata(all_metadata)
        return

    # --- 4. Update Status to Running --- 
    session_data['status'] = 'running'
    session_data['error_message'] = None # Clear previous error
    save_session_metadata(all_metadata) 

    # --- 5. Load Configs and Initialize Clients --- 
    success_count = 0
    failure_count = 0
    pipeline_error = None # Store potential error
    try:
        session_logger.info("Loading API keys and LLM config...")
        try:
            scrapingbee_api_key, openai_api_key, serper_api_key = load_env_vars()
            llm_config = load_llm_config("llm_config.yaml") 
            # ++ Загружаем конфиг для LLM Deep Search, если он будет использоваться ++
            llm_deep_search_specific_queries = []
            if run_llm_deep_search_pipeline:
                # Для примера, статический список запросов. В будущем можно вынести в конфиг.
                # Эти ключи будут использованы для формирования имен колонок.
                llm_deep_search_specific_queries = [
                    "Каков годовой доход (ARR) компании?",
                    "Сколько сотрудников работает в компании?",
                    "Каковы детали последнего раунда финансирования (сумма, дата, инвесторы)?",
                    "Какие ключевые продукты или услуги предлагает компания?",
                    "Кто основные конкуренты компании?"
                ]
                # Можно также загружать их из llm_deep_search_config.yaml, если он будет создан
                # deep_search_llm_config = load_llm_config("llm_deep_search_config.yaml")
                # llm_deep_search_specific_queries = deep_search_llm_config.get("specific_queries", [])
                session_logger.info(f"[BG Task {session_id}] LLM Deep Search specific queries: {llm_deep_search_specific_queries}")

            if not all([scrapingbee_api_key, openai_api_key, serper_api_key, llm_config]):
                raise ValueError("One or more required API keys or LLM config missing.")
        except Exception as e_conf:
            pipeline_error = f"Config/Key loading failed: {e_conf}"
            raise # Re-raise to be caught by outer try/except
            
        session_logger.info("Initializing API clients...")
        try:
            openai_client = AsyncOpenAI(api_key=openai_api_key)
            sb_client = ScrapingBeeClient(api_key=scrapingbee_api_key) 
        except Exception as e_client:
            pipeline_error = f"API Client initialization failed: {e_client}"
            raise # Re-raise
        
        # --- Определение полей CSV --- 
        base_ordered_fields = ["name", "homepage", "linkedin", "description", "timestamp"]
        additional_llm_fields = [] # Для стандартного LLM JSON вывода, если он есть
        
        # Эта часть относится к СТАНДАРТНОМУ LLM пайплайну, если он используется для JSON вывода
        if run_standard_pipeline and isinstance(llm_config.get("response_format"), dict) and \
           llm_config["response_format"].get("type") == "json_object":
            try:
                if "expected_json_keys" in llm_config: 
                    llm_keys = [f"llm_{k}" for k in llm_config["expected_json_keys"]]
                    additional_llm_fields.extend(llm_keys)
            except Exception as e_llm_keys:
                session_logger.warning(f"[BG Task {session_id}] Could not dynamically determine standard LLM output keys: {e_llm_keys}")
        
        temp_fieldnames = list(base_ordered_fields) 
        for field in additional_llm_fields:
            if field not in temp_fieldnames:
                temp_fieldnames.append(field)
        
        expected_cols = temp_fieldnames 
        session_logger.info(f"[BG Task {session_id}] Determined expected_csv_fieldnames: {expected_cols}")
        # --- Конец определения полей CSV ---

        # --- Передаем также llm_deep_search_specific_queries, если он активен ---
        # Это необходимо для src/pipeline.py -> process_company
        deep_search_config_for_pipeline = {
            "specific_queries": llm_deep_search_specific_queries
        } if run_llm_deep_search_pipeline else None

        # --- 6. Execute Pipeline --- 
        session_logger.info("Starting core pipeline execution...")
        try:
            async with aiohttp.ClientSession() as aio_session:
                success_count, failure_count, _ = await run_pipeline_for_file(
                    input_file_path=input_file_path,
                    output_csv_path=output_csv_path,
                    pipeline_log_path=str(pipeline_log_path), # Pass as string
                    scoring_log_path=str(scoring_log_path), # Pass as string
                    context_text=context_text,
                    company_col_index=0,
                    aiohttp_session=aio_session,
                    sb_client=sb_client,
                    llm_config=llm_config,
                    openai_client=openai_client,
                    serper_api_key=serper_api_key,
                    expected_csv_fieldnames=expected_cols, # <--- ПЕРЕДАЕМ ПРАВИЛЬНЫЙ СПИСОК
                    broadcast_update=broadcast_update,
                    main_batch_size=session_data.get("batch_size", 50), # Пример: берем batch_size из метаданных или по умолчанию 50
                    # ++ Передаем флаги и конфиг для LLM Deep Search ++
                    run_standard_pipeline=run_standard_pipeline,
                    run_llm_deep_search_pipeline=run_llm_deep_search_pipeline,
                    llm_deep_search_config=deep_search_config_for_pipeline
                )
            session_logger.info(f"Pipeline execution finished. Success: {success_count}, Failed: {failure_count}")
            session_data['status'] = 'completed'
            session_data['last_processed_count'] = success_count + failure_count
        except Exception as e_run:
            pipeline_error = f"Pipeline run failed: {type(e_run).__name__}: {e_run}"
            raise # Re-raise

    except Exception as e_outer_pipeline:
        # This catches errors from config loading, client init, or pipeline run
        session_logger.critical(f"CRITICAL ERROR during pipeline setup or execution for session {session_id}: {e_outer_pipeline}")
        session_logger.debug(traceback.format_exc())
        session_data['status'] = 'error'
        # Use the specific error if caught, otherwise the generic outer one
        session_data['error_message'] = pipeline_error if pipeline_error else f"{type(e_outer_pipeline).__name__}: {e_outer_pipeline}"
        # failure_count might be inaccurate here, depends where error happened
        session_data['last_processed_count'] = success_count # Only successful ones before error

    finally:
        # --- 7. Save Final Metadata --- 
        try:
            # Reload metadata *again* before saving, in case another process modified it
            # This reduces but doesn't eliminate race conditions without proper locking
            final_metadata = load_session_metadata()
            final_session_data_ptr = next((s for s in final_metadata if s.get('session_id') == session_id), None)
            if final_session_data_ptr:
                # Update only the fields changed by this task run
                final_session_data_ptr['status'] = session_data['status']
                final_session_data_ptr['error_message'] = session_data.get('error_message')
                final_session_data_ptr['last_processed_count'] = session_data.get('last_processed_count')
                # Ensure paths are stored if not already (should be from step 2)
                final_session_data_ptr['output_csv_path'] = session_data['output_csv_path']
                final_session_data_ptr['pipeline_log_path'] = session_data['pipeline_log_path']
                final_session_data_ptr['scoring_log_path'] = session_data['scoring_log_path']
            else:
                # This shouldn't happen if initial load worked, but handle defensively
                 session_logger.error(f"[BG Task {session_id}] Cannot find session in final metadata load. Appending potentially duplicate/outdated info.")
                 final_metadata.append(session_data) # Add potentially outdated info

            save_session_metadata(final_metadata)
            session_logger.info(f"Background task finished for session: {session_id}. Final status: {session_data['status']}")
        except Exception as e_save:
            session_logger.error(f"[BG Task {session_id}] CRITICAL: Failed to save final session metadata: {e_save}") 