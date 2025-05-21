"""
HubSpot API Client Module

Provides a client for interacting with the HubSpot API, focusing on
companies and their properties.
"""

import requests
import datetime
import logging
from typing import Dict, Optional, List, Tuple, Any

logger = logging.getLogger(__name__)

class HubSpotClient:
    """
    Client for interacting with the HubSpot API
    
    Provides methods for searching, retrieving, and updating company data in HubSpot.
    Uses caching to optimize API usage.
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.hubapi.com"):
        """
        Initialize the HubSpot client
        
        Args:
            api_key: HubSpot API key
            base_url: HubSpot API base URL
        """
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self._cache = {}  # Кэш для избежания повторных запросов
    
    async def search_company_by_website(self, website: str) -> Optional[Dict]:
        """
        Поиск компании по веб-сайту
        
        Args:
            website: URL веб-сайта компании
            
        Returns:
            Dict или None: данные компании или None, если не найдена
        """
        # Нормализация URL (удаление http://, https://, www., конечных слешей)
        normalized_website = self._normalize_website(website)
        
        # Проверяем кэш
        if normalized_website in self._cache:
            logger.info(f"Using cached result for website: {normalized_website}")
            return self._cache[normalized_website]
        
        endpoint = f"{self.base_url}/crm/v3/objects/companies/search"
        payload = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "website",
                    "operator": "CONTAINS_TOKEN",
                    "value": normalized_website
                }]
            }],
            "properties": ["name", "website", "description", "description_timestamp", "linkedin_url"],
            "limit": 1
        }
        
        logger.info(f"Searching HubSpot for company with website: {normalized_website}")
        response = requests.post(endpoint, headers=self.headers, json=payload)
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                logger.info(f"Found company with website {normalized_website} in HubSpot")
                self._cache[normalized_website] = results[0]  # Сохраняем в кэш
                return results[0]
            logger.info(f"No company found with website {normalized_website} in HubSpot")
        else:
            logger.warning(f"HubSpot API error: {response.status_code} - {response.text}")
        
        self._cache[normalized_website] = None  # Кэшируем отрицательный результат
        return None
    
    def _normalize_website(self, website: str) -> str:
        """
        Нормализация веб-сайта для сравнения
        
        Args:
            website: URL веб-сайта
            
        Returns:
            str: нормализованный URL
        """
        if not website:
            return ""
            
        website = website.lower()
        for prefix in ["https://", "http://", "www."]:
            if website.startswith(prefix):
                website = website[len(prefix):]
        if website.endswith("/"):
            website = website[:-1]
        return website
    
    def is_description_fresh(self, timestamp_str: str, max_age_months: int = 6) -> bool:
        """
        Проверка свежести описания (меньше max_age_months)
        
        Args:
            timestamp_str: Строка с временной меткой в формате ISO
            max_age_months: Максимальный возраст в месяцах
            
        Returns:
            bool: True, если описание свежее
        """
        try:
            timestamp = datetime.datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            now = datetime.datetime.now(datetime.timezone.utc)
            age = now - timestamp
            return age.days < max_age_months * 30  # примерно 30 дней в месяце
        except Exception as e:
            logger.error(f"Error parsing timestamp {timestamp_str}: {e}")
            return False  # При ошибке считаем описание устаревшим
    
    async def update_company_description(self, company_id: str, description: str) -> bool:
        """
        Обновление описания компании в HubSpot
        
        Args:
            company_id: ID компании в HubSpot
            description: Новое описание
            
        Returns:
            bool: True в случае успеха
        """
        endpoint = f"{self.base_url}/crm/v3/objects/companies/{company_id}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        payload = {
            "properties": {
                "description": description,
                "description_timestamp": now
            }
        }
        
        logger.info(f"Updating company {company_id} description in HubSpot")
        response = requests.patch(endpoint, headers=self.headers, json=payload)
        
        if response.status_code == 200:
            logger.info(f"Successfully updated description for company {company_id}")
            return True
        else:
            logger.error(f"Failed to update company {company_id}: {response.status_code} - {response.text}")
            return False 