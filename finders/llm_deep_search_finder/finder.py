import os
import sys
import logging
import json
import traceback
from typing import Dict, List, Any, Optional

# Добавляем корневую директорию проекта в путь Python
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from finders.base import Finder
from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

class LLMDeepSearchFinder(Finder):
    """
    Финдер, использующий LLM с возможностью поиска в интернете для получения 
    подробной информации о компании.
    
    Использует модель GPT-4o-mini-search-preview, которая может
    искать актуальную информацию в интернете и составлять структурированный отчет,
    соответствующий JSON-схеме для последующей обработки.
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
            logger.info(f"\n--- LLM Deep Search для компании '{company_name}' ---")
            logger.info(f"Модель: {self.model}")
            logger.info(f"Исследуемые аспекты: {len(specific_aspects)} пунктов")
        
        try:
            report_dict = await self._query_llm_for_deep_info(
                company_name=company_name,
                specific_aspects_to_cover=specific_aspects,
                user_context_text=user_context
            )
            
            if "error" in report_dict:
                if self.verbose:
                    logger.error(f"Ошибка при поиске: {report_dict['error']}")
                return {
                    "source": "llm_deep_search", 
                    "result": None, 
                    "error": report_dict["error"],
                    "sources": []
                }
            
            report_text = report_dict.get("report_text", "")
            sources = report_dict.get("sources", [])
            
            if self.verbose:
                logger.info(f"Получен отчет ({len(report_text)} символов) с {len(sources)} источниками")
            else:
                logger.info(f"LLM Deep Search для '{company_name}': получен отчет с {len(sources)} источниками")
                
            return {
                "source": "llm_deep_search", 
                "result": report_text, 
                "sources": sources
            }
        except Exception as e:
            error_msg = f"Непредвиденная ошибка при поиске для '{company_name}': {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return {
                "source": "llm_deep_search",
                "result": None,
                "error": error_msg,
                "sources": []
            }
    
    def _get_default_aspects(self) -> List[str]:
        """
        Возвращает список аспектов для исследования по умолчанию.
        Аспекты выбраны таким образом, чтобы соответствовать полям JSON-схемы.
        
        Returns:
            List[str]: Список аспектов
        """
        return [
            "precise founding year of the company (exact date)",
            "detailed headquarters location including city and country",
            "full names of the founding team members and current CEO",
            "detailed ownership structure (e.g., public company with stock symbol, private company with major investors, etc.)",
            "last 2-3 years of annual revenue with exact figures and currency (specify fiscal year periods)",
            "exact employee count (current or most recently reported) with source and date",
            "all funding rounds with exact amounts, dates, and lead investors",
            "detailed product portfolio with specific product names and core features, including year of launch",
            "underlying technologies used by the company for their products/services",
            "primary customer types (B2B, B2C, B2G) with specific industry focus",
            "industries served or targeted by the company",
            "geographic markets where the company operates or sells its products",
            "major clients or case studies with specific names",
            "strategic initiatives, partnerships, or mergers & acquisitions",
            "key competitors mentioned within the company's industry",
            "any pending mergers, acquisitions, or significant organizational changes"
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
        Промпт структурирован в соответствии с JSON-схемой для лучшей обработки.
        
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
        
        # Основной шаблон промпта (структурированный под JSON-схему)
        prompt_template = """Please generate a detailed Business Analytics Report for the company: '{company_name_placeholder}'.

Your primary goal is to extract and present factual data that will later be structured according to a specific JSON schema. 
When reporting financial figures (like revenue, ARR, funding), prioritize data for the most recent fiscal year. If multiple years of data are found, include all such figures, clearly stating the period/year each figure refers to.

The report MUST follow this structure that corresponds to our JSON schema:

1. **Basic Company Information:**
   * Company Name: Official legal name of the company.
   * Founding Year: Exact year when the company was founded.
   * Headquarters Location: City and country of the company's headquarters.
   * Founders: Names of all company founders.
   * Ownership Background: Information about ownership structure (public/private, parent companies, etc.)

2. **Products and Technology:**
   * Core Products & Services: List each major product/service with its launch year.
   * Underlying Technologies: Key technologies, frameworks, or platforms used by the company.

3. **Market and Customer Information:**
   * Customer Types: Primary customer categories (B2B, B2C, B2G).
   * Industries Served: Specific industries or sectors the company targets.
   * Geographic Markets: Countries or regions where the company operates.

4. **Financial and HR Details:**
   * Revenue History: For each reported year, provide the amount, currency, and type (total revenue, ARR, etc.).
   * Funding Rounds: For each round, include the round name, year closed, amount, currency, and key investors.
   * Employee Count: Current or most recent employee count with the reporting year.

5. **Strategic Information:**
   * Major Clients or Case Studies: Notable customers or implementation examples.
   * Strategic Initiatives: Key partnerships, expansions, or strategic moves.
   * Key Competitors: Main competitors in their space.
   * Overall Summary: Brief summary of the company's position and outlook.

{additional_aspects_placeholder}{user_context_placeholder}

Provide a concise, data-driven report. Avoid conversational filler, disclaimers, or speculative statements. All factual data, especially figures like revenue, subscriber counts, and pricing, should be cited with sources, either inline or in a concluding 'Sources' list."""

        # Формируем полный пользовательский промпт
        user_content = prompt_template.format(
            company_name_placeholder=safe_company_name, 
            additional_aspects_placeholder=additional_aspects_str,
            user_context_placeholder=context_injection_str
        )
        
        # Системный промпт для модели
        system_prompt = (
            "You are an AI Business Analyst. Your task is to generate a detailed, structured, and factual business report on a given company. "
            "Utilize your web search capabilities to find the most current information. When financial data is requested, if multiple recent years are found, "
            "include data for each distinct year, clearly stating the period. Prioritize the most recent full fiscal year data. "
            "The report MUST follow the exact sections in the prompt, as these will be used to extract structured data into a JSON schema. "
            "Be concise and data-driven. Do not include conversational intros, outros, or disclaimers. "
            "For sections where you cannot find information, simply include a brief note like 'No specific data found on [topic]' rather than leaving the section empty."
        )
        
        if self.verbose:
            logger.info(f"Отправка запроса к {self.model} для компании '{company_name}'")
        
        try:
            # Делаем запрос к модели с правильными параметрами
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            )
            
            answer_content = "LLM did not provide a comprehensive answer."
            extracted_sources = []
            
            if completion.choices and completion.choices[0].message:
                message = completion.choices[0].message
                if message.content:
                    answer_content = message.content.strip()
                
                # Извлекаем источники из аннотаций, если они есть
                if hasattr(message, 'annotations') and message.annotations:
                    for ann in message.annotations:
                        if ann.type == "url_citation" and hasattr(ann, 'url_citation'):
                            try:
                                cited_title = getattr(ann.url_citation, 'title', "N/A") or "N/A"
                                cited_url = getattr(ann.url_citation, 'url', "N/A") or "N/A"
                                extracted_sources.append({"title": cited_title, "url": cited_url})
                            except Exception as e:
                                logger.warning(f"Ошибка при извлечении URL-цитаты: {e}")
            
            return {"report_text": answer_content, "sources": extracted_sources}
            
        except APITimeoutError as e:
            error_msg = f"OpenAI Timeout error для '{company_name}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}
        except RateLimitError as e:
            error_msg = f"OpenAI Rate Limit error для '{company_name}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}  
        except APIError as e:
            error_msg = f"OpenAI API error для '{company_name}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Unexpected error для '{company_name}': {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
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