import os
import sys
import logging
import json
from typing import Dict, List, Any, Optional

# Добавляем корневую директорию проекта в путь Python
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from finders.base import Finder
from openai import AsyncOpenAI, APIError, Timeout

class LLMDeepSearchFinder(Finder):
    """
    Финдер, использующий LLM с возможностью поиска в интернете для получения 
    подробной информации о компании.
    
    Использует модель GPT-4o-mini-search-preview или аналогичную, которая может
    искать актуальную информацию в интернете и составлять структурированный отчет.
    """
    
    def __init__(self, openai_api_key: str, verbose: bool = False):
        """
        Инициализирует финдер с API ключом для OpenAI.
        
        Args:
            openai_api_key: API ключ для OpenAI
            verbose: Выводить подробные логи поиска (по умолчанию False)
        """
        self.openai_api_key = openai_api_key
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.verbose = verbose
        self.model = "gpt-4o-mini-search-preview"  # Модель с поддержкой поиска
        
    async def find(self, company_name: str, **context) -> dict:
        """
        Ищет подробную информацию о компании, используя LLM с возможностью поиска в интернете.
        
        Args:
            company_name: Название компании
            context: Словарь с контекстом, может содержать:
                     - 'specific_aspects': список аспектов, которые нужно исследовать
                     - 'user_context': дополнительный контекст от пользователя
                     
        Returns:
            dict: Результат поиска {
                "source": "llm_deep_search", 
                "result": str или None,  # текст отчета
                "sources": list  # список источников в формате [{"title": str, "url": str}, ...]
            }
        """
        specific_aspects = context.get('specific_aspects', self._get_default_aspects())
        user_context = context.get('user_context', None)
        
        if self.verbose:
            print(f"\n--- LLM Deep Search для компании '{company_name}' ---")
            print(f"Модель: {self.model}")
            print(f"Исследуемые аспекты: {len(specific_aspects)} пунктов")
        
        report_dict = await self._query_llm_for_deep_info(
            company_name=company_name,
            specific_aspects_to_cover=specific_aspects,
            user_context_text=user_context
        )
        
        if "error" in report_dict:
            if self.verbose:
                print(f"Ошибка при поиске: {report_dict['error']}")
            return {
                "source": "llm_deep_search", 
                "result": None, 
                "error": report_dict["error"],
                "sources": []
            }
        
        report_text = report_dict.get("report_text", "")
        sources = report_dict.get("sources", [])
        
        if self.verbose:
            print(f"Получен отчет ({len(report_text)} символов) с {len(sources)} источниками")
        else:
            print(f"LLM Deep Search для '{company_name}': получен отчет с {len(sources)} источниками")
            
        return {
            "source": "llm_deep_search", 
            "result": report_text, 
            "sources": sources
        }
    
    def _get_default_aspects(self) -> List[str]:
        """
        Возвращает список аспектов для исследования по умолчанию.
        
        Returns:
            List[str]: Список аспектов
        """
        return [
            "company founding year",
            "headquarters location (city and country)",
            "names of founders",
            "ownership structure (e.g., public, private, VC-backed, parent company)",
            "latest reported annual revenue or ARR (specify currency and year if possible)",
            "approximate number of employees",
            "details of the latest funding round (amount, date, key investors, series - if applicable)",
            "key products, services, or core technologies offered",
            "main competitors identified by reliable sources",
            "primary business segments and target customer focus (e.g., B2C, B2B, B2G)",
            "geographical regions of operation and overall global strategy"
        ]
    
    def _escape_string_for_prompt(self, text: str) -> str:
        """
        Экранирует специальные символы в строке для безопасного вставления в промпт.
        
        Args:
            text: Исходная строка
            
        Returns:
            str: Экранированная строка
        """
        return json.dumps(text)[1:-1]  # Используем json.dumps и удаляем внешние кавычки
    
    async def _query_llm_for_deep_info(
        self,
        company_name: str,
        specific_aspects_to_cover: List[str],
        user_context_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Запрашивает у LLM с поиском подробную информацию о компании.
        
        Args:
            company_name: Название компании
            specific_aspects_to_cover: Список аспектов, которые нужно исследовать
            user_context_text: Дополнительный контекст от пользователя
            
        Returns:
            Dict[str, Any]: Словарь с отчетом и источниками или с ошибкой
        """
        safe_company_name = self._escape_string_for_prompt(company_name)
        
        # Формируем части промпта на основе переданных аспектов
        additional_aspects_str = ""
        if specific_aspects_to_cover:
            escaped_aspects = [self._escape_string_for_prompt(aspect) for aspect in specific_aspects_to_cover]
            additional_aspects_str = "\n\nAdditionally, ensure these specific aspects are thoroughly investigated and included within the relevant sections of your report:\n- " + "\n- ".join(escaped_aspects)
        
        # Добавляем пользовательский контекст, если он есть
        context_injection_str = ""
        if user_context_text:
            safe_user_context = self._escape_string_for_prompt(user_context_text)
            context_injection_str = f"\n\nUser-provided context to guide your research: '{safe_user_context}'"
        
        # Основной шаблон промпта
        prompt_template = """Please generate a detailed Business Analytics Report for the company: '{company_name_placeholder}'.

Your primary goal is to extract and present factual data about the company. 
When reporting financial figures (like revenue, funding), provide the latest available data, clearly stating the period/year each figure refers to.

The report should include the following sections:

1. **Company Overview:**
   * Brief description of what the company does
   * Founding date and founder information
   * Headquarters location
   * Company size (employees)
   * Private/public status, major investors

2. **Business Model & Revenue:**
   * Primary business model (SaaS, marketplace, etc.)
   * Revenue information (if available)
   * Pricing model (subscription, one-time purchase, etc.)
   * Customer segments (B2B, B2C, etc.)

3. **Products and Services:**
   * Main product/service offerings
   * Key technologies utilized
   * Core features and capabilities

4. **Market Position:**
   * Industry category
   * Main competitors
   * Market share (if available)
   * Key differentiators

5. **Geographic Presence:**
   * Countries/regions of operation
   * Target markets
   * Expansion strategy

{additional_aspects_placeholder}{user_context_placeholder}

Provide a concise, data-driven report. Avoid conversational filler, disclaimers, or speculative statements. All factual data should be cited with sources, either inline or in a concluding 'Sources' list. Respond only in English."""

        # Формируем полный пользовательский промпт
        user_content = prompt_template.format(
            company_name_placeholder=safe_company_name, 
            additional_aspects_placeholder=additional_aspects_str,
            user_context_placeholder=context_injection_str
        )
        
        # Системный промпт для модели
        system_prompt = (
            "You are an AI Business Analyst. Your task is to generate a detailed, structured, and factual business "
            "report on a given company, in English. Utilize your web search capabilities to find the most current "
            "information. Include data for the most recent available year, clearly stating the period. "
            "Adhere strictly to the requested report structure and level of detail. Cite all specific data points "
            "with their sources. Be concise and data-driven. Do not include conversational intros, outros, or disclaimers."
        )
        
        if self.verbose:
            print(f"Отправка запроса к {self.model} для компании '{company_name}'")
        
        try:
            # Делаем запрос к модели
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Please generate a detailed Business Analytics Report for the company: '{safe_company_name}'."
                     f"{user_context_text if user_context_text else ''}"},
                    {"role": "user", "content": user_content}
                ],
                web_search_options={"search_context_size": "high"}
            )
            
            answer_content = "LLM did not provide a comprehensive answer."
            extracted_sources = []
            
            if completion.choices and completion.choices[0].message:
                message = completion.choices[0].message
                if message.content:
                    answer_content = message.content.strip()
                
                # Извлекаем источники из аннотаций, если они есть
                if message.annotations:
                    for ann in message.annotations:
                        if ann.type == "url_citation" and ann.url_citation:
                            cited_title = ann.url_citation.title or "N/A"
                            cited_url = ann.url_citation.url or "N/A"
                            extracted_sources.append({"title": cited_title, "url": cited_url})
            
            return {"report_text": answer_content, "sources": extracted_sources}
            
        except APIError as e:
            error_msg = f"OpenAI API error: {str(e)}"
            if self.verbose:
                print(error_msg)
            return {"error": error_msg}
        except Timeout as e:
            error_msg = f"Timeout error: {str(e)}"
            if self.verbose:
                print(error_msg)
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            if self.verbose:
                print(error_msg)
            return {"error": error_msg}


# Код для тестового запуска при прямом выполнении файла
if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    
    async def test_finder():
        # Настройка логирования
        logging.basicConfig(level=logging.INFO, 
                           format='%(asctime)s - %(levelname)s - %(message)s')
        
        # Загрузка переменных окружения
        load_dotenv()
        
        # Получение API ключа
        openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if not openai_api_key:
            print("Ошибка: OPENAI_API_KEY не найден в .env файле")
            return
        
        # Создаем финдер
        finder = LLMDeepSearchFinder(openai_api_key, verbose=True)
        
        # Тестовые компании
        test_companies = ["Microsoft"]
        
        # Специфические аспекты для исследования
        specific_aspects = [
            "latest annual revenue",
            "key products",
            "CEO name"
        ]
        
        for company in test_companies:
            print(f"\nТестовый поиск для компании: {company}")
            result = await finder.find(
                company, 
                specific_aspects=specific_aspects,
                user_context="Focus on cloud services and AI products"
            )
            
            if result["result"]:
                print(f"Получен отчет ({len(result['result'])} символов)")
                print(f"Первые 200 символов: {result['result'][:200]}...")
                
                if result["sources"]:
                    print(f"\nИсточники ({len(result['sources'])}):")
                    for i, source in enumerate(result['sources'][:3], 1):
                        print(f"{i}. {source['title']}: {source['url']}")
                    if len(result['sources']) > 3:
                        print(f"...и еще {len(result['sources']) - 3} источников")
            else:
                print(f"Ошибка: {result.get('error', 'Неизвестная ошибка')}")
    
    # Запускаем тестовую функцию
    asyncio.run(test_finder()) 