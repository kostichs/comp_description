import os
import re
import json
import logging
import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
import aiohttp
import asyncio
from dotenv import load_dotenv

# Настройка логирования
logger = logging.getLogger(__name__)

class HubSpotClient:
    """
    Клиент для работы с HubSpot API.
    
    Обеспечивает функциональность:
    - Поиск компаний по домену
    - Получение свойств компании
    - Обновление свойств компании
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.hubapi.com"):
        """
        Инициализация клиента HubSpot API.
        
        Args:
            api_key (str, optional): API ключ для доступа к HubSpot. 
                                     Если не указан, будет взят из переменной окружения HUBSPOT_API_KEY.
            base_url (str): Базовый URL для API HubSpot.
        """
        # Загружаем переменные окружения, если api_key не передан
        if api_key is None:
            load_dotenv()
            api_key = os.getenv("HUBSPOT_API_KEY")
        
        if not api_key:
            logger.warning("HubSpot API key not provided. HubSpot integration will not work.")
        
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Кэш для избежания повторных запросов
        self._cache = {}
    
    async def search_company_by_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Поиск компании в HubSpot по домену.
        
        Args:
            domain (str): Домен компании (например, "example.com")
            
        Returns:
            Optional[Dict[str, Any]]: Данные о компании, если найдена, иначе None
        """
        if not self.api_key:
            logger.warning("HubSpot API key not set. Search operation aborted.")
            return None
        
        try:
            # Нормализация домена
            normalized_domain = self._normalize_domain(domain)
            if not normalized_domain:
                logger.warning(f"Invalid domain: {domain}")
                return None
            
            # Проверяем кэш
            cache_key = f"domain:{normalized_domain}"
            if cache_key in self._cache:
                logger.info(f"Using cached result for domain: {normalized_domain}")
                return self._cache[cache_key]
            
            # Формируем запрос к API
            endpoint = f"{self.base_url}/crm/v3/objects/companies/search"
            
            async with aiohttp.ClientSession() as session:
                payload = {
                    "filterGroups": [{
                        "filters": [{
                            "propertyName": "domain",
                            "operator": "EQ",
                            "value": normalized_domain
                        }]
                    }],
                    "properties": ["name", "domain", "ai_description", "ai_description_updated"],
                    "limit": 1
                }
                
                async with session.post(endpoint, headers=self.headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        
                        if results:
                            company = results[0]
                            # Кэшируем результат
                            self._cache[cache_key] = company
                            logger.info(f"Found company in HubSpot: {company.get('properties', {}).get('name')}")
                            return company
                        else:
                            logger.info(f"No company found for domain: {normalized_domain}")
                            # Кэшируем отрицательный результат
                            self._cache[cache_key] = None
                            return None
                    else:
                        error_text = await response.text()
                        logger.error(f"HubSpot API error ({response.status}): {error_text}")
                        return None
        
        except Exception as e:
            logger.error(f"Error searching company by domain: {e}", exc_info=True)
            return None
    
    async def create_company(self, domain: str, properties: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Создание новой компании в HubSpot.
        
        Args:
            domain (str): Домен компании (например, "example.com")
            properties (Dict[str, str]): Словарь свойств компании
            
        Returns:
            Optional[Dict[str, Any]]: Данные о созданной компании в случае успеха, иначе None
        """
        if not self.api_key:
            logger.warning("HubSpot API key not set. Create operation aborted.")
            return None
        
        try:
            # Нормализация домена
            normalized_domain = self._normalize_domain(domain)
            if not normalized_domain:
                logger.warning(f"Invalid domain: {domain}")
                return None
            
            # Добавляем домен в свойства
            properties["domain"] = normalized_domain
            
            # Устанавливаем текущую дату в формате YYYY-MM-DD
            if "ai_description_updated" in properties:
                # Всегда используем только формат YYYY-MM-DD без времени
                properties["ai_description_updated"] = datetime.datetime.now().strftime("%Y-%m-%d")
            
            endpoint = f"{self.base_url}/crm/v3/objects/companies"
            
            async with aiohttp.ClientSession() as session:
                payload = {
                    "properties": properties
                }
                
                async with session.post(endpoint, headers=self.headers, json=payload) as response:
                    if response.status == 201:
                        data = await response.json()
                        logger.info(f"Successfully created company with domain: {normalized_domain}")
                        
                        # Добавляем свойства в ответ для соответствия формату ответа search_company_by_domain
                        if "properties" not in data:
                            data["properties"] = properties
                        
                        # Сбрасываем кэш для этого домена
                        cache_key = f"domain:{normalized_domain}"
                        if cache_key in self._cache:
                            del self._cache[cache_key]
                        
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create company. Status: {response.status}, Error: {error_text}")
                        return None
        
        except Exception as e:
            logger.error(f"Error creating company: {e}", exc_info=True)
            return None
    
    async def update_company_properties(self, company_id: str, properties: Dict[str, str]) -> bool:
        """
        Обновление свойств компании в HubSpot.
        
        Args:
            company_id (str): ID компании в HubSpot
            properties (Dict[str, str]): Словарь свойств для обновления
            
        Returns:
            bool: True в случае успеха, False в случае ошибки
        """
        if not self.api_key:
            logger.warning("HubSpot API key not set. Update operation aborted.")
            return False
        
        try:
            # Устанавливаем текущую дату в формате YYYY-MM-DD
            if "ai_description_updated" in properties:
                # Всегда используем только формат YYYY-MM-DD без времени
                properties["ai_description_updated"] = datetime.datetime.now().strftime("%Y-%m-%d")
            
            endpoint = f"{self.base_url}/crm/v3/objects/companies/{company_id}"
            
            async with aiohttp.ClientSession() as session:
                payload = {
                    "properties": properties
                }
                
                async with session.patch(endpoint, headers=self.headers, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Successfully updated properties for company ID: {company_id}")
                        # Сбрасываем кэш для этой компании
                        self._invalidate_cache_for_company(company_id)
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to update company properties. Status: {response.status}, Error: {error_text}")
                        return False
        
        except Exception as e:
            logger.error(f"Error updating company properties: {e}", exc_info=True)
            return False
    
    def is_description_fresh(self, timestamp_str: Optional[str], max_age_months: int = 6) -> bool:
        """
        Проверка свежести описания по временной метке.
        
        Args:
            timestamp_str (Optional[str]): Временная метка в ISO формате или YYYY-MM-DD
            max_age_months (int): Максимальный возраст описания в месяцах
            
        Returns:
            bool: True если описание свежее (не старше max_age_months), иначе False
        """
        if not timestamp_str:
            return False
        
        try:
            # Если формат даты YYYY-MM-DD, просто используем разницу между датами
            if len(timestamp_str) == 10 and timestamp_str[4] == '-' and timestamp_str[7] == '-':
                try:
                    # Парсим дату в формате YYYY-MM-DD
                    date_parts = timestamp_str.split('-')
                    year = int(date_parts[0])
                    month = int(date_parts[1])
                    day = int(date_parts[2])
                    
                    # Получаем текущую дату без времени
                    today = datetime.datetime.now().date()
                    timestamp_date = datetime.date(year, month, day)
                    
                    # Вычисляем разницу в днях
                    age_days = (today - timestamp_date).days
                    max_age_days = max_age_months * 30  # примерное количество дней в месяце
                    
                    logger.debug(f"Description age: {age_days} days, max allowed: {max_age_days} days")
                    return age_days < max_age_days
                except Exception as e:
                    logger.error(f"Error parsing YYYY-MM-DD format: {e}")
                    return False
            
            # Если формат ISO, используем datetime
            try:
                # Пробуем ISO формат
                timestamp = datetime.datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                now = datetime.datetime.now(datetime.timezone.utc)
                
                # Вычисляем разницу в днях
                age_days = (now - timestamp).days
                max_age_days = max_age_months * 30  # примерное количество дней в месяце
                
                logger.debug(f"Description age: {age_days} days, max allowed: {max_age_days} days")
                return age_days < max_age_days
            except Exception as e:
                logger.error(f"Error parsing ISO format: {e}")
                return False
        
        except Exception as e:
            logger.error(f"Error checking timestamp freshness: {e}")
            return False
    
    def _normalize_domain(self, url: str) -> str:
        """
        Нормализация URL в домен для сравнения.
        
        Args:
            url (str): URL или домен (например, "https://www.example.com/page")
            
        Returns:
            str: Нормализованный домен (например, "example.com")
        """
        if not url:
            return ""
        
        # Проверяем, является ли url уже доменом
        if "/" not in url and "." in url:
            domain = url.lower()
        else:
            # Добавляем протокол, если его нет
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            
            # Парсим URL
            try:
                parsed_url = urlparse(url)
                domain = parsed_url.netloc.lower()
            except Exception:
                logger.warning(f"Failed to parse URL: {url}")
                return ""
        
        # Удаляем 'www.' если есть
        if domain.startswith("www."):
            domain = domain[4:]
        
        return domain
    
    def _invalidate_cache_for_company(self, company_id: str) -> None:
        """
        Инвалидация кэша для компании.
        
        Args:
            company_id (str): ID компании в HubSpot
        """
        # Удаляем все записи в кэше, связанные с этой компанией
        keys_to_remove = []
        for key, value in self._cache.items():
            if value and value.get("id") == company_id:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._cache[key]


# Пример использования
async def test_hubspot_client():
    """Тестовая функция для демонстрации работы клиента."""
    # Настройка логирования для тестирования
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(levelname)s - %(message)s')
    
    client = HubSpotClient()
    
    # Пример поиска компании по домену
    test_domain = "example.com"
    company = await client.search_company_by_domain(test_domain)
    
    if company:
        company_id = company["id"]
        properties = company.get("properties", {})
        print(f"Found company: {properties.get('name')}")
        
        # Пример обновления свойств
        update_result = await client.update_company_properties(
            company_id, 
            {
                "ai_description": "Тестовое описание компании",
                "ai_description_updated": datetime.datetime.now().strftime("%Y-%m-%d")
            }
        )
        print(f"Update result: {update_result}")
    else:
        print(f"No company found for domain: {test_domain}")
        
        # Пример создания новой компании
        now = datetime.datetime.now().strftime("%Y-%m-%d")  # Используем формат YYYY-MM-DD
        new_company = await client.create_company(
            test_domain,
            {
                "name": "Example Company",
                "ai_description": "Новое описание компании",
                "ai_description_updated": now
            }
        )
        if new_company:
            print(f"Created new company with ID: {new_company.get('id')}")


if __name__ == "__main__":
    # Запускаем тестовую функцию при прямом вызове скрипта
    asyncio.run(test_hubspot_client()) 