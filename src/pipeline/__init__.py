"""
Pipeline package for company description generation

This package provides the API for generating company descriptions
using various data sources and integrations.
"""

import logging
import os
from src.pipeline.adapter import PipelineAdapter
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import HubSpot adapter
try:
    from src.integrations.hubspot.adapter import HubSpotPipelineAdapter
    HUBSPOT_AVAILABLE = True
    logger.info("HubSpot integration available and HubSpotPipelineAdapter imported successfully.")
except ImportError as e:
    HUBSPOT_AVAILABLE = False
    logger.warning(f"HubSpot integration not available due to import error: {e}")

def get_pipeline_adapter(config_path: str = "llm_config.yaml", input_file=None, use_hubspot: bool = None, session_id: Optional[str] = None):
    """
    Get the appropriate pipeline adapter based on configuration
    
    Args:
        config_path: Path to the LLM configuration file
        input_file: Path to the input file with company names
        use_hubspot: Override whether to use HubSpot integration
        session_id: Optional session ID to pass to the adapter
        
    Returns:
        PipelineAdapter: The appropriate pipeline adapter
    """
    should_use_hubspot_final = False

    if use_hubspot is not None:
        should_use_hubspot_final = use_hubspot
        logger.info(f"HubSpot usage explicitly set to: {should_use_hubspot_final}")
    else:
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                should_use_hubspot_from_config = config.get("use_hubspot_integration", False)
                logger.info(f"HubSpot usage from llm_config.yaml (use_hubspot_integration): {should_use_hubspot_from_config}")
                should_use_hubspot_final = should_use_hubspot_from_config
        except Exception as e_yaml:
            logger.warning(f"Could not load or parse llm_config.yaml to check HubSpot usage: {e_yaml}. Checking HUBSPOT_API_KEY environment variable.")
            if bool(os.getenv("HUBSPOT_API_KEY")):
                logger.info("HUBSPOT_API_KEY is set in environment.")
            else:
                logger.info("HUBSPOT_API_KEY is NOT set in environment.")
            should_use_hubspot_final = False
            logger.info(f"Defaulting HubSpot usage to {should_use_hubspot_final} due to config read issue and no explicit override.")

    logger.info(f"Final decision for should_use_hubspot: {should_use_hubspot_final}, HUBSPOT_AVAILABLE by import: {HUBSPOT_AVAILABLE}")

    if should_use_hubspot_final and HUBSPOT_AVAILABLE:
        logger.info("Attempting to use HubSpotPipelineAdapter.")
        return HubSpotPipelineAdapter(config_path=config_path, input_file=input_file, session_id=session_id)
    else:
        if should_use_hubspot_final and not HUBSPOT_AVAILABLE:
            logger.warning("HubSpot integration was requested (should_use_hubspot_final=True), but it's not available (HUBSPOT_AVAILABLE=False due to import issues). Falling back to base PipelineAdapter.")
        elif not should_use_hubspot_final:
            logger.info("HubSpot integration is not requested (should_use_hubspot_final=False). Using base PipelineAdapter.")
        else:
            logger.info("HubSpot integration is not available and not requested. Using base PipelineAdapter.")
        return PipelineAdapter(config_path=config_path, input_file=input_file, session_id=session_id)

# Convenience function for direct use
async def run_pipeline(config_path: str = "llm_config.yaml", input_file = None, use_hubspot: bool = None, session_id: Optional[str] = None):
    """
    Run the pipeline with given settings
    
    This is the main entry point for the pipeline, used from command line 
    or when no customization is needed.
    
    Args:
        config_path: Path to the LLM configuration file
        input_file: Path to the input file with company names
        use_hubspot: Whether to use HubSpot integration
        session_id: Optional session ID
        
    Returns:
        Tuple with success count, failure count, and results
    """
    adapter = get_pipeline_adapter(config_path, input_file, use_hubspot, session_id=session_id)
    return await adapter.run()

__all__ = ['PipelineAdapter', 'HubSpotPipelineAdapter', 'run_pipeline', 'get_pipeline_adapter'] 