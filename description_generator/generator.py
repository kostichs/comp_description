import json
import logging
from typing import List, Dict, Any, Optional, Union
from openai import AsyncOpenAI

from description_generator.config import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    DEFAULT_MODEL_CONFIG
)
from description_generator.schemas import (
    COMPANY_PROFILE_SCHEMA, 
    BASIC_INFO_SCHEMA,
    PRODUCT_TECH_SCHEMA,
    MARKET_CUSTOMER_SCHEMA,
    FINANCIAL_HR_SCHEMA,
    STRATEGIC_SCHEMA,
    extract_data_with_schema,
    generate_text_summary_from_json_async
)

# Настройка логирования
logger = logging.getLogger(__name__)

class DescriptionGenerator:
    """
    Генератор описаний компаний, используя данные, собранные финдерами,
    и OpenAI модель для создания структурированных, информативных текстов.
    """
    
    def __init__(self, api_key: str, model_config: Dict[str, Any] = None):
        """
        Инициализирует генератор описаний с API ключом для OpenAI.
        
        Args:
            api_key: API ключ для OpenAI
            model_config: Конфигурация модели (по умолчанию DEFAULT_MODEL_CONFIG)
        """
        self.api_key = api_key
        self.client = AsyncOpenAI(api_key=api_key)
        self.model_config = model_config or DEFAULT_MODEL_CONFIG
        
    async def generate_description(self, company_name: str, findings: List[Dict[str, Any]]) -> Union[Dict[str, Any], str]:
        """
        Генерирует структурированное описание компании на основе найденных данных.
        
        Args:
            company_name: Название компании
            findings: Список результатов от различных финдеров
            
        Returns:
            Union[Dict[str, Any], str]: Структурированное описание компании или сообщение об ошибке
        """
        # Собираем все найденные данные в единый текст
        text_source = self._prepare_text_source(company_name, findings)
        
        # Если у нас недостаточно данных, возвращаем сообщение об ошибке
        if not text_source:
            return f"Insufficient data to generate description for {company_name}."
        
        # Генерируем структурированные данные и описание компании
        try:
            # Шаг 1: Извлекаем структурированные данные по полной схеме
            llm_config = {
                "model": self.model_config.get("model", "gpt-3.5-turbo"),
                "temperature": 0.1,  # Низкая температура для более точного извлечения фактов
                "max_tokens_json_extract": 4000  # Больше токенов для сложной схемы
            }
            
            # Извлекаем данные для каждой под-схемы
            basic_info = await extract_data_with_schema(
                company_name, 
                text_source, 
                BASIC_INFO_SCHEMA, 
                "basic_info", 
                llm_config, 
                self.client
            )
            
            product_tech = await extract_data_with_schema(
                company_name, 
                text_source, 
                PRODUCT_TECH_SCHEMA, 
                "product_tech", 
                llm_config, 
                self.client
            )
            
            market_customer = await extract_data_with_schema(
                company_name, 
                text_source, 
                MARKET_CUSTOMER_SCHEMA, 
                "market_customer", 
                llm_config, 
                self.client
            )
            
            financial_hr = await extract_data_with_schema(
                company_name, 
                text_source, 
                FINANCIAL_HR_SCHEMA, 
                "financial_hr", 
                llm_config, 
                self.client
            )
            
            strategic = await extract_data_with_schema(
                company_name, 
                text_source, 
                STRATEGIC_SCHEMA, 
                "strategic", 
                llm_config, 
                self.client
            )
            
            # Объединяем все данные в единую структуру
            structured_data = {
                # Basic Info
                "company_name": basic_info.get("company_name", company_name),
                "founding_year": basic_info.get("founding_year"),
                "headquarters_city": basic_info.get("headquarters_city"),
                "headquarters_country": basic_info.get("headquarters_country"),
                "founders": basic_info.get("founders", []),
                "ownership_background": basic_info.get("ownership_background"),
                
                # Product Tech
                "core_products_services": product_tech.get("core_products_services", []),
                "underlying_technologies": product_tech.get("underlying_technologies", []),
                
                # Market Customer
                "customer_types": market_customer.get("customer_types", []),
                "industries_served": market_customer.get("industries_served", []),
                "geographic_markets": market_customer.get("geographic_markets", []),
                
                # Financial HR
                "financial_details": financial_hr.get("financial_details"),
                "employee_count_details": financial_hr.get("employee_count_details"),
                
                # Strategic
                "major_clients_or_case_studies": strategic.get("major_clients_or_case_studies", []),
                "strategic_initiatives": strategic.get("strategic_initiatives", []),
                "key_competitors_mentioned": strategic.get("key_competitors_mentioned", []),
                "overall_summary": strategic.get("overall_summary")
            }
            
            # Шаг 2: Генерируем текстовое описание из структурированных данных
            summary_llm_config = {
                "model": self.model_config.get("model", "gpt-3.5-turbo"),
                "temperature": self.model_config.get("temperature", 0.5),
                "max_tokens_for_summary": self.model_config.get("max_tokens", 1000)
            }
            
            description = await generate_text_summary_from_json_async(
                company_name,
                structured_data,
                self.client,
                summary_llm_config
            )
            
            # Создаем упрощенную версию для совместимости с frontend
            simplified_result = {
                "company_name": structured_data.get("company_name", company_name),
                "founding_year": str(structured_data.get("founding_year")) if structured_data.get("founding_year") else None,
                "headquarters_location": self._format_headquarters(
                    structured_data.get("headquarters_city"), 
                    structured_data.get("headquarters_country")
                ),
                "industry": self._get_main_industry(structured_data.get("industries_served", [])),
                "main_products_services": self._format_products_services(structured_data.get("core_products_services", [])),
                "employees_count": self._format_employees(structured_data.get("employee_count_details")),
                "description": description
            }
            
            # Сохраняем полные данные для доступа
            simplified_result["full_structured_data"] = structured_data
            
            return simplified_result
        except Exception as e:
            logger.error(f"Error generating structured description for {company_name}: {e}")
            return f"Failed to generate description for {company_name}: {str(e)}"
    
    async def generate_batch_descriptions(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Генерирует описания для списка результатов поиска компаний.
        
        Args:
            results: Список результатов поиска компаний
            
        Returns:
            list: Список результатов с добавленными описаниями
        """
        enriched_results = []
        
        for i, result in enumerate(results):
            print(f"Generating description for company {i+1}/{len(results)}: {result.get('company', 'Unknown company')}")
            
            if result.get("successful"):
                # Получаем структурированный результат
                structured_result = await self.generate_description(
                    result["company"], 
                    result["results"]
                )
                
                # Если результат - строка, значит произошла ошибка
                if isinstance(structured_result, str):
                    result["description"] = structured_result
                    result["structured_data"] = None
                else:
                    # Извлекаем текстовое описание из структурированного результата
                    result["description"] = structured_result.get("description", "No description generated.")
                    # Сохраняем структурированные данные
                    result["structured_data"] = structured_result
            else:
                result["description"] = f"Insufficient data to generate description for {result['company']}."
                result["structured_data"] = None
                
            enriched_results.append(result)
            
        return enriched_results
    
    def _prepare_text_source(self, company_name: str, findings: List[Dict[str, Any]]) -> str:
        """
        Подготавливает текстовый источник для генерации описания из найденных данных.
        
        Args:
            company_name: Название компании
            findings: Список результатов от различных финдеров
            
        Returns:
            str: Текстовый источник для генерации описания
        """
        # Извлекаем различные типы данных
        homepage_url = None
        linkedin_url = None
        linkedin_snippet = None
        llm_deep_search_report = None
        
        # Проходим по всем результатам и извлекаем нужные данные
        for finding in findings:
            source = finding.get("source", "")
            result = finding.get("result")
            
            if not result:
                continue
                
            if source == "llm_deep_search":
                llm_deep_search_report = result
            elif source == "linkedin_finder":
                linkedin_url = result
                linkedin_snippet = finding.get("snippet")
            elif "homepage_finder" not in source and not homepage_url:
                homepage_url = result
        
        # Собираем все данные в единый текст
        text_parts = []
        
        # Добавляем основную информацию о компании
        text_parts.append(f"Company Information: {company_name}")
        
        if homepage_url:
            text_parts.append(f"Official Website: {homepage_url}")
            
        if linkedin_url:
            text_parts.append(f"LinkedIn: {linkedin_url}")
            
        if linkedin_snippet:
            text_parts.append(f"LinkedIn Description: {linkedin_snippet}")
        
        # Если есть отчет от LLM Deep Search, добавляем его как основной источник данных
        if llm_deep_search_report:
            text_parts.append("--- Detailed Report ---")
            text_parts.append(llm_deep_search_report)
        
        # Объединяем все части в единый текст
        return "\n\n".join(text_parts)

    def _format_headquarters(self, city: Optional[str], country: Optional[str]) -> Optional[str]:
        """Форматирует местоположение штаб-квартиры компании."""
        if city and country:
            return f"{city}, {country}"
        elif city:
            return city
        elif country:
            return country
        return None
        
    def _get_main_industry(self, industries: List[str]) -> Optional[str]:
        """Возвращает основную отрасль компании из списка отраслей."""
        if not industries or len(industries) == 0:
            return None
        return industries[0]
        
    def _format_products_services(self, products_services: List[Dict[str, Any]]) -> Optional[str]:
        """Форматирует список продуктов/услуг компании в текстовое описание."""
        if not products_services or len(products_services) == 0:
            return None
            
        product_names = [p.get("name") for p in products_services if p.get("name")]
        if not product_names:
            return None
            
        if len(product_names) == 1:
            return product_names[0]
        elif len(product_names) == 2:
            return f"{product_names[0]} and {product_names[1]}"
        else:
            return f"{', '.join(product_names[:-1])}, and {product_names[-1]}"
            
    def _format_employees(self, employee_details: Optional[Dict[str, Any]]) -> Optional[str]:
        """Форматирует данные о количестве сотрудников компании."""
        if not employee_details:
            return None
            
        count = employee_details.get("count")
        year = employee_details.get("year_reported")
        
        if not count:
            return None
            
        if year:
            return f"{count} employees (as of {year})"
        else:
            return f"{count} employees" 