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
    session_logger = logging.getLogger(f"pipeline.session.{session_id}") # Get or create session-specific logger
    session_logger.info(f"Background task started for session: {session_id}")
    
    # --- 1. Load Session Metadata --- 
    try:
        all_metadata = load_session_metadata()
        session_data = next((s for s in all_metadata if s.get('session_id') == session_id), None)
        if not session_data:
            session_logger.error(f"[BG Task {session_id}] Session metadata not found. Aborting.")
            return # Cannot proceed without metadata

        # ++ Read pipeline selection flags from metadata ++
        run_standard_pipeline = session_data.get("run_standard_pipeline", True) # Default to True
        run_llm_deep_search_pipeline = session_data.get("run_llm_deep_search_pipeline", True) # Default to True
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
        output_csv_path = session_dir / f"{session_id}_results.csv"
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
        # Move setup_session_logging here so paths are already defined
        # Ensure session log directory exists
        pipeline_log_path.parent.mkdir(parents=True, exist_ok=True)
        setup_session_logging(str(pipeline_log_path), str(scoring_log_path))
        session_logger.info(f"--- Starting Background Processing for Session: {session_id} ---")
        session_logger.info(f"Input file: {input_file_path}")
        session_logger.info(f"Context provided: {bool(context_text)}")
        session_logger.info(f"Output CSV: {output_csv_path}")
        session_logger.info(f"Pipeline Log: {pipeline_log_path}")
        session_logger.info(f"Scoring Log: {scoring_log_path}")
    except Exception as e_log:
        # Use global logger if session_logger is not yet configured
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
            
            llm_deep_search_specific_aspects = [] # Renamed for clarity
            if run_llm_deep_search_pipeline:
                # Updated list of specific aspects in English, including more foundational queries
                llm_deep_search_specific_aspects = [
                    "company founding year",
                    "headquarters location (city and country)",
                    "names of founders",
                    "ownership structure (e.g., public, private, VC-backed, parent company)",
                    "latest reported annual revenue or ARR (specify currency and year if possible)",
                    "approximate number of employees",
                    "details of the latest funding round (amount, date, key investors, series - if applicable)",
                    "key products, services, or core technologies offered",
                    "main competitors identified by reliable sources",
                    "primary business segments and target customer focus (e.g., B2C, B2B, B2G)",
                    "geographical regions of operation and overall global strategy",
                    "overview of pricing models or typical engagement costs for key offerings, if publicly available or inferable",
                    "solutions or services related to connectivity, cloud, AI, security, and IoT",
                    "recent significant company news, product launches, or M&A activities (last 12-18 months)"
                ]
                session_logger.info(f"[BG Task {session_id}] LLM Deep Search specific aspects for comprehensive report: {llm_deep_search_specific_aspects}")

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
        
        # --- Define CSV fields --- 
        base_ordered_fields = ["name", "homepage", "linkedin", "description", "timestamp"]
        additional_llm_fields = [] # For standard LLM JSON output, if any
        
        # This part relates to the STANDARD LLM pipeline if it's used for JSON output
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
        # --- End CSV field definition ---

        # --- Pass llm_deep_search_specific_aspects if active ---
        deep_search_config_for_pipeline = {
            "specific_queries": llm_deep_search_specific_aspects # Ensure this key matches what pipeline.py expects
        } if run_llm_deep_search_pipeline and llm_deep_search_specific_aspects else None

        # --- 6. Execute Pipeline --- 
        session_logger.info("Starting core pipeline execution...")
        try:
            async with aiohttp.ClientSession() as aio_session:
                success_count, failure_count, _ = await run_pipeline_for_file(
                    input_file_path=input_file_path,
                    output_csv_path=output_csv_path,
                    pipeline_log_path=str(pipeline_log_path), 
                    scoring_log_path=str(scoring_log_path), 
                    session_dir_path=session_dir,
                    context_text=context_text,
                    company_col_index=0,
                    aiohttp_session=aio_session,
                    sb_client=sb_client,
                    llm_config=llm_config,
                    openai_client=openai_client,
                    serper_api_key=serper_api_key,
                    expected_csv_fieldnames=expected_cols, 
                    broadcast_update=broadcast_update,
                    main_batch_size=10,
                    run_standard_pipeline=run_standard_pipeline,
                    run_llm_deep_search_pipeline=run_llm_deep_search_pipeline,
                    llm_deep_search_config=deep_search_config_for_pipeline # This now contains the updated aspects
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