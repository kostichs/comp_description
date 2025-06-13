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

# Обновленные импорты для новой структуры
from src.pipeline import get_pipeline_adapter # Импортируем get_pipeline_adapter
from src.pipeline.utils.logging import setup_session_logging
from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR # Import session helpers
from src.config import load_env_vars, load_llm_config # Import config loaders
from openai import AsyncOpenAI
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient

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

        run_llm_deep_search_pipeline = session_data.get("run_llm_deep_search_pipeline", True)
        write_to_hubspot = session_data.get("write_to_hubspot", True)
        session_logger.info(f"[BG Task {session_id}] LLM Deep Search pipeline: {run_llm_deep_search_pipeline}, Write to HubSpot: {write_to_hubspot}")

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
            # Исправленная распаковка - теперь получаем 4 значения, включая hubspot_api_key
            scrapingbee_api_key, openai_api_key, serper_api_key, hubspot_api_key = load_env_vars()
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
            sb_client = CustomScrapingBeeClient(api_key=scrapingbee_api_key) 
        except Exception as e_client:
            pipeline_error = f"API Client initialization failed: {e_client}"
            raise 
        
        # Формируем список полей для CSV
        base_ordered_fields = ["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp", "HubSpot_Company_ID", "Predator_ID"]
        # Добавляем поля валидации в базовый список
        expected_cols = list(base_ordered_fields)
        session_logger.info(f"[BG Task {session_id}] Determined expected_csv_fieldnames: {expected_cols}")
        
        # deep_search_config_for_pipeline больше не формируется и не передается здесь

        session_logger.info("Starting core pipeline execution...")
        try:
            # Создаем коннектор с обычными ограничениями для основного pipeline
            connector = aiohttp.TCPConnector(
                limit=50,  # Обычное количество соединений для основного pipeline
                limit_per_host=10,  # Обычное количество соединений на хост
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            
            async with aiohttp.ClientSession(connector=connector) as aio_session:
                # Используем get_pipeline_adapter для получения нужного адаптера
                pipeline_adapter = get_pipeline_adapter(
                    config_path="llm_config.yaml", 
                    input_file=input_file_path,
                    session_id=session_id, # session_id уже передается
                    # use_hubspot будет определен внутри get_pipeline_adapter на основе llm_config.yaml
                )
                
                # Настраиваем адаптер (большинство настроек должно происходить в setup() адаптера)
                # pipeline_adapter.company_col_index = 0 # Это может быть установлено в PipelineAdapter.setup()
                # pipeline_adapter.output_csv_path = output_csv_path # Это может быть установлено в PipelineAdapter.setup()
                # pipeline_adapter.pipeline_log_path = Path(str(pipeline_log_path)) # Это может быть установлено в PipelineAdapter.setup()
                
                # Инициализируем клиентов и передаем api_keys. Это должно быть частью setup() адаптера.
                # Если PipelineAdapter.setup() или HubSpotPipelineAdapter.setup() этого не делают, нужно будет доработать там.
                # Пока оставляем здесь, чтобы не сломать существующую логику, но это кандидаты на перенос в setup() соответствующего адаптера.
                pipeline_adapter.openai_client = openai_client
                pipeline_adapter.sb_client = sb_client
                pipeline_adapter.aiohttp_session = aio_session
                pipeline_adapter.llm_config = llm_config # llm_config уже загружается в setup адаптера из config_path
                pipeline_adapter.api_keys = {
                    "openai": openai_api_key,
                    "serper": serper_api_key,
                    "scrapingbee": scrapingbee_api_key,
                    "hubspot": hubspot_api_key
                }
                # use_raw_llm_data_as_description также должен быть параметром llm_config или конструктора адаптера
                # Пока что, если этот флаг важен, его нужно будет установить после получения pipeline_adapter
                # Например: pipeline_adapter.use_raw_llm_data_as_description = True (если это свойство адаптера)
                # В HubSpotPipelineAdapter это есть, в базовом PipelineAdapter нужно проверить.
                # Если PipelineAdapter его не имеет, то нужно будет выставлять только для HubSpotPipelineAdapter, например:
                if hasattr(pipeline_adapter, 'use_raw_llm_data_as_description'):
                    pipeline_adapter.use_raw_llm_data_as_description = True 

                # Перед вызовом run(), вызываем setup() для инициализации всего, включая HubSpotAdapter, если он используется.
                await pipeline_adapter.setup() 
                
                # Передаем output_csv_path, pipeline_log_path и company_col_index в метод run
                # или убеждаемся, что они устанавливаются в setup() из session_data или других источников.
                # Для run() из HubSpotPipelineAdapter эти параметры не принимаются напрямую.
                # Он ожидает, что они будут установлены как атрибуты экземпляра в setup().

                # Передаем необходимые параметры в run(), если они не являются частью setup
                # Это потребует ревизии метода run() в PipelineAdapter и HubSpotPipelineAdapter
                # Пока что, если эти параметры нужны в run, они должны быть частью его сигнатуры.

                # output_csv_path, pipeline_log_path, и company_col_index уже должны быть доступны 
                # адаптеру через его атрибуты, установленные в setup() или при инициализации,
                # если они берутся из session_data (например, input_file_path -> output_csv_path).

                pipeline_adapter.output_csv_path = output_csv_path
                pipeline_adapter.pipeline_log_path = pipeline_log_path
                pipeline_adapter.company_col_index = 0 # Предполагаем, что это всегда 0 по умолчанию

                # Запускаем пайплайн
                success_count, failure_count, all_results = await pipeline_adapter.run(
                    # Параметры, которые run может все еще ожидать:
                    # run_standard_pipeline=run_standard_pipeline, # Эти флаги из session_data
                    # run_llm_deep_search_pipeline=run_llm_deep_search_pipeline
                    # broadcast_update=broadcast_update # callback
                    # main_batch_size # из параметров функции run_session_pipeline
                    # context_text # из session_data
                    expected_csv_fieldnames = expected_cols, # <--- Передаем наш список полей
                    write_to_hubspot = write_to_hubspot # <--- Передаем флаг записи в HubSpot
                    # aiohttp_session, sb_client, openai_client - уже установлены как атрибуты
                    # llm_config, api_keys - уже установлены как атрибуты
                )
                
                session_logger.info(f"Pipeline completed with {success_count} successes and {failure_count} failures.")
                
        except Exception as e_pipeline:
            session_logger.error(f"Pipeline execution error: {e_pipeline}", exc_info=True)
            pipeline_error = f"Pipeline execution failed: {e_pipeline}"
            raise

    except asyncio.CancelledError:
        session_logger.info(f"Processing was cancelled for session: {session_id}")
        session_data['status'] = 'cancelled'
        session_data['error_message'] = 'Processing cancelled by user'
        failure_count = 0
        success_count = 0
        raise  # Перебрасываем CancelledError для правильной обработки в callback
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
        # Перезагружаем метаданные ПЕРЕД финальным сохранением,
        # чтобы учесть изменения от других модулей (например, normalize_urls)
        current_all_metadata = load_session_metadata()
        final_session_data_idx = -1
        # Используем локальный session_data для получения статуса, который был определен в try/except/else выше
        determined_status = session_data.get('status', 'unknown') 
        determined_error_message = session_data.get('error_message')

        for idx, meta_item in enumerate(current_all_metadata):
            if meta_item.get("session_id") == session_id:
                final_session_data_idx = idx
                break
        
        status_to_log = 'unknown' # Для лога в конце
        error_msg_to_log = ''    # Для лога в конце

        if final_session_data_idx != -1:
            # Обновляем только те поля, за которые отвечает этот runner
            current_all_metadata[final_session_data_idx]['status'] = determined_status
            current_all_metadata[final_session_data_idx]['processed_count'] = success_count
            current_all_metadata[final_session_data_idx]['error_count'] = failure_count
            current_all_metadata[final_session_data_idx]['error_message'] = determined_error_message
            current_all_metadata[final_session_data_idx]['completion_time'] = asyncio.get_running_loop().time()
            
            save_session_metadata(current_all_metadata)
            
            status_to_log = current_all_metadata[final_session_data_idx].get('status', 'unknown')
            error_msg_to_log = current_all_metadata[final_session_data_idx].get('error_message', '')
        else:
            session_logger.error(f"[BG Task {session_id}] Session metadata not found in list during final save. This is unexpected.")
            # Если сессии нет в списке, то и сохранять нечего, но нужно залогировать и для broadcast_update
            status_to_log = 'error' 
            error_msg_to_log = 'Session data not found in metadata list for final update'

        session_logger.info(f"Background task ended for session: {session_id} - Status: {status_to_log}{' - ' + error_msg_to_log if error_msg_to_log else ''}")
        
        if broadcast_update:
            await broadcast_update({
                "type": "session_status",
                "session_id": session_id,
                "status": status_to_log, # Используем статус из сохраненных/определенных данных
                "error_message": error_msg_to_log or None,
                "success_count": success_count,
                "failure_count": failure_count
            }) 