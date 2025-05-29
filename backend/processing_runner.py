import asyncio
import logging
import os
import sys
import traceback
from pathlib import Path
import ssl
import aiohttp
import yaml
import time
from dotenv import load_dotenv

# Adjust sys.path to allow importing from src
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Обновленные импорты для новой структуры
from src.pipeline import get_pipeline_adapter # Import get_pipeline_adapter
from src.pipeline.utils.logging import setup_session_logging
from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR # Import session helpers
from src.config import load_env_vars, load_llm_config # Import config loaders
from openai import AsyncOpenAI
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient

async def run_session_pipeline(session_id: str, broadcast_update=None):
    """
    Executes the full pipeline for a session (asynchronously). This includes both standard and LLM Deep Search modes.
    """
    session_logger = logging.getLogger(f"session_{session_id}")
    session_logger.info(f"[BG Task {session_id}] Starting pipeline execution...")

    # Initialize in case of early stage error
    all_metadata = [] # Initialize in case of early stage error
    session_data = {} # Initialize in case of early stage error

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
    
    # Try to get file paths from metadata
    try:
        input_file_path_str = session_data.get('input_file_path')
        if not input_file_path_str:
            session_logger.error(f"[BG Task {session_id}] No input file path in metadata")
            return

        session_logger.info(f"[BG Task {session_id}] Using input file: {input_file_path_str}")
        session_logger.info(f"[BG Task {session_id}] Session data: {session_data}")
        
        # Calculate absolute paths
        input_file_path = PROJECT_ROOT / input_file_path_str
        output_csv_path = PROJECT_ROOT / "output" / "sessions" / session_id / f"results_{session_id}.csv"
        pipeline_log_path = PROJECT_ROOT / "output" / "sessions" / session_id / f"pipeline_{session_id}.log"
        scoring_log_path = PROJECT_ROOT / "output" / "sessions" / session_id / f"scoring_{session_id}.log"

        context_text = None
        context_path = session_data.get('context_used_path')
        if context_path:
            context_file_path = PROJECT_ROOT / context_path
            if context_file_path.exists():
                try:
                    with open(context_file_path, 'r', encoding='utf-8') as f:
                        context_text = f.read()
                    session_logger.info(f"[BG Task {session_id}] Loaded context text from {context_file_path}")
                except Exception as e:
                    session_logger.error(f"[BG Task {session_id}] Error reading context file: {e}")
            else:
                session_logger.warning(f"[BG Task {session_id}] Context file not found: {context_file_path}")

        # Load configuration
        llm_config_path = Path("llm_config.yaml")
        if llm_config_path.exists():
            with open(llm_config_path, 'r', encoding='utf-8') as f:
                llm_config = yaml.safe_load(f)
        else:
            session_logger.warning(f"[BG Task {session_id}] Config file {llm_config_path} not found. Using default config.")
            llm_config = {}

        # Update session metadata: processing
        session_data['status'] = 'processing'
        save_session_metadata(all_metadata)

        if broadcast_update:
            await broadcast_update({
                "type": "status_update",
                "session_id": session_id,
                "status": "processing",
                "message": "Starting processing..."
            })
        
    except Exception as e:
        session_logger.error(f"[BG Task {session_id}] Error during initialization: {e}")
        # Update metadata: error status
        try:
            session_data['status'] = 'error'
            session_data['error_message'] = f"Initialization error: {str(e)}"
            save_session_metadata(all_metadata)
        except Exception:
            pass
        return

    # Now execute the pipeline
    try:
        session_logger.info(f"[BG Task {session_id}] Starting pipeline execution...")
        
        # OPTION 1: Direct adapter usage
        if run_llm_deep_search_pipeline or write_to_hubspot:
            from src.integrations.hubspot.adapter import HubSpotPipelineAdapter
            adapter = HubSpotPipelineAdapter(
                config_path="llm_config.yaml",
                input_file=str(input_file_path),
                session_id=session_id
            )
        else:
            from src.pipeline.adapter import PipelineAdapter
            adapter = PipelineAdapter(
                config_path="llm_config.yaml",
                input_file=str(input_file_path), 
                session_id=session_id
            )

        adapter.output_csv_path = output_csv_path
        adapter.pipeline_log_path = pipeline_log_path
        if hasattr(adapter, "scoring_log_path"):
            adapter.scoring_log_path = scoring_log_path

        session_logger.info(f"[BG Task {session_id}] Adapter created, calling setup()...")

        # Adapter setup
        await adapter.setup()

        # Add runtime configuration for the current session
        adapter.use_llm_deep_search = run_llm_deep_search_pipeline
        if hasattr(adapter, 'use_hubspot'): adapter.use_hubspot = write_to_hubspot

        session_logger.info(f"[BG Task {session_id}] Starting adapter.run()...")

        # OPTION 2: Direct function call if needed
        # await execute_pipeline_for_session_async(
        #     session_id, input_file_path, output_csv_path, pipeline_log_path, scoring_log_path, context_text, llm_config
        # )
        
        # Initialize clients and pass api_keys. This should be part of adapter's setup()
        load_dotenv()  # Load environment variables
        api_keys = {
            "openai": os.getenv("OPENAI_API_KEY"),
            "serper": os.getenv("SERPER_API_KEY"),
            "scrapingbee": os.getenv("SCRAPINGBEE_API_KEY")
        }
        
        if not api_keys["openai"]:
            raise Exception("OPENAI_API_KEY not found in environment variables")
        if not api_keys["serper"]:
            raise Exception("SERPER_API_KEY not found in environment variables")
        if not api_keys["scrapingbee"]:
            raise Exception("SCRAPINGBEE_API_KEY not found in environment variables")

        session_logger.info(f"[BG Task {session_id}] API keys loaded successfully")

        # Create output directory if it doesn't exist
        output_csv_path.parent.mkdir(parents=True, exist_ok=True)

        # Before calling run(), call setup() to initialize everything, including HubSpotAdapter if used.
        # await adapter.setup() # Already called above

        session_logger.info(f"[BG Task {session_id}] All setup completed, running pipeline...")

        # Pass context text and all other configuration to adapter if needed.
        # The adapter should get all the information it needs through its attributes, set in setup() or during initialization,
        # including session_id, use_llm_deep_search, use_hubspot, etc.
        await adapter.run()

        session_logger.info(f"[BG Task {session_id}] Pipeline completed successfully")

        # Update session metadata
        session_data['status'] = 'completed'
        session_data['output_csv_path'] = str(output_csv_path.relative_to(PROJECT_ROOT))
        session_data['pipeline_log_path'] = str(pipeline_log_path.relative_to(PROJECT_ROOT))
        session_data['scoring_log_path'] = str(scoring_log_path.relative_to(PROJECT_ROOT))
        session_data['timestamp_completed'] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_session_metadata(all_metadata)

        if broadcast_update:
            await broadcast_update({
                "type": "processing_complete",
                "session_id": session_id,
                "status": "completed",
                "message": "Processing completed successfully"
            })

    except Exception as e:
        session_logger.error(f"[BG Task {session_id}] Error during pipeline execution: {e}", exc_info=True)
        session_data['status'] = 'error'
        session_data['error_message'] = str(e)
        session_data['timestamp_completed'] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_session_metadata(all_metadata)

        if broadcast_update:
            await broadcast_update({
                "type": "processing_error",
                "session_id": session_id,
                "status": "error",
                "message": f"Processing failed: {str(e)}"
            })

    session_logger.info(f"[BG Task {session_id}] Pipeline execution finished") 