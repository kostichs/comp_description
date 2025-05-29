"""
HubSpot Integration Module

Provides integration with HubSpot CRM for retrieving and updating
company descriptions.
"""

import logging

logger = logging.getLogger(__name__)

try:
    # Fix circular dependencies by importing client first
    from src.integrations.hubspot.client import HubSpotClient

    # Then import adapters
    from src.integrations.hubspot.adapter import HubSpotAdapter, HubSpotPipelineAdapter

    # Then import service
    from src.integrations.hubspot.service import HubSpotIntegrationService

    __all__ = [
        'HubSpotClient',
        'HubSpotAdapter',
        'HubSpotPipelineAdapter',
        'HubSpotIntegrationService'
    ]
    
    HUBSPOT_AVAILABLE = True
    logger.info("HubSpot integration module loaded successfully")
    
except ImportError as e:
    HUBSPOT_AVAILABLE = False
    logger.error(f"Failed to import HubSpot integration module: {e}")
    
    # Create stub classes
    class HubSpotClient:
        def __init__(self, *args, **kwargs):
            logger.error("HubSpotClient unavailable - module import failed")
            
    class HubSpotAdapter:
        def __init__(self, *args, **kwargs):
            logger.error("HubSpotAdapter unavailable - module import failed")
            
    class HubSpotPipelineAdapter:
        def __init__(self, *args, **kwargs):
            logger.error("HubSpotPipelineAdapter unavailable - module import failed")
            
    class HubSpotIntegrationService:
        def __init__(self, *args, **kwargs):
            logger.error("HubSpotIntegrationService unavailable - module import failed")
            
    __all__ = [
        'HubSpotClient',
        'HubSpotAdapter',
        'HubSpotPipelineAdapter',
        'HubSpotIntegrationService'
    ] 