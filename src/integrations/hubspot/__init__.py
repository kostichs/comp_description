"""
HubSpot Integration Module

Provides integration with HubSpot CRM for retrieving and updating
company descriptions.
"""

from src.integrations.hubspot.client import HubSpotClient
from src.integrations.hubspot.adapter import HubSpotPipelineAdapter
from src.integrations.hubspot.service import HubSpotIntegrationService

__all__ = [
    'HubSpotClient',
    'HubSpotPipelineAdapter',
    'HubSpotIntegrationService'
] 