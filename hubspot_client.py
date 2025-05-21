import requests
import datetime
from typing import Dict, Optional, List, Tuple

class HubSpotClient:
    def __init__(self, api_key: str, base_url: str = "https://api.hubapi.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self._cache = {}  # Кэш для избежания повторных запросов
    
    async def search_company_by_website(self, website: str) -> Optional[Dict]:
        """Поиск компании по веб-сайту"""
        # Нормализация URL (удаление http://, https://, www., конечных слешей)
        normalized_website = self._normalize_website(website)
        
        # Проверяем кэш
        if normalized_website in self._cache:
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
        
        response = requests.post(endpoint, headers=self.headers, json=payload)
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                self._cache[normalized_website] = results[0]  # Сохраняем в кэш
                return results[0]
        
        self._cache[normalized_website] = None  # Кэшируем отрицательный результат
        return None
    
    def _normalize_website(self, website: str) -> str:
        """Нормализация веб-сайта для сравнения"""
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
        """Проверка свежести описания (меньше max_age_months)"""
        try:
            timestamp = datetime.datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            now = datetime.datetime.now(datetime.timezone.utc)
            age = now - timestamp
            return age.days < max_age_months * 30  # примерно 30 дней в месяце
        except Exception:
            return False  # При ошибке считаем описание устаревшим 