import os
import logging
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from hubspot_adapter import HubSpotAdapter

# Настройка логирования
logger = logging.getLogger(__name__)

class HubSpotIntegration:
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
            self.adapter = HubSpotAdapter(api_key=api_key, max_age_months=max_age_months)
            logger.info(f"HubSpot integration initialized with max age: {max_age_months} months")
        else:
            logger.info("HubSpot integration disabled")
    
    async def should_process_company(self, company_name: str, url: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка необходимости обработки компании.
        
        Args:
            company_name (str): Название компании
            url (str): URL компании
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]:
                - Первый элемент: True если компания должна быть обработана, иначе False
                - Второй элемент: Данные о компании из HubSpot, если найдена
        """
        # Если интеграция отключена, всегда обрабатываем компанию
        if not self.use_integration or self.adapter is None:
            return True, None
        
        # Проверяем наличие URL
        if not url:
            logger.info(f"No URL provided for '{company_name}', skipping HubSpot check")
            return True, None
        
        # Проверяем наличие актуального описания в HubSpot
        has_description, company_data = await self.adapter.check_company_description(company_name, url)
        
        # Если описание не найдено или устарело, обрабатываем компанию
        return not has_description, company_data
    
    def get_existing_description(self, company_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Получение существующего описания из данных о компании.
        
        Args:
            company_data (Dict[str, Any]): Данные о компании из HubSpot
            
        Returns:
            Dict[str, str]: Словарь с описанием и временной меткой
        """
        if not self.use_integration or self.adapter is None or not company_data:
            return {"description": "", "timestamp": ""}
        
        description, timestamp = self.adapter.get_description_from_company(company_data)
        return {
            "description": description,
            "timestamp": timestamp,
            "source": "HubSpot"
        }
    
    async def save_description(self, 
                              company_data: Optional[Dict[str, Any]], 
                              company_name: str, 
                              url: str, 
                              description: str) -> bool:
        """
        Сохранение описания компании в HubSpot.
        
        Args:
            company_data (Optional[Dict[str, Any]]): Данные о компании из HubSpot, если уже найдена
            company_name (str): Название компании
            url (str): URL компании
            description (str): Описание компании для сохранения
            
        Returns:
            bool: True в случае успешного сохранения, иначе False
        """
        if not self.use_integration or self.adapter is None:
            logger.info(f"HubSpot integration disabled, not saving description for '{company_name}'")
            return False
        
        return await self.adapter.save_company_description(company_data, company_name, url, description)
    
    async def create_company(self, company_name: str, url: str, description: str) -> Optional[Dict[str, Any]]:
        """
        Создание новой компании в HubSpot.
        
        Args:
            company_name (str): Название компании
            url (str): URL компании
            description (str): Описание компании
            
        Returns:
            Optional[Dict[str, Any]]: Данные о созданной компании в случае успеха, иначе None
        """
        if not self.use_integration or self.adapter is None:
            logger.info(f"HubSpot integration disabled, not creating company '{company_name}'")
            return None
        
        return await self.adapter.create_company(company_name, url, description)


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
    hubspot = HubSpotIntegration(
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
        should_process, company_data = await hubspot.should_process_company(company_name, url)
        
        if not should_process:
            # Используем существующее описание из HubSpot
            existing_data = hubspot.get_existing_description(company_data)
            
            result = {
                "Company_Name": company_name,
                "Official_Website": url,
                "Description": existing_data["description"],
                "Timestamp": existing_data["timestamp"],
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
                    # Если компания уже найдена, обновляем её
                    if company_data:
                        await hubspot.save_description(
                            company_data, 
                            company_name, 
                            url, 
                            process_result["Description"]
                        )
                    # Иначе создаём новую компанию
                    else:
                        await hubspot.create_company(
                            company_name,
                            url,
                            process_result["Description"]
                        )
                
                # Добавляем результат в общий список
                if process_result:
                    process_result["Data_Source"] = "Pipeline"
                    results.append(process_result)
            
            except Exception as e:
                logger.error(f"Error processing company '{company_name}': {e}", exc_info=True)
                # Добавляем информацию об ошибке
                results.append({
                    "Company_Name": company_name,
                    "Official_Website": url,
                    "Description": f"Error: {str(e)}",
                    "Timestamp": datetime.now().strftime("%Y-%m-%d"),
                    "Data_Source": "Error"
                })
    
    return results


# Пример использования
async def test_integration():
    """Тестовая функция для демонстрации интеграции."""
    # Настройка логирования для тестирования
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Тестовые компании
    test_companies = [
        {"name": "Example Inc.", "url": "https://example.com"},
        {"name": "Test Company", "url": "https://test-company.com"},
        {"name": "Company without URL", "url": ""}
    ]
    
    # Функция для имитации обработки
    async def mock_process(company_name, url):
        logger.info(f"Mock processing: {company_name}")
        # Имитация обработки
        await asyncio.sleep(1)
        return {
            "Company_Name": company_name,
            "Official_Website": url,
            "Description": f"This is a generated description for {company_name}.",
            "Timestamp": datetime.now().strftime("%Y-%m-%d")
        }
    
    # Запускаем обработку с интеграцией HubSpot
    results = await process_companies_with_hubspot(
        test_companies,
        mock_process,
        use_hubspot=True
    )
    
    # Выводим результаты
    for i, result in enumerate(results):
        print(f"\nResult {i+1}:")
        for key, value in result.items():
            if key == "Description":
                value = value[:50] + "..." if len(value) > 50 else value
            print(f"  {key}: {value}")


if __name__ == "__main__":
    # Запускаем тестовую функцию при прямом вызове скрипта
    asyncio.run(test_integration()) 