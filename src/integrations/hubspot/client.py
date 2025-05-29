"""
HubSpot API Client Module

Provides a client for interacting with the HubSpot API, focusing on
companies and their properties.
"""

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

# Configure logging
logger = logging.getLogger(__name__)

class HubSpotClient:
    """
    Client for working with HubSpot API.
    
    Provides functionality:
    - Search companies by domain
    - Get company properties
    - Update company properties
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.hubapi.com"):
        """
        Initialize HubSpot API client.
        
        Args:
            api_key (str, optional): API key for HubSpot access. 
                                     If not specified, will be taken from HUBSPOT_API_KEY environment variable.
            base_url (str): Base URL for HubSpot API.
        """
        # Load environment variables if api_key is not provided
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
        
        # Cache to avoid repeated requests
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
                    "filterGroups": [
                        {
                            "filters": [{
                                "propertyName": "domain",
                                "operator": "CONTAINS_TOKEN",
                                "value": normalized_domain
                            }]
                        },
                        {
                            "filters": [{
                                "propertyName": "domain", 
                                "operator": "EQ",
                                "value": normalized_domain
                            }]
                        },
                        {
                            "filters": [{
                                "propertyName": "website",
                                "operator": "EQ", 
                                "value": normalized_domain
                            }]
                        },
                        {
                            "filters": [{
                                "propertyName": "hs_additional_domains",
                                "operator": "CONTAINS_TOKEN",
                                "value": normalized_domain
                            }]
                        }
                        # Можно добавить дополнительные поля для веб-сайтов, если они есть в вашем HubSpot
                        # {
                        #     "filters": [{
                        #         "propertyName": "additional_website",
                        #         "operator": "EQ",
                        #         "value": normalized_domain
                        #     }]
                        # }
                    ],
                    "properties": ["name", "domain", "website", "hs_additional_domains", "ai_description", "ai_description_updated", "linkedin_company_page"],
                    "limit": 10  # Увеличиваем лимит на случай нескольких совпадений
                }
                
                async with session.post(endpoint, headers=self.headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        
                        if results:
                            # Если найдено несколько компаний, выберем лучшее совпадение
                            # Приоритет: точное совпадение domain > точное совпадение website > первый результат
                            best_match = None
                            
                            for company in results:
                                properties = company.get("properties", {})
                                company_domain = properties.get("domain", "")
                                company_website = properties.get("website", "")
                                company_additional_domains = properties.get("hs_additional_domains", "")
                                
                                # Проверяем основной домен
                                domain_match_found = self._check_domain_match(company_domain, normalized_domain)
                                # Проверяем поле website
                                website_match_found = self._check_domain_match(company_website, normalized_domain)
                                # Проверяем дополнительные домены
                                additional_domains_match_found = self._check_domain_match(company_additional_domains, normalized_domain)
                                
                                # Точное совпадение с полем domain имеет наивысший приоритет
                                if domain_match_found:
                                    best_match = company
                                    logger.info(f"Found domain match in HubSpot: {properties.get('name')} (domain field: {company_domain})")
                                    break
                                # Совпадение с дополнительными доменами имеет второй приоритет
                                elif additional_domains_match_found:
                                    if not best_match:
                                        best_match = company
                                        logger.info(f"Found additional domains match in HubSpot: {properties.get('name')} (hs_additional_domains field: {company_additional_domains})")
                                # Совпадение с полем website
                                elif website_match_found:
                                    if not best_match:  # Только если еще не найдено совпадение с domain или additional_domains
                                        best_match = company
                                        logger.info(f"Found website match in HubSpot: {properties.get('name')} (website field: {company_website})")
                                # Если не найдено совпадений, используем первый результат как fallback
                                elif not best_match:
                                    best_match = company
                                    logger.info(f"Using first result in HubSpot: {properties.get('name')} (domain: {company_domain}, website: {company_website}, additional_domains: {company_additional_domains})")
                            
                            if best_match:
                                # Кэшируем результат
                                self._cache[cache_key] = best_match
                                return best_match
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
                    
                    # Рассчитываем разницу в месяцах
                    # Приблизительный расчет: (разница в днях) / 30.44
                    # Более точный вариант:
                    months_difference = (today.year - timestamp_date.year) * 12 + (today.month - timestamp_date.month)
                    
                    # Если сегодня тот же день или раньше (например, дата из будущего), считаем свежим
                    if today <= timestamp_date:
                        return True
                        
                    # Если разница в месяцах меньше или равна max_age_months, считаем свежим
                    if months_difference <= max_age_months:
                        # Дополнительная проверка на случай, если день в текущем месяце меньше дня в timestamp
                        if months_difference == max_age_months and today.day < timestamp_date.day:
                            return False # Уже прошел полный месяц
                        return True
                    
                    return False
                    
                except ValueError:
                    logger.warning(f"Invalid date format in YYYY-MM-DD: {timestamp_str}")
                    return False

            # Если формат ISO (стандарт HubSpot), парсим с учетом часового пояса
            timestamp = datetime.datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            
            # Получаем текущее время с учетом часового пояса
            now = datetime.datetime.now(datetime.timezone.utc)
            
            # Рассчитываем разницу во времени
            age = now - timestamp
            
            # Рассчитываем максимальный возраст в днях (приблизительно)
            max_age_days = max_age_months * 30.44  # Среднее количество дней в месяце
            
            # Сравниваем возраст с максимальным
            return age.days <= max_age_days
            
        except Exception as e:
            logger.error(f"Error parsing timestamp '{timestamp_str}': {e}")
            return False # В случае ошибки парсинга считаем описание не свежим
            
    def _normalize_domain(self, url: str) -> str:
        """
        Нормализация URL или домена.
        
        Args:
            url (str): URL или домен для нормализации
            
        Returns:
            str: Нормализованный домен
        """
        try:
            # Импортируем функцию normalize_domain из input_validators
            from src.input_validators import normalize_domain
            
            # Используем общую функцию normalize_domain
            normalized_domain = normalize_domain(url)
            return normalized_domain
        except Exception as e:
            logger.error(f"Error normalizing domain: {e}")
            
            # Резервный вариант, если импорт функции не удался
            try:
                # Очищаем URL от пробелов
                url = url.strip().lower()
                
                # Если URL не содержит протокол, добавляем https://
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                
                # Используем urlparse для извлечения домена
                parsed_url = urlparse(url)
                domain = parsed_url.netloc
                
                # Удаляем www. из начала домена, если присутствует
                if domain.startswith('www.'):
                    domain = domain[4:]
                
                # Удаляем порт, если он есть
                domain = domain.split(':')[0]
                
                return domain.lower()
            except Exception as inner_e:
                logger.error(f"Error in fallback domain normalization: {inner_e}")
                return ""

    def _invalidate_cache_for_company(self, company_id: str) -> None:
        """
        Инвалидация кэша для конкретной компании.
        
        Это необходимо, если данные компании были обновлены, и кэш для её домена 
        (если он был основан на поиске по домену) должен быть сброшен.
        
        Args:
            company_id (str): ID компании в HubSpot.
        """
        # Ищем ключ в кэше, который соответствует company_id
        # Это упрощенная инвалидация, так как мы кэшируем по домену.
        # Если есть более сложная логика кэширования, её нужно будет учесть.
        
        # Собираем ключи, которые нужно удалить
        keys_to_delete = []
        for key, cached_item in self._cache.items():
            if isinstance(cached_item, dict) and cached_item.get("id") == company_id:
                keys_to_delete.append(key)
        
        # Удаляем найденные ключи
        for key in keys_to_delete:
            del self._cache[key]
            logger.info(f"Cache invalidated for company ID {company_id} (key: {key})")

    def _check_domain_match(self, domain_field: str, normalized_target_domain: str) -> bool:
        """
        Проверка совпадения домена с нормализованным доменом.
        Обрабатывает как одиночные домены, так и множественные (разделенные ; или другими разделителями).
        
        Args:
            domain_field (str): Поле домена из HubSpot (может содержать несколько доменов)
            normalized_target_domain (str): Нормализованный целевой домен для поиска
            
        Returns:
            bool: True, если один из доменов совпадает, иначе False
        """
        if not domain_field or not normalized_target_domain:
            return False
            
        try:
            # Возможные разделители доменов в HubSpot
            separators = [';', ',', '\n', '\r\n', '|']
            
            # Разбиваем поле на отдельные домены
            domains = [domain_field.strip()]  # Начинаем с исходного значения
            
            for sep in separators:
                if sep in domain_field:
                    domains = []
                    for part in domain_field.split(sep):
                        part = part.strip()
                        if part:  # Игнорируем пустые части
                            domains.append(part)
                    break  # Используем первый найденный разделитель
            
            # Проверяем каждый домен на совпадение
            for domain in domains:
                domain = domain.strip()
                if not domain:
                    continue
                    
                # Нормализуем домен из HubSpot
                normalized_hubspot_domain = self._normalize_domain(domain)
                
                if normalized_hubspot_domain == normalized_target_domain:
                    logger.debug(f"Domain match found: '{domain}' -> '{normalized_hubspot_domain}' == '{normalized_target_domain}'")
                    return True
                    
            return False
            
        except Exception as e:
            logger.error(f"Error checking domain match for '{domain_field}': {e}")
            return False


# Пример использования и тестирования
async def test_hubspot_client():
    """Тестовая функция для демонстрации работы клиента."""
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Загрузка API ключа из .env файла (убедитесь, что файл .env существует и содержит HUBSPOT_API_KEY)
    load_dotenv()
    api_key = os.getenv("HUBSPOT_API_KEY")
    
    if not api_key:
        logger.error("HUBSPOT_API_KEY not found in .env file. Please set it to run the test.")
        return

    client = HubSpotClient(api_key=api_key)

    # Тест поиска компании
    # Используйте домен, который существует или не существует в вашем HubSpot для теста
    test_domain = "hubspot.com" # Существующий домен
    # test_domain = "nonexistentdomain12345.com" # Несуществующий домен
    
    logger.info(f"--- Testing search_company_by_domain for '{test_domain}' ---")
    company = await client.search_company_by_domain(test_domain)
    if company:
        logger.info(f"Found company: {company.get('properties', {}).get('name')}")
        logger.info(f"Company ID: {company.get('id')}")
        logger.info(f"Company properties: {company.get('properties')}")
    else:
        logger.info(f"Company with domain '{test_domain}' not found.")
    
    # Тест создания компании (Будьте осторожны, это создаст реальную компанию в HubSpot)
    # logger.info("--- Testing create_company ---")
    # new_company_domain = "test-new-company-domain-python.com" 
    # new_company_props = {
    #     "name": "Test New Company (Python)",
    #     "ai_description": "This is a test company created via Python script.",
    #     "ai_description_updated": "current_date" 
    # }
    # created_company = await client.create_company(new_company_domain, new_company_props)
    # if created_company:
    #     logger.info(f"Successfully created company: {created_company.get('properties', {}).get('name')}")
    #     created_company_id = created_company.get("id")
    #     logger.info(f"New company ID: {created_company_id}")
        
    #     # Тест обновления свойств компании (используем ID созданной компании)
    #     if created_company_id:
    #         logger.info(f"--- Testing update_company_properties for ID '{created_company_id}' ---")
    #         updated_props = {
    #             "ai_description": "Updated description for the test company (Python).",
    #             "ai_description_updated": "current_date"
    #         }
    #         success = await client.update_company_properties(created_company_id, updated_props)
    #         if success:
    #             logger.info("Successfully updated company properties.")
    #             # Проверим, что описание обновилось, сделав повторный поиск
    #             updated_company_check = await client.search_company_by_domain(new_company_domain)
    #             if updated_company_check:
    #                 logger.info(f"Updated description: {updated_company_check.get('properties', {}).get('ai_description')}")
    #         else:
    #             logger.error("Failed to update company properties.")
    # else:
    #     logger.error(f"Failed to create company with domain '{new_company_domain}'.")

    # Тест проверки свежести описания
    logger.info("--- Testing is_description_fresh ---")
    
    # Пример 1: Свежая дата (сегодня)
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    is_fresh_today = client.is_description_fresh(today_str, 6)
    logger.info(f"Timestamp '{today_str}' (YYYY-MM-DD), fresh (6 months): {is_fresh_today}") # Ожидаем True

    # Пример 2: Дата месяц назад (свежая)
    one_month_ago = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    is_fresh_one_month = client.is_description_fresh(one_month_ago, 6)
    logger.info(f"Timestamp '{one_month_ago}' (YYYY-MM-DD), fresh (6 months): {is_fresh_one_month}") # Ожидаем True

    # Пример 3: Дата 7 месяцев назад (устаревшая)
    seven_months_ago = (datetime.datetime.now() - datetime.timedelta(days=7*30)).strftime("%Y-%m-%d")
    is_fresh_seven_months = client.is_description_fresh(seven_months_ago, 6)
    logger.info(f"Timestamp '{seven_months_ago}' (YYYY-MM-DD), fresh (6 months): {is_fresh_seven_months}") # Ожидаем False

    # Пример 4: ISO формат, свежая дата (UTC)
    now_utc_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    is_fresh_iso_now = client.is_description_fresh(now_utc_iso, 6)
    logger.info(f"Timestamp '{now_utc_iso}' (ISO), fresh (6 months): {is_fresh_iso_now}") # Ожидаем True

    # Пример 5: ISO формат, устаревшая дата
    seven_months_ago_iso = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7*30)).isoformat()
    is_fresh_iso_old = client.is_description_fresh(seven_months_ago_iso, 6)
    logger.info(f"Timestamp '{seven_months_ago_iso}' (ISO), fresh (6 months): {is_fresh_iso_old}") # Ожидаем False
    
    # Пример 6: Невалидный timestamp
    invalid_ts = "не дата"
    is_fresh_invalid = client.is_description_fresh(invalid_ts, 6)
    logger.info(f"Timestamp '{invalid_ts}', fresh (6 months): {is_fresh_invalid}") # Ожидаем False
    
    # Пример 7: Пустой timestamp
    empty_ts = None
    is_fresh_empty = client.is_description_fresh(empty_ts, 6)
    logger.info(f"Timestamp '{empty_ts}', fresh (6 months): {is_fresh_empty}") # Ожидаем False

if __name__ == "__main__":
    # Для запуска теста раскомментируйте следующую строку:
    asyncio.run(test_hubspot_client())
    pass 