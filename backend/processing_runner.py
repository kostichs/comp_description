import asyncio
import logging
import os
import sys
import traceback
from pathlib import Path
import ssl
import aiohttp

# Adjust sys.path to allow importing from src
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import adapter functions instead of direct pipeline calls
from src.pipeline_adapter import run_pipeline_for_file, setup_session_logging
from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR # Import session helpers
from src.config import load_env_vars, load_llm_config # Import config loaders
from openai import AsyncOpenAI
from scrapingbee import ScrapingBeeClient

async def run_session_pipeline(session_id: str, broadcast_update=None):
    """
    Runs the full data processing pipeline for a given session ID in the background.
    Updates the session metadata with status (running, completed, error).
    """
    session_logger = logging.getLogger(f"pipeline.session.{session_id}")
    session_logger.info(f"Background task started for session: {session_id}")
    
    all_metadata = [] # Инициализируем на случай ошибки на раннем этапе
    session_data = {} # Инициализируем на случай ошибки на раннем этапе
    try:
        all_metadata = load_session_metadata()
        session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
        if not session_data:
            session_logger.error(f"[BG Task {session_id}] Session metadata not found. Aborting.")
            return

        run_standard_pipeline = session_data.get("run_standard_pipeline", True)
        run_llm_deep_search_pipeline = session_data.get("run_llm_deep_search_pipeline", True)
        session_logger.info(f"[BG Task {session_id}] Standard pipeline: {run_standard_pipeline}, LLM Deep Search: {run_llm_deep_search_pipeline}")

    except Exception as e:
        session_logger.error(f"[BG Task {session_id}] Error loading session metadata: {e}. Aborting.")
        return
        
    try:
        input_file_path_rel = session_data.get("input_file_path")
        if not input_file_path_rel:
            raise ValueError("input_file_path missing in session metadata.")
        input_file_path = PROJECT_ROOT / input_file_path_rel
        
        session_dir = PROJECT_ROOT / "output" / "sessions" / session_id
        output_csv_path = session_dir / f"{session_id}_results.csv"
        pipeline_log_path = session_dir / "pipeline.log" # Только один файл лога
        # scoring_log_path = session_dir / "scoring.log" # Удаляем scoring_log_path
        
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

        session_data['output_csv_path'] = str(output_csv_path.relative_to(PROJECT_ROOT))
        session_data['pipeline_log_path'] = str(pipeline_log_path.relative_to(PROJECT_ROOT))
        # session_data['scoring_log_path'] = str(scoring_log_path.relative_to(PROJECT_ROOT)) # Удаляем из метаданных
        
    except Exception as e_path:
        session_logger.error(f"[BG Task {session_id}] Error preparing file paths: {e_path}. Aborting.")
        session_data['status'] = 'error'
        session_data['error_message'] = f"Error preparing paths: {e_path}"
        if all_metadata: save_session_metadata(all_metadata)
        return

    try:
        pipeline_log_path.parent.mkdir(parents=True, exist_ok=True)
        setup_session_logging(str(pipeline_log_path)) # Передаем только pipeline_log_path
        session_logger.info(f"--- Starting Background Processing for Session: {session_id} ---")
        session_logger.info(f"Input file: {input_file_path}")
        session_logger.info(f"Context provided: {bool(context_text)}")
        session_logger.info(f"Output CSV: {output_csv_path}")
        session_logger.info(f"Pipeline Log: {pipeline_log_path}")
        # session_logger.info(f"Scoring Log: {scoring_log_path}") # Удаляем из логов
    except Exception as e_log:
        logging.error(f"[BG Task {session_id}] Error setting up session logging: {e_log}. Aborting.")
        session_data['status'] = 'error'
        session_data['error_message'] = f"Error setting up logging: {e_log}"
        if all_metadata: save_session_metadata(all_metadata)
        return

    session_data['status'] = 'running'
    session_data['error_message'] = None 
    save_session_metadata(all_metadata) 

    success_count = 0
    failure_count = 0
    pipeline_error = None
    try:
        session_logger.info("Loading API keys and LLM config...")
        try:
            scrapingbee_api_key, openai_api_key, serper_api_key = load_env_vars()
            llm_config = load_llm_config("llm_config.yaml") 
            
            # llm_deep_search_specific_aspects больше не используется здесь напрямую
            # Эта логика перенесена внутрь pipeline_adapter или будет браться из llm_config

            if not all([scrapingbee_api_key, openai_api_key, serper_api_key, llm_config]):
                raise ValueError("One or more required API keys or LLM config missing.")
        except Exception as e_conf:
            pipeline_error = f"Config/Key loading failed: {e_conf}"
            raise 
            
        session_logger.info("Initializing API clients...")
        try:
            openai_client = AsyncOpenAI(api_key=openai_api_key)
            sb_client = ScrapingBeeClient(api_key=scrapingbee_api_key) 
        except Exception as e_client:
            pipeline_error = f"API Client initialization failed: {e_client}"
            raise 
        
        base_ordered_fields = ["name", "homepage", "linkedin", "description", "timestamp"]
        # additional_llm_fields больше не актуальны в таком виде, если CSV стандартизирован
        expected_cols = list(base_ordered_fields) 
        session_logger.info(f"[BG Task {session_id}] Determined expected_csv_fieldnames: {expected_cols}")
        
        # deep_search_config_for_pipeline больше не формируется и не передается здесь

        session_logger.info("Starting core pipeline execution...")
        try:
            # Создаем SSL контекст, который не проверяет сертификаты
            ssl_context_no_verify = ssl.create_default_context()
            ssl_context_no_verify.check_hostname = False
            ssl_context_no_verify.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context_no_verify)
            
            async with aiohttp.ClientSession(connector=connector) as aio_session:
                success_count, failure_count, all_results = await run_pipeline_for_file(
                    input_file_path=input_file_path,
                    output_csv_path=output_csv_path,
                    pipeline_log_path=str(pipeline_log_path), 
                    # scoring_log_path=str(scoring_log_path), # Удален
                    session_dir_path=session_dir,
                    context_text=context_text,
                    company_col_index=0,
                    aiohttp_session=aio_session,
                    sb_client=sb_client,
                    llm_config=llm_config, # Передаем полный llm_config
                    openai_client=openai_client,
                    serper_api_key=serper_api_key,
                    expected_csv_fieldnames=expected_cols, 
                    broadcast_update=broadcast_update,
                    main_batch_size=10,
                    run_standard_pipeline=run_standard_pipeline,
                    run_llm_deep_search_pipeline=run_llm_deep_search_pipeline
                    # llm_deep_search_config=None # Удален, т.к. не принимается функцией
                )
                
                session_logger.info(f"Pipeline completed with {success_count} successes and {failure_count} failures.")
                
        except Exception as e_pipeline:
            session_logger.error(f"Pipeline execution error: {e_pipeline}", exc_info=True)
            pipeline_error = f"Pipeline execution failed: {e_pipeline}"
            raise

    except Exception as e_outer:
        session_logger.error(f"Error during processing: {e_outer}", exc_info=True)
        session_data['status'] = 'error'
        session_data['error_message'] = pipeline_error or f"Processing error: {e_outer}"
        failure_count = 1 
        success_count = 0 
    else:
        session_data['status'] = 'completed'
        session_data['processed_count'] = success_count
        session_data['error_count'] = failure_count
        session_data['error_message'] = None if failure_count == 0 else f"Completed with {failure_count} errors"

    finally:
        session_data['processed_count'] = success_count
        session_data['error_count'] = failure_count
        session_data['completion_time'] = asyncio.get_running_loop().time()
        if all_metadata: save_session_metadata(all_metadata)
        
        status_message = session_data.get('status', 'unknown')
        error_message = session_data.get('error_message', '')
        session_logger.info(f"Background task ended for session: {session_id} - Status: {status_message}{' - ' + error_message if error_message else ''}")
        
        if broadcast_update:
            await broadcast_update({
                "type": "session_status",
                "session_id": session_id,
                "status": status_message,
                "error_message": error_message or None,
                "success_count": success_count,
                "failure_count": failure_count
            }) 