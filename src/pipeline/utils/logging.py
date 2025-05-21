"""
Pipeline Logging Utilities

This module provides functions for setting up logging for the pipeline.
"""

import logging
from typing import Optional

def setup_session_logging(pipeline_log_path: str, log_level: Optional[int] = None):
    """
    Set up logging for a pipeline session.
    
    Args:
        pipeline_log_path: Path to save pipeline logs
        log_level: Optional logging level (defaults to INFO)
    """
    if log_level is None:
        log_level = logging.INFO
        
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s:%(module)s:%(funcName)s:%(lineno)d] - %(message)s'
    )
    
    root_logger = logging.getLogger() 
    
    # Remove any existing handlers for this log file
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler) and \
           (handler.baseFilename == pipeline_log_path):
            root_logger.removeHandler(handler)
            handler.close()

    # Create and add file handler
    pipeline_handler = logging.FileHandler(pipeline_log_path, mode='w', encoding='utf-8')
    pipeline_handler.setFormatter(detailed_formatter)
    pipeline_handler.setLevel(log_level) 
    root_logger.addHandler(pipeline_handler)
    
    # Set root logger level
    root_logger.setLevel(log_level) 

    logger = logging.getLogger(__name__)
    logger.info("Session logging setup complete with detailed formatter")
    
    # Reduce logging level for HTTP client libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING) 