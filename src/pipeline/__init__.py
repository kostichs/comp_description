"""
Pipeline package for company description generation

This package provides the API for generating company descriptions
using various data sources and integrations.
"""

import logging
import os
from src.pipeline.adapter import PipelineAdapter

logger = logging.getLogger(__name__)

# Try to import HubSpot adapter
try:
    from src.integrations.hubspot.adapter import HubSpotPipelineAdapter
    HUBSPOT_AVAILABLE = True
except ImportError:
    HUBSPOT_AVAILABLE = False
    logger.warning("HubSpot integration not available")

def get_pipeline_adapter(config_path: str = "llm_config.yaml", input_file=None, use_hubspot: bool = None):
    """
    Get the appropriate pipeline adapter based on configuration
    
    Args:
        config_path: Path to the LLM configuration file
        input_file: Path to the input file with company names
        use_hubspot: Override whether to use HubSpot integration
        
    Returns:
        PipelineAdapter: The appropriate pipeline adapter
    """
    # Determine if HubSpot should be used
    should_use_hubspot = use_hubspot
    
    if should_use_hubspot is None:
        # Try to read from config or environment
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                should_use_hubspot = config.get("use_hubspot_integration", False)
        except Exception:
            # If config not available, check for API key
            should_use_hubspot = bool(os.getenv("HUBSPOT_API_KEY"))
    
    # Use HubSpot adapter if available and enabled
    if should_use_hubspot and HUBSPOT_AVAILABLE:
        logger.info("Using HubSpotPipelineAdapter")
        return HubSpotPipelineAdapter(config_path, input_file)
    else:
        if should_use_hubspot and not HUBSPOT_AVAILABLE:
            logger.warning("HubSpot integration requested but not available, using base adapter")
        else:
            logger.info("Using base PipelineAdapter")
        return PipelineAdapter(config_path, input_file)

# Convenience function for direct use
async def run_pipeline(config_path: str = "llm_config.yaml", input_file = None, use_hubspot: bool = None):
    """
    Run the pipeline with given settings
    
    This is the main entry point for the pipeline, used from command line 
    or when no customization is needed.
    
    Args:
        config_path: Path to the LLM configuration file
        input_file: Path to the input file with company names
        use_hubspot: Whether to use HubSpot integration
        
    Returns:
        Tuple with success count, failure count, and results
    """
    adapter = get_pipeline_adapter(config_path, input_file, use_hubspot)
    return await adapter.run()

__all__ = ['PipelineAdapter', 'run_pipeline', 'get_pipeline_adapter'] 