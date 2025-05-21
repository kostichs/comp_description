import os
import logging
import datetime
from typing import Optional, Dict, Any, Tuple, List
from urllib.parse import urlparse

from hubspot_client import HubSpotClient

# Настройка логирования
logger = logging.getLogger(__name__)

class HubSpotAdapter:
    """
    Адаптер для интеграции HubSpot с основным пайплайном обработки компаний.
    
    Обеспечивает:
    - Проверку существования компании в HubSpot по домену
    - Извлечение существующего описания, если оно актуально
    - Сохранение новых описаний в HubSpot
    """
    
    def __init__(self, api_key: Optional[str] = None, max_age_months: int = 6):
        """
        Инициализация адаптера.
        
        Args:
            api_key (str, optional): API ключ для HubSpot. Если не указан, 
                                     будет взят из переменной окружения HUBSPOT_API_KEY.
            max_age_months (int): Максимальный возраст описания в месяцах.
                                  Описания старше этого возраста будут считаться устаревшими.
        """
        self.client = HubSpotClient(api_key)
        self.max_age_months = max_age_months
        logger.info(f"HubSpot Adapter initialized with max age: {max_age_months} months")
    
    async def check_company_description(self, company_name: str, url: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка наличия актуального описания компании в HubSpot.
        
        Args:
            company_name (str): Название компании
            url (str): URL компании
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: 
                - Первый элемент: True если найдено актуальное описание, иначе False
                - Второй элемент: Словарь с данными о компании, если найдена, иначе None
        """
        if not url:
            logger.info(f"No URL provided for company '{company_name}', skipping HubSpot check")
            return False, None
        
        try:
            # Получаем домен из URL
            domain = self._extract_domain_from_url(url)
            if not domain:
                logger.warning(f"Could not extract domain from URL '{url}' for company '{company_name}'")
                return False, None
            
            logger.info(f"Checking HubSpot for company '{company_name}' with domain '{domain}'")
            company = await self.client.search_company_by_domain(domain)
            
            if not company:
                logger.info(f"Company '{company_name}' with domain '{domain}' not found in HubSpot")
                return False, None
            
            # Получаем свойства компании
            properties = company.get("properties", {})
            description = properties.get("ai_description")
            updated_timestamp = properties.get("ai_description_updated")
            
            logger.info(
                f"Found company in HubSpot: {properties.get('name')}, "
                f"description length: {len(description) if description else 0}, "
                f"updated: {updated_timestamp}"
            )
            
            # Проверяем наличие и актуальность описания
            if description and updated_timestamp:
                is_fresh = self.client.is_description_fresh(updated_timestamp, self.max_age_months)
                if is_fresh:
                    logger.info(
                        f"Using existing description for '{company_name}' from HubSpot. "
                        f"Last updated: {updated_timestamp}"
                    )
                    return True, company
                else:
                    logger.info(
                        f"Description for '{company_name}' in HubSpot is outdated. "
                        f"Last updated: {updated_timestamp}"
                    )
            else:
                logger.info(f"No description found for '{company_name}' in HubSpot")
            
            return False, company
        
        except Exception as e:
            logger.error(f"Error checking company '{company_name}' in HubSpot: {e}", exc_info=True)
            return False, None
    
    async def create_company(self, company_name: str, url: str, description: str) -> Optional[Dict[str, Any]]:
        """
        Создание новой компании в HubSpot.
        
        Args:
            company_name (str): Название компании
            url (str): URL компании
            description (str): Описание компании для сохранения
            
        Returns:
            Optional[Dict[str, Any]]: Данные о созданной компании в случае успеха, иначе None
        """
        if not url:
            logger.info(f"No URL provided for company '{company_name}', cannot create in HubSpot")
            return None
        
        try:
            # Получаем домен из URL
            domain = self._extract_domain_from_url(url)
            if not domain:
                logger.warning(f"Could not extract domain from URL '{url}' for company '{company_name}'")
                return None
            
            # Текущая дата в формате YYYY-MM-DD
            now = datetime.datetime.now().strftime("%Y-%m-%d")
            
            # Свойства для создания компании
            properties = {
                "name": company_name,
                "domain": domain,
                "ai_description": description,
                "ai_description_updated": now
            }
            
            logger.info(f"Creating new company '{company_name}' with domain '{domain}' in HubSpot")
            company = await self.client.create_company(domain, properties)
            
            if company:
                logger.info(f"Successfully created company '{company_name}' in HubSpot")
                return company
            else:
                logger.error(f"Failed to create company '{company_name}' in HubSpot")
                return None
        
        except Exception as e:
            logger.error(f"Error creating company '{company_name}' in HubSpot: {e}", exc_info=True)
            return None
    
    async def save_company_description(
        self, 
        company: Optional[Dict[str, Any]], 
        company_name: str,
        url: str,
        description: str
    ) -> bool:
        """
        Сохранение описания компании в HubSpot.
        
        Args:
            company (Optional[Dict[str, Any]]): Данные о компании из HubSpot, если уже найдена
            company_name (str): Название компании
            url (str): URL компании
            description (str): Описание компании для сохранения
            
        Returns:
            bool: True в случае успешного сохранения, иначе False
        """
        try:
            # Если компания не была найдена ранее, попробуем найти её снова
            if not company and url:
                domain = self._extract_domain_from_url(url)
                if domain:
                    company = await self.client.search_company_by_domain(domain)
            
            # Если компания найдена, обновляем её свойства
            if company:
                company_id = company.get("id")
                
                # Текущая дата в формате YYYY-MM-DD
                now = datetime.datetime.now().strftime("%Y-%m-%d")
                
                # Обновляем свойства
                properties = {
                    "ai_description": description,
                    "ai_description_updated": now
                }
                
                logger.info(f"Updating description for company '{company_name}' in HubSpot")
                result = await self.client.update_company_properties(company_id, properties)
                
                if result:
                    logger.info(f"Successfully updated description for '{company_name}' in HubSpot")
                    return True
                else:
                    logger.error(f"Failed to update description for '{company_name}' in HubSpot")
                    return False
            else:
                # Если компания не найдена, создаём новую
                new_company = await self.create_company(company_name, url, description)
                return new_company is not None
        
        except Exception as e:
            logger.error(f"Error saving description for '{company_name}' in HubSpot: {e}", exc_info=True)
            return False
    
    def _extract_domain_from_url(self, url: str) -> str:
        """
        Извлечение домена из URL.
        
        Args:
            url (str): URL компании
            
        Returns:
            str: Домен компании
        """
        return self.client._normalize_domain(url)
    
    def get_description_from_company(self, company: Dict[str, Any]) -> Tuple[str, str]:
        """
        Извлечение описания и временной метки из данных о компании.
        
        Args:
            company (Dict[str, Any]): Данные о компании из HubSpot
            
        Returns:
            Tuple[str, str]: 
                - Первый элемент: Описание компании
                - Второй элемент: Временная метка обновления в читаемом формате
        """
        properties = company.get("properties", {})
        description = properties.get("ai_description", "")
        timestamp = properties.get("ai_description_updated", "")
        
        # Преобразуем timestamp в читаемый формат
        readable_timestamp = timestamp
        
        # Для формата YYYY-MM-DD дополнительное преобразование не требуется
        
        return description, readable_timestamp


# Пример использования
async def test_hubspot_adapter():
    """Тестовая функция для демонстрации работы адаптера."""
    import asyncio
    
    # Настройка логирования для тестирования
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(levelname)s - %(message)s')
    
    adapter = HubSpotAdapter()
    
    # Тестовая компания
    test_company = "Example Inc."
    test_url = "https://example.com"
    
    # Проверяем наличие описания
    has_description, company_data = await adapter.check_company_description(test_company, test_url)
    
    if has_description:
        description, timestamp = adapter.get_description_from_company(company_data)
        print(f"Found description for {test_company}: {description[:100]}... (Updated: {timestamp})")
    else:
        print(f"No fresh description found for {test_company}")
        
        # Если компания найдена, сохраняем новое описание
        if company_data:
            print("Saving new description to HubSpot...")
            test_description = "This is a test description generated for Example Inc."
            save_result = await adapter.save_company_description(
                company_data, test_company, test_url, test_description
            )
            print(f"Save result: {save_result}")
        else:
            # Если компания не найдена, создаём новую
            print("Creating new company in HubSpot...")
            test_description = "This is a description for a newly created Example Inc."
            new_company = await adapter.create_company(test_company, test_url, test_description)
            if new_company:
                print(f"Successfully created company: {new_company.get('id')}")
            else:
                print("Failed to create company")


if __name__ == "__main__":
    # Запускаем тестовую функцию при прямом вызове скрипта
    import asyncio
    asyncio.run(test_hubspot_adapter()) 