import os
import logging
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv

# Импортируем модуль интеграции HubSpot
from hubspot_integration import HubSpotIntegration

# Настройка логирования
logger = logging.getLogger(__name__)

class PipelineHubSpotIntegrator:
    """
    Адаптер для интеграции HubSpot с существующим пайплайном.
    
    Этот класс может быть легко встроен в существующий код обработки компаний,
    добавляя функционал проверки и сохранения описаний в HubSpot.
    """
    
    def __init__(self, 
                 api_key: Optional[str] = None, 
                 use_hubspot: bool = True,
                 max_age_months: int = 6):
        """
        Инициализация адаптера.
        
        Args:
            api_key (str, optional): API ключ для HubSpot. Если не указан, 
                                     будет взят из переменной окружения HUBSPOT_API_KEY.
            use_hubspot (bool): Флаг для включения/отключения интеграции.
            max_age_months (int): Максимальный возраст описания в месяцах.
        """
        # Загружаем переменные окружения, если api_key не передан
        if api_key is None:
            load_dotenv()
            api_key = os.getenv("HUBSPOT_API_KEY")
        
        self.hubspot = HubSpotIntegration(
            api_key=api_key,
            use_integration=use_hubspot,
            max_age_months=max_age_months
        )
        
        self.use_hubspot = use_hubspot
        logger.info(f"Pipeline HubSpot Integrator initialized. Integration enabled: {use_hubspot}")
    
    async def check_company_before_processing(self, company_name: str, url: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
        """
        Проверка компании перед обработкой.
        
        Args:
            company_name (str): Название компании
            url (str): URL компании
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
                - Первый элемент: True если компанию нужно обрабатывать, иначе False
                - Второй элемент: Данные о компании из HubSpot, если найдена
                - Третий элемент: Существующее описание, если найдено и актуально
        """
        if not self.use_hubspot:
            return True, None, None
        
        # Проверяем наличие актуального описания в HubSpot
        should_process, company_data = await self.hubspot.should_process_company(company_name, url)
        
        existing_description = None
        if not should_process and company_data:
            # Получаем существующее описание
            existing_description = self.hubspot.get_existing_description(company_data)
        
        return should_process, company_data, existing_description
    
    async def save_description_to_hubspot(self, 
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
        if not self.use_hubspot:
            return False
        
        # Если компания уже найдена, обновляем её
        if company_data:
            return await self.hubspot.save_description(company_data, company_name, url, description)
        else:
            # Иначе создаём новую компанию
            new_company = await self.hubspot.create_company(company_name, url, description)
            return new_company is not None
    
    async def create_company_in_hubspot(self, 
                                      company_name: str, 
                                      url: str, 
                                      description: str) -> Optional[Dict[str, Any]]:
        """
        Создание новой компании в HubSpot.
        
        Args:
            company_name (str): Название компании
            url (str): URL компании
            description (str): Описание компании
            
        Returns:
            Optional[Dict[str, Any]]: Данные о созданной компании или None в случае ошибки
        """
        if not self.use_hubspot:
            return None
        
        return await self.hubspot.create_company(company_name, url, description)


# Пример интеграции с существующим пайплайном
async def integrate_with_existing_pipeline(input_file_path: str, 
                                         output_csv_path: str,
                                         use_hubspot: bool = True,
                                         hubspot_api_key: Optional[str] = None,
                                         max_age_months: int = 6,
                                         **pipeline_params):
    """
    Интеграция HubSpot с существующим пайплайном обработки компаний.
    
    Args:
        input_file_path (str): Путь к входному файлу с компаниями
        output_csv_path (str): Путь к выходному CSV файлу
        use_hubspot (bool): Флаг для включения/отключения интеграции HubSpot
        hubspot_api_key (Optional[str]): API ключ для HubSpot
        max_age_months (int): Максимальный возраст описания в месяцах
        **pipeline_params: Дополнительные параметры для пайплайна
        
    Returns:
        List[Dict[str, Any]]: Результаты обработки компаний
    """
    # Код для загрузки компаний из входного файла
    # В реальном коде этот метод будет использовать существующие функции загрузки данных
    # Пример:
    # companies = load_companies_from_file(input_file_path)
    
    # Для примера создадим тестовые данные
    companies = [
        {"name": "Example Inc.", "url": "https://example.com"},
        {"name": "Test Company", "url": "https://test-company.com"}
    ]
    
    # Инициализация интегратора HubSpot
    hubspot_integrator = PipelineHubSpotIntegrator(
        api_key=hubspot_api_key,
        use_hubspot=use_hubspot,
        max_age_months=max_age_months
    )
    
    results = []
    
    # Обработка каждой компании
    for company in companies:
        company_name = company["name"]
        url = company["url"]
        
        logger.info(f"Processing company: {company_name}")
        
        # Проверка компании в HubSpot перед обработкой
        should_process, company_data, existing_description = await hubspot_integrator.check_company_before_processing(
            company_name, url
        )
        
        if not should_process and existing_description:
            # Используем существующее описание из HubSpot
            logger.info(f"Using existing description for '{company_name}' from HubSpot")
            
            result = {
                "Company_Name": company_name,
                "Official_Website": url,
                "Description": existing_description["description"],
                "Timestamp": existing_description["timestamp"],
                "Data_Source": "HubSpot"
            }
            
            results.append(result)
            
            # Код для сохранения результата в CSV
            # save_result_to_csv(result, output_csv_path)
            
            continue
        
        # Если описания нет или оно устарело, обрабатываем компанию стандартным способом
        try:
            # Здесь вызов вашего существующего кода обработки компании
            # Например:
            # process_result = await process_company(company_name, url, **pipeline_params)
            
            # Для примера создадим имитацию результата обработки
            await asyncio.sleep(1)  # Имитация обработки
            process_result = {
                "Company_Name": company_name,
                "Official_Website": url,
                "Description": f"Generated description for {company_name}",
                "Timestamp": "2023-06-15"  # Используем только дату в формате YYYY-MM-DD
            }
            
            # Сохраняем результат в HubSpot
            if process_result and "Description" in process_result:
                saved = await hubspot_integrator.save_description_to_hubspot(
                    company_data,
                    company_name,
                    url,
                    process_result["Description"]
                )
                if saved:
                    logger.info(f"Description for '{company_name}' saved to HubSpot")
                else:
                    logger.warning(f"Failed to save description for '{company_name}' to HubSpot")
            
            # Добавляем метку источника данных
            process_result["Data_Source"] = "Pipeline"
            results.append(process_result)
            
            # Код для сохранения результата в CSV
            # save_result_to_csv(process_result, output_csv_path)
            
        except Exception as e:
            logger.error(f"Error processing company '{company_name}': {e}", exc_info=True)
            # Обработка ошибки
    
    return results


# Пример использования
async def test_pipeline_integration():
    """Тестовая функция для демонстрации интеграции с пайплайном."""
    # Настройка логирования для тестирования
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Запускаем интеграцию
    results = await integrate_with_existing_pipeline(
        input_file_path="example.csv",
        output_csv_path="results.csv",
        use_hubspot=True
    )
    
    # Выводим результаты
    for i, result in enumerate(results):
        print(f"\nResult {i+1}:")
        for key, value in result.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    # Запускаем тестовую функцию при прямом вызове скрипта
    asyncio.run(test_pipeline_integration()) 