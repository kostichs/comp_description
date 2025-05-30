import json
import logging
import traceback
import time
import httpx
import re
import yaml
import os
from typing import List, Dict, Any, Optional, Union
from openai import AsyncOpenAI
from dotenv import load_dotenv

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

# Configure logging
logger = logging.getLogger(__name__)

# Load API keys from .env
load_dotenv()

# Use API key directly from environment variables if not passed in constructor
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class DescriptionGenerator:
    """
    Company description generator that uses data collected by finders
    and OpenAI model to create structured, informative descriptions.
    """
    
    def __init__(self, api_key: str, model_config: Dict[str, Any] = None):
        """
        Initialize description generator with API key and optional model configuration.
        
        Args:
            api_key: OpenAI API key
            model_config: Model configuration (optional)
        """
        self.api_key = api_key
        self.client = AsyncOpenAI(api_key=api_key)
        self.model_config = model_config or DEFAULT_MODEL_CONFIG
        
    async def generate_description(self, company_name: str, findings: list) -> Union[dict, str]:
        """
        Генерирует структурированное описание компании на основе собранных данных.
        
        Args:
            company_name: Название компании
            findings: Список найденных данных о компании
            
        Returns:
            Union[dict, str]: Структурированное описание компании или сообщение об ошибке
        """
        # Обработка и подготовка входных данных
        sources_text = ""
        llm_deep_search_report = None
        
        # Проверяем, есть ли среди находок отчет от LLMDeepSearchFinder
        for finding in findings:
            if isinstance(finding, dict) and finding.get("source") == "llm_deep_search" and finding.get("result"):
                llm_deep_search_report = finding.get("result")
                logger.info(f"Найден отчет LLMDeepSearch ({len(llm_deep_search_report)} символов)")
                break
        
        # Собираем все результаты в один текст
        for finding in findings:
            if isinstance(finding, str):
                sources_text += finding + "\n\n"
            elif isinstance(finding, dict) and finding.get("result"):
                result = finding.get("result")
                # Проверяем тип result
                if isinstance(result, str):
                    sources_text += result + "\n\n"
                elif isinstance(result, dict):
                    # Если словарь, то конвертируем в строку JSON
                    sources_text += json.dumps(result, ensure_ascii=False) + "\n\n"
                else:
                    # Для других типов преобразуем в строку
                    sources_text += str(result) + "\n\n"
        
        # Если есть отчет от LLMDeepSearchFinder, добавляем его в начало для приоритета
        if llm_deep_search_report:
            sources_text = llm_deep_search_report + "\n\n---\n\n" + sources_text
            
        if not sources_text:
            error_msg = f"Недостаточно данных для генерации описания компании {company_name}"
            logger.error(error_msg)
            return error_msg
        
        # Обрезаем слишком длинный текст
        max_text_length = 32000  # максимальная длина текста для обработки
        if len(sources_text) > max_text_length:
            logger.warning(f"Текст слишком длинный ({len(sources_text)} символов), обрезаем до {max_text_length}")
            sources_text = sources_text[:max_text_length]
        
        try:
            # Шаг 1: Извлекаем структурированные данные из текста по схеме
            structured_data = await extract_data_with_schema(
                company_name=company_name,
                about_snippet=sources_text,
                sub_schema=COMPANY_PROFILE_SCHEMA,
                schema_name="COMPANY_PROFILE_SCHEMA",
                llm_config=self.model_config,
                openai_client=self.client
            )
            
            if not structured_data or isinstance(structured_data, str) or structured_data.get("error"):
                error_msg = f"Не удалось извлечь структурированные данные для компании {company_name}. Результат: {structured_data}"
                logger.error(error_msg)
                return structured_data if isinstance(structured_data, dict) and structured_data.get("error") else error_msg
            
            # Шаг 2: Генерируем текстовое описание на основе структурированных данных
            description = await generate_text_summary_from_json_async(
                structured_data=structured_data,
                company_name=company_name,
                openai_client=self.client,
                llm_config=self.model_config
            )
            
            # Возвращаем результат в виде словаря с описанием и структурированными данными
            result = {
                "description": description,
                **structured_data  # Добавляем все поля структурированных данных в корень объекта
            }
            
            return result
            
        except Exception as e:
            error_msg = f"Ошибка при генерации описания для компании {company_name}: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return error_msg
    
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
        login_detection_result = None
        
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
            elif source == "login_detection_finder":
                login_detection_result = result
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
        
        # Добавляем информацию о логин-системе, если она есть
        if login_detection_result:
            text_parts.append("--- Login System Information ---")
            if isinstance(login_detection_result, dict):
                has_user_portal = login_detection_result.get("has_user_portal", False)
                has_transaction_interface = login_detection_result.get("has_transaction_interface", False)
                has_dashboard = login_detection_result.get("has_dashboard", False)
                description = login_detection_result.get("description", "")
                
                text_parts.append(f"User Portal Available: {'Yes' if has_user_portal else 'No'}")
                text_parts.append(f"Transaction Interface Available: {'Yes' if has_transaction_interface else 'No'}")
                text_parts.append(f"Dashboard Available: {'Yes' if has_dashboard else 'No'}")
                if description:
                    text_parts.append(f"Description: {description}")
            else:
                text_parts.append(str(login_detection_result))
        
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