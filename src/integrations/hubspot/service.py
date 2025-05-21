"""
HubSpot Integration Service

Provides business logic for working with HubSpot data
"""

import logging
from typing import Optional, Dict, Any
from src.integrations.hubspot.client import HubSpotClient

logger = logging.getLogger(__name__)

class HubSpotIntegrationService:
    """
    Service for HubSpot integration business logic
    
    Encapsulates the business rules for working with HubSpot data,
    such as when to retrieve data, when to update it, etc.
    """
    
    def __init__(self, api_key: str, max_age_months: int = 6, base_url: str = "https://api.hubapi.com"):
        """
        Initialize the HubSpot integration service
        
        Args:
            api_key: HubSpot API key
            max_age_months: Maximum age of description in months
            base_url: HubSpot API base URL
        """
        self.client = HubSpotClient(api_key, base_url)
        self.max_age_months = max_age_months
    
    async def should_process_company(self, domain: str) -> bool:
        """
        Check if a company should be processed
        
        This method determines if we should run the full pipeline for a company
        or use the existing data from HubSpot.
        
        Args:
            domain: Company domain/website
            
        Returns:
            bool: True if the company should be processed, False if HubSpot data is fresh
        """
        if not domain:
            logger.info("No domain provided, company should be processed")
            return True
        
        company_data = await self.client.search_company_by_website(domain)
        if not company_data:
            logger.info(f"Company with domain {domain} not found in HubSpot, should be processed")
            return True
        
        # Проверяем наличие и свежесть описания
        properties = company_data.get("properties", {})
        description = properties.get("description")
        timestamp = properties.get("description_timestamp")
        
        if not description or not timestamp:
            logger.info(f"Company {domain} found in HubSpot but missing description or timestamp, should be processed")
            return True
        
        # Проверяем свежесть описания
        is_fresh = self.client.is_description_fresh(timestamp, self.max_age_months)
        logger.info(f"Company {domain} description in HubSpot is {'fresh' if is_fresh else 'outdated'}")
        
        # Если описание свежее, не нужно обрабатывать компанию
        return not is_fresh
    
    async def get_company_data(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Get company data from HubSpot
        
        Args:
            domain: Company domain/website
            
        Returns:
            Dict or None: Company data if found, with proper formatting
        """
        company_data = await self.client.search_company_by_website(domain)
        if not company_data:
            return None
        
        properties = company_data.get("properties", {})
        
        # Форматируем данные для использования в пайплайне
        return {
            "description": properties.get("description"),
            "timestamp": properties.get("description_timestamp"),
            "linkedin_url": properties.get("linkedin_url"),
            "name": properties.get("name"),
            "hubspot_id": company_data.get("id")
        }
    
    async def save_company_description(self, domain: str, company_name: str, description: str) -> bool:
        """
        Save company description to HubSpot
        
        Args:
            domain: Company domain/website
            company_name: Company name
            description: Company description
            
        Returns:
            bool: True if saved successfully
        """
        # Проверяем существование компании
        company_data = await self.client.search_company_by_website(domain)
        
        if company_data and company_data.get("id"):
            # Компания существует, обновляем описание
            company_id = company_data.get("id")
            logger.info(f"Updating existing company {company_name} ({domain}) in HubSpot")
            return await self.client.update_company_description(company_id, description)
            
        # В будущем можно добавить создание новой компании, если она не существует
        logger.warning(f"Company {company_name} ({domain}) not found in HubSpot, cannot update description")
        return False 