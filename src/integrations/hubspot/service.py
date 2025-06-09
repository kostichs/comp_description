"""
HubSpot Integration Service

Provides business logic for working with HubSpot data
"""

import os
import logging
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

# Убираем импорт HubSpotAdapter отсюда для избавления от циклической зависимости
# from src.integrations.hubspot.adapter import HubSpotAdapter

# Настройка логирования
logger = logging.getLogger(__name__)

class HubSpotIntegrationService:
    """
    Модуль интеграции для связи между основным пайплайном и HubSpot.
    
    Этот класс предоставляет методы для:
    - Проверки описаний компаний в HubSpot
    - Принятия решения о необходимости генерации новых описаний
    - Сохранения сгенерированных описаний обратно в HubSpot
    """
    
    def __init__(self, 
                 api_key: Optional[str] = None, 
                 use_integration: bool = True,
                 max_age_months: int = 6):
        """
        Инициализация модуля интеграции.
        
        Args:
            api_key (str, optional): API ключ для HubSpot. Если не указан, 
                                     будет взят из переменной окружения HUBSPOT_API_KEY.
            use_integration (bool): Флаг для включения/отключения интеграции.
            max_age_months (int): Максимальный возраст описания в месяцах.
        """
        self.use_integration = use_integration
        self.adapter = None
        
        if use_integration:
            # Используем динамический импорт для избежания циклической зависимости
            from src.integrations.hubspot.adapter import HubSpotAdapter
            self.adapter = HubSpotAdapter(api_key=api_key, max_age_months=max_age_months)
            logger.info(f"HubSpot integration initialized with max age: {max_age_months} months")
        else:
            logger.info("HubSpot integration disabled")
    
    async def get_company_data(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Получение данных о компании из HubSpot.
        
        Args:
            domain (str): Домен компании
            
        Returns:
            Optional[Dict[str, Any]]: Данные о компании или None, если не найдена
        """
        if not self.use_integration or self.adapter is None:
            return None
            
        has_description, company_data = await self.adapter.check_company_description("Unknown", domain)
        
        if not company_data:
            return None
            
        # Форматируем данные для использования в пайплайне
        description, timestamp = self.adapter.get_description_from_company(company_data)
        properties = company_data.get("properties", {})
        
        return {
            "description": description,
            "timestamp": timestamp,
            "name": properties.get("name"),
            "hubspot_id": company_data.get("id")
        }
    
    async def should_process_company(self, domain: str) -> bool:
        """
        Проверка необходимости обработки компании.
        
        Args:
            domain (str): Домен компании
            
        Returns:
            bool: True если компания должна быть обработана, иначе False
        """
        # Если интеграция отключена, всегда обрабатываем компанию
        if not self.use_integration or self.adapter is None:
            return True
        
        # Проверяем наличие URL
        if not domain:
            logger.info(f"No domain provided, company should be processed")
            return True
        
        # Проверяем наличие актуального описания в HubSpot
        has_description, _ = await self.adapter.check_company_description("Unknown", domain)
        
        # Если описание не найдено или устарело, обрабатываем компанию
        return not has_description
    
    async def save_company_description(self, company_name: str, domain: str, description: str) -> bool:
        """
        Сохранение описания компании в HubSpot.
        
        Args:
            company_name (str): Название компании
            domain (str): Домен компании
            description (str): Описание компании для сохранения
            
        Returns:
            bool: True в случае успешного сохранения, иначе False
        """
        if not self.use_integration or self.adapter is None:
            logger.info(f"HubSpot integration disabled, not saving description for '{company_name}'")
            return False
        
        # Проверяем существование компании
        has_description, company_data = await self.adapter.check_company_description(company_name, domain)
        
        return await self.adapter.save_company_description(company_data, company_name, domain, description)


async def process_companies_with_hubspot(
    companies: List[Dict[str, str]],
    process_function,
    use_hubspot: bool = True,
    max_age_months: int = 6,
    api_key: Optional[str] = None
):
    """
    Обработка списка компаний с интеграцией HubSpot.
    
    Args:
        companies (List[Dict[str, str]]): Список компаний для обработки
        process_function: Функция для обработки компании
        use_hubspot (bool): Флаг для включения/отключения интеграции HubSpot
        max_age_months (int): Максимальный возраст описания в месяцах
        api_key (Optional[str]): API ключ для HubSpot
        
    Returns:
        List[Dict[str, Any]]: Результаты обработки компаний
    """
    # Инициализация интеграции HubSpot
    hubspot = HubSpotIntegrationService(
        api_key=api_key,
        use_integration=use_hubspot,
        max_age_months=max_age_months
    )
    
    results = []
    
    for company in companies:
        company_name = company.get("name", "")
        url = company.get("url", "")
        
        logger.info(f"Processing company: {company_name}")
        
        # Проверяем необходимость обработки
        should_process = await hubspot.should_process_company(url)
        
        if not should_process:
            # Используем существующее описание из HubSpot
            company_data = await hubspot.get_company_data(url)
            
            result = {
                "Company_Name": company_name,
                "Official_Website": url,
                "Description": company_data.get("description", ""),
                "Timestamp": company_data.get("timestamp", ""),
                "Data_Source": "HubSpot"
            }
            
            logger.info(f"Using existing description for '{company_name}' from HubSpot")
            results.append(result)
        else:
            # Обрабатываем компанию стандартным способом
            logger.info(f"Processing '{company_name}' using standard pipeline")
            
            try:
                # Вызываем функцию обработки
                process_result = await process_function(company_name, url)
                
                # Сохраняем результат в HubSpot
                if process_result and "Description" in process_result:
                    await hubspot.save_company_description(
                        company_name, 
                        url, 
                        process_result["Description"]
                    )
                    process_result["Data_Source"] = "Generated + HubSpot"
                
                results.append(process_result)
            except Exception as e:
                logger.error(f"Error processing company '{company_name}': {e}", exc_info=True)
                results.append({
                    "Company_Name": company_name,
                    "Official_Website": url,
                    "Error": str(e),
                    "Status": "Failed"
                })
    
    return results


async def test_integration():
    """
    Тестирование интеграции с HubSpot.
    """
    companies = [
        {"name": "Example Company", "url": "example.com"},
        {"name": "Test Company", "url": "test-company.com"}
    ]
    
    async def mock_process(company_name, url):
        """
        Мок-функция для обработки компании.
        """
        print(f"Processing {company_name} ({url})...")
        return {
            "Company_Name": company_name,
            "Official_Website": url,
            "Description": f"This is a test description for {company_name}.",
            "Timestamp": datetime.now().isoformat()
        }
    
    results = await process_companies_with_hubspot(
        companies=companies,
        process_function=mock_process,
        use_hubspot=True
    )
    
    for result in results:
        print(f"Result for {result['Company_Name']}:")
        for key, value in result.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(test_integration()) 