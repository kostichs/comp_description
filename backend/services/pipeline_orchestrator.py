"""
Universal Pipeline Orchestrator

This is the main orchestrator for running any type of pipeline in the system.
It coordinates between:
- Session management
- Configuration loading  
- Pipeline execution
- Error handling and status updates

Supports multiple pipeline types through the pipeline adapter pattern.
"""

import asyncio
import logging
import aiohttp
from pathlib import Path

from src.pipeline import get_pipeline_adapter
from .config_loader import ConfigLoader
from .session_manager import SessionManager

# Project root path
PROJECT_ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)

async def run_session_pipeline(session_id: str, broadcast_update=None):
    """
    Universal pipeline orchestrator for any session type.
    
    This function:
    1. Loads session metadata and configuration
    2. Sets up logging and file paths
    3. Initializes the appropriate pipeline adapter
    4. Executes the pipeline
    5. Handles status updates and error reporting
    
    Args:
        session_id: Unique session identifier
        broadcast_update: Optional callback for real-time updates
    """
    session_logger = logging.getLogger(f"pipeline.session.{session_id}")
    session_logger.info(f"Background task started for session: {session_id}")
    
    # Initialize managers
    session_manager = SessionManager(session_id, PROJECT_ROOT)
    config_loader = ConfigLoader()
    
    success_count = 0
    failure_count = 0
    pipeline_error = None
    
    try:
        # Step 1: Load session data
        session_logger.info("Loading session metadata...")
        session_data = await session_manager.load_session_data()
        
        run_llm_deep_search_pipeline = session_data.get("run_llm_deep_search_pipeline", True)
        write_to_hubspot = session_data.get("write_to_hubspot", True)
        session_logger.info(f"Pipeline settings - LLM Deep Search: {run_llm_deep_search_pipeline}, Write to HubSpot: {write_to_hubspot}")
        
        # Step 2: Prepare file paths
        session_logger.info("Preparing file paths...")
        paths = session_manager.prepare_file_paths()
        
        # Step 3: Setup logging
        session_logger.info("Setting up session logging...")
        session_logger = session_manager.setup_logging(paths['pipeline_log_path'])
        
        # Step 4: Update status to running
        session_manager.update_status('running')
        
        # Step 5: Load configuration and initialize clients
        session_logger.info("Loading configuration and API keys...")
        await config_loader.load_config("llm_config.yaml")
        await config_loader.initialize_clients()
        
        # Step 6: Execute pipeline
        session_logger.info("Starting pipeline execution...")
        success_count, failure_count = await _execute_pipeline(
            session_logger=session_logger,
            session_data=session_data,
            paths=paths,
            config_loader=config_loader,
            write_to_hubspot=write_to_hubspot
        )
        
        session_logger.info(f"Pipeline completed with {success_count} successes and {failure_count} failures.")
        
    except asyncio.CancelledError:
        session_logger.info(f"Processing was cancelled for session: {session_id}")
        session_manager.finalize_session('cancelled', 0, 0, 'Processing cancelled by user')
        raise  # Re-raise for proper handling in callback
        
    except Exception as e_outer:
        session_logger.error(f"Error during processing: {e_outer}", exc_info=True)
        pipeline_error = f"Processing error: {e_outer}"
        session_manager.finalize_session('error', 0, 1, pipeline_error)
        failure_count = 1
        success_count = 0
        
    else:
        # Success case
        error_message = None if failure_count == 0 else f"Completed with {failure_count} errors"
        final_session_data = session_manager.finalize_session('completed', success_count, failure_count, error_message)
        
    finally:
        # Send final broadcast update
        if broadcast_update:
            final_status = session_manager.session_data.get('status', 'unknown') if hasattr(session_manager, 'session_data') else 'error'
            final_error = session_manager.session_data.get('error_message') if hasattr(session_manager, 'session_data') else pipeline_error
            
            await broadcast_update({
                "type": "session_status",
                "session_id": session_id,
                "status": final_status,
                "error_message": final_error,
                "success_count": success_count,
                "failure_count": failure_count
            })
        
        session_logger.info(f"Background task ended for session: {session_id}")


async def _execute_pipeline(session_logger, session_data, paths, config_loader, write_to_hubspot):
    """
    Execute the actual pipeline with proper resource management.
    
    This is separated to ensure proper cleanup of aiohttp session.
    """
    # Define expected CSV fields
    base_ordered_fields = ["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp", "HubSpot_Company_ID", "Predator_ID"]
    expected_cols = list(base_ordered_fields)
    session_logger.info(f"Expected CSV fieldnames: {expected_cols}")
    
    # Create aiohttp connector with appropriate limits
    connector = aiohttp.TCPConnector(
        limit=50,
        limit_per_host=10,
        ttl_dns_cache=300,
        use_dns_cache=True,
        keepalive_timeout=30,
        enable_cleanup_closed=True
    )
    
    async with aiohttp.ClientSession(connector=connector) as aio_session:
        # Get appropriate pipeline adapter
        pipeline_adapter = get_pipeline_adapter(
            config_path="llm_config.yaml",
            input_file=paths['input_file_path'],
            session_id=session_data.get('session_id')
        )
        
        # Configure pipeline adapter
        pipeline_adapter.openai_client = config_loader.openai_client
        pipeline_adapter.sb_client = config_loader.sb_client
        pipeline_adapter.aiohttp_session = aio_session
        pipeline_adapter.llm_config = config_loader.llm_config
        pipeline_adapter.api_keys = config_loader.get_api_keys_dict()
        
        # Set pipeline-specific attributes
        pipeline_adapter.output_csv_path = paths['output_csv_path']
        pipeline_adapter.pipeline_log_path = paths['pipeline_log_path']
        pipeline_adapter.company_col_index = 0  # Default company column index
        
        # Set description-specific flag if adapter supports it
        if hasattr(pipeline_adapter, 'use_raw_llm_data_as_description'):
            pipeline_adapter.use_raw_llm_data_as_description = True
        
        # Setup pipeline adapter
        await pipeline_adapter.setup()
        
        # Execute pipeline
        success_count, failure_count, all_results = await pipeline_adapter.run(
            expected_csv_fieldnames=expected_cols,
            write_to_hubspot=write_to_hubspot
        )
        
        return success_count, failure_count 