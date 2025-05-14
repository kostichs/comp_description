import json
import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI

from description_generator.config import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    DEFAULT_MODEL_CONFIG
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
        
    async def generate_description(self, company_name: str, findings: List[Dict[str, Any]]) -> str:
        """
        Генерирует описание компании на основе найденных данных.
        
        Args:
            company_name: Название компании
            findings: Список результатов от различных финдеров
            
        Returns:
            str: Сгенерированное описание компании
        """
        # Собираем все найденные данные в единый текст
        text_source = self._prepare_text_source(company_name, findings)
        
        # Если у нас недостаточно данных, возвращаем сообщение об ошибке
        if not text_source:
            return f"Insufficient data to generate description for {company_name}."
        
        # Генерируем описание компании
        try:
            description = await self._generate_summary_from_text(company_name, text_source)
            return description
        except Exception as e:
            logger.error(f"Error generating description for {company_name}: {e}")
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
                description = await self.generate_description(
                    result["company"], 
                    result["results"]
                )
                result["description"] = description
            else:
                result["description"] = f"Insufficient data to generate description for {result['company']}."
                
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
    
    async def _generate_summary_from_text(self, company_name: str, text_source: str) -> str:
        """
        Генерирует краткое описание компании из текстового источника.
        
        Args:
            company_name: Название компании
            text_source: Текстовый источник для генерации описания
            
        Returns:
            str: Сгенерированное описание компании
        """
        # Формируем пользовательский промпт с данными о компании
        user_prompt = USER_PROMPT_TEMPLATE.format(
            company_name=company_name,
            text_source=text_source
        )

        # Вызов API OpenAI для генерации описания
        response = await self.client.chat.completions.create(
            model=self.model_config.get("model", "gpt-3.5-turbo"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=self.model_config.get("temperature", 0.5),
            max_tokens=self.model_config.get("max_tokens", 1000)
        )
        
        # Извлекаем текст ответа и возвращаем его
        if response.choices and response.choices[0].message:
            description = response.choices[0].message.content.strip()
            return description
        else:
            return "Failed to generate description." 