"""
Модуль для проверки качества описаний компаний перед записью в HubSpot
"""

import logging
import re
from typing import Dict, Any, Tuple, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class DescriptionQualityChecker:
    """
    Класс для проверки качества описаний компаний перед записью в HubSpot.
    
    Включает различные методы валидации:
    - Проверка на шаблонные фразы неудачных поисков
    - Анализ структуры описания
    - LLM-валидация качества (опционально)
    """
    
    def __init__(self, openai_client: Optional[AsyncOpenAI] = None, use_llm_validation: bool = False, 
                 min_description_length: int = 500):
        """
        Инициализация проверки качества.
        
        Args:
            openai_client: Клиент OpenAI для LLM-валидации (опционально)
            use_llm_validation: Использовать ли LLM для дополнительной валидации
            min_description_length: Минимальная длина описания в символах
        """
        self.openai_client = openai_client
        self.use_llm_validation = use_llm_validation
        self.min_description_length = min_description_length
        
        # Фразы, указывающие на неудачный поиск
        self.failure_patterns = [
            # Полная неудача поиска
            r"unable to locate any information",
            r"could not locate any specific information",
            r"i was unable to find any information",
            r"after an extensive search.*unable to",
            r"after conducting a thorough search.*could not",
            r"no specific information.*could be found",
            r"i could not find any reliable information",
            
            # Найдены только похожие компании
            r"however.*found details on several organizations with similar names",
            r"however.*i found.*organizations.*similar names",
            r"found.*companies with similar names",
            r"several organizations.*similar names.*might be relevant",
            
            # Просьбы о дополнительной информации
            r"if you can provide additional details",
            r"if you can provide more specific details",
            r"please provide more information",
            r"could you clarify",
            r"i'd be happy to assist further",
            
            # Общие шаблонные фразы
            r"it's possible that the company operates under a different name",
            r"is a private entity with limited public information",
            r"smaller or newer organization without.*online presence",
            r"limited public information available",
        ]
        
        # Минимальные требования к качественному описанию (перенесены в __init__)
        self.required_sections = [
            "company",  # Упоминание о компании
            "business", # Информация о бизнесе
        ]
        
    def check_description_quality(self, description: str, company_name: str = "") -> Tuple[bool, str, Dict[str, Any]]:
        """
        Основная функция проверки качества описания.
        
        Args:
            description: Текст описания компании
            company_name: Название компании (для контекста)
            
        Returns:
            Tuple[bool, str, Dict[str, Any]]: 
                - is_good_quality: True если описание качественное
                - reason: Причина решения
                - details: Дополнительные детали проверки
        """
        if not description or not description.strip():
            return False, "Empty description", {"length": 0}
        
        details = {
            "length": len(description),
            "company_name": company_name
        }
        
        # 1. Проверка на фразы неудачного поиска
        failure_check = self._check_failure_patterns(description)
        if not failure_check[0]:
            details["failure_patterns"] = failure_check[2]
            return False, f"Contains failure patterns: {failure_check[1]}", details
        
        # 2. Проверка длины описания
        if len(description) < self.min_description_length:
            return False, f"Description too short: {len(description)} < {self.min_description_length}", details
        
        # 3. Проверка структуры описания
        structure_check = self._check_description_structure(description)
        details["structure"] = structure_check[2]
        if not structure_check[0]:
            return False, f"Poor structure: {structure_check[1]}", details
        
        # 4. Проверка на информативность
        info_check = self._check_information_content(description, company_name)
        details["information"] = info_check[2]
        if not info_check[0]:
            return False, f"Low information content: {info_check[1]}", details
        
        return True, "Good quality description", details
    
    def _check_failure_patterns(self, description: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Проверка на паттерны неудачного поиска.
        """
        description_lower = description.lower()
        found_patterns = []
        
        for pattern in self.failure_patterns:
            if re.search(pattern, description_lower, re.IGNORECASE | re.MULTILINE):
                found_patterns.append(pattern)
        
        details = {
            "found_patterns": found_patterns,
            "total_patterns_checked": len(self.failure_patterns)
        }
        
        if found_patterns:
            return False, f"Found {len(found_patterns)} failure patterns", details
        
        return True, "No failure patterns found", details
    
    def _check_description_structure(self, description: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Проверка структуры описания.
        """
        lines = description.split('\n')
        non_empty_lines = [line.strip() for line in lines if line.strip()]
        
        # Проверяем количество параграфов/секций
        paragraphs = description.split('\n\n')
        meaningful_paragraphs = [p.strip() for p in paragraphs if len(p.strip()) > 50]
        
        # Проверяем наличие заголовков/структуры
        has_headers = any(line.startswith('**') or line.startswith('#') or line.endswith(':') 
                         for line in non_empty_lines[:10])  # Проверяем первые 10 строк
        
        # Проверяем наличие списков или структурированной информации
        has_lists = any('- ' in line or '• ' in line or re.match(r'^\d+\.', line.strip()) 
                       for line in non_empty_lines)
        
        details = {
            "total_lines": len(lines),
            "non_empty_lines": len(non_empty_lines),
            "paragraphs": len(meaningful_paragraphs),
            "has_headers": has_headers,
            "has_lists": has_lists
        }
        
        # Минимальные требования к структуре
        if len(meaningful_paragraphs) < 2:
            return False, "Too few meaningful paragraphs", details
        
        if not (has_headers or has_lists):
            return False, "No clear structure (headers or lists)", details
        
        return True, "Good structure", details
    
    def _check_information_content(self, description: str, company_name: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Проверка информативности описания.
        """
        description_lower = description.lower()
        company_name_lower = company_name.lower() if company_name else ""
        
        # Ключевые категории информации, которые должны присутствовать
        info_categories = {
            "company_identity": [
                "company", "organization", "business", "corporation", "firm", "enterprise",
                company_name_lower
            ],
            "products_services": [
                "product", "service", "solution", "platform", "software", "technology",
                "offer", "provide", "deliver", "develop"
            ],
            "business_details": [
                "industry", "market", "customer", "client", "revenue", "employee", "staff",
                "founded", "headquarter", "location", "office"
            ],
            "specific_info": [
                "website", "url", "domain", "linkedin", "contact", "phone", "email",
                "address", "year", "million", "billion", "$"
            ]
        }
        
        category_scores = {}
        total_score = 0
        
        for category, keywords in info_categories.items():
            found_keywords = []
            for keyword in keywords:
                if keyword and keyword in description_lower:
                    found_keywords.append(keyword)
            
            category_score = len(found_keywords) / len(keywords) if keywords else 0
            category_scores[category] = {
                "score": category_score,
                "found_keywords": found_keywords,
                "total_keywords": len(keywords)
            }
            total_score += category_score
        
        avg_score = total_score / len(info_categories)
        
        details = {
            "avg_information_score": avg_score,
            "category_scores": category_scores,
            "min_required_score": 0.3
        }
        
        # Требуем минимальный уровень информативности
        if avg_score < 0.3:  # 30% релевантных ключевых слов
            return False, f"Low information score: {avg_score:.2f}", details
        
        # Проверяем что есть упоминания компании
        if category_scores["company_identity"]["score"] < 0.2:
            return False, "No clear company identification", details
        
        return True, f"Good information content: {avg_score:.2f}", details
    
    async def llm_quality_check(self, description: str, company_name: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Дополнительная проверка качества с помощью LLM.
        
        Args:
            description: Описание компании
            company_name: Название компании
            
        Returns:
            Tuple[bool, str, Dict]: Результат LLM проверки
        """
        if not self.openai_client or not self.use_llm_validation:
            return True, "LLM validation disabled", {"llm_used": False}
        
        try:
            prompt = f"""
Analyze the following company description for quality and completeness. 
Company name: {company_name}

Description to analyze:
{description}

Please evaluate:
1. Is this a proper company description or an error message?
2. Does it contain meaningful business information?
3. Is it informative and useful for a CRM system?

Respond with JSON format:
{{
    "is_good_quality": true/false,
    "confidence": 0.0-1.0,
    "issues": ["list of issues if any"],
    "summary": "brief explanation"
}}
"""
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Используем более дешевую модель для валидации
                messages=[
                    {"role": "system", "content": "You are a quality control expert for business descriptions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content
            
            # Пытаемся парсить JSON ответ
            import json
            try:
                result_json = json.loads(result_text)
                is_good = result_json.get("is_good_quality", True)
                confidence = result_json.get("confidence", 0.5)
                issues = result_json.get("issues", [])
                summary = result_json.get("summary", "")
                
                details = {
                    "llm_used": True,
                    "confidence": confidence,
                    "issues": issues,
                    "full_response": result_json
                }
                
                return is_good, summary, details
                
            except json.JSONDecodeError:
                # Если не удалось парсить JSON, анализируем текст
                is_good = "true" in result_text.lower() or "good" in result_text.lower()
                return is_good, result_text[:100], {"llm_used": True, "raw_response": result_text}
                
        except Exception as e:
            logger.error(f"Error in LLM quality check: {e}")
            return True, f"LLM error: {str(e)}", {"llm_used": True, "error": str(e)}


def should_write_to_hubspot(description: str, company_name: str = "", 
                           openai_client: Optional[AsyncOpenAI] = None,
                           use_llm_validation: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Convenience function для быстрой проверки качества описания.
    
    Args:
        description: Текст описания
        company_name: Название компании  
        openai_client: OpenAI клиент для LLM валидации
        use_llm_validation: Использовать ли LLM для проверки
        
    Returns:
        Tuple[bool, str, Dict]: Можно ли записывать, причина, детали
    """
    checker = DescriptionQualityChecker(openai_client, use_llm_validation)
    return checker.check_description_quality(description, company_name)


async def should_write_to_hubspot_async(description: str, company_name: str = "", 
                                       openai_client: Optional[AsyncOpenAI] = None,
                                       use_llm_validation: bool = False,
                                       min_description_length: int = 500) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Асинхронная версия проверки качества с опциональной LLM валидацией.
    
    Args:
        description: Текст описания
        company_name: Название компании  
        openai_client: OpenAI клиент для LLM валидации
        use_llm_validation: Использовать ли LLM для проверки
        min_description_length: Минимальная длина описания в символах
        
    Returns:
        Tuple[bool, str, Dict]: Можно ли записывать, причина, детали
    """
    checker = DescriptionQualityChecker(openai_client, use_llm_validation, min_description_length)
    
    # Основная проверка
    is_good, reason, details = checker.check_description_quality(description, company_name)
    
    # Если основная проверка прошла и включена LLM валидация
    if is_good and use_llm_validation and openai_client:
        llm_result = await checker.llm_quality_check(description, company_name)
        details["llm_validation"] = llm_result[2]
        
        # Если LLM считает описание плохим, отклоняем
        if not llm_result[0]:
            return False, f"LLM validation failed: {llm_result[1]}", details
    
    return is_good, reason, details 