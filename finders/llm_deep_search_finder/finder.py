import os
import sys
import logging
import json
import traceback
import re
from typing import Dict, List, Any, Optional
import aiohttp
from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError

# Добавляем корневую директорию проекта в путь Python
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from finders.base import Finder

logger = logging.getLogger(__name__)

async def translate_to_english(text: str, openai_client: AsyncOpenAI) -> str:
    """
    Принудительно переводит весь текст на английский язык.
    
    Args:
        text: Исходный текст
        openai_client: Клиент OpenAI
        
    Returns:
        str: Переведенный текст
    """
    if not text:
        return text
        
    try:
        logger.info(f"Translating text to English (length: {len(text)})")
        
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional translator. Your task is to translate ALL content to English including ALL Arabic, Chinese, Russian or any other non-English text. Preserve exact line breaks, formatting, and structure. For company names, add English translations in parentheses where needed."},
                {"role": "user", "content": f"Translate the following text to English, ensuring that ALL non-English content is fully translated. Pay special attention to any Arabic, Chinese, or other non-Latin script content:\n\n{text}"}
            ],
            temperature=0.1,
            max_tokens=10000
        )
        
        translated_text = response.choices[0].message.content
        logger.info(f"Translation completed (new length: {len(translated_text)})")
        return translated_text
    except Exception as e:
        logger.error(f"Error during translation: {e}")
        return text  # Return original text if translation fails

async def _extract_homepage_from_report_text_async(
    company_name: str, 
    report_text: str, 
    openai_client: AsyncOpenAI,
    model: str = "gpt-3.5-turbo",
    temperature: float = 0.0
) -> Optional[str]:
    """
    Извлекает наиболее вероятный URL официального сайта из текста отчета с помощью LLM
    и затем очищает его от Markdown или лишнего текста.
    """
    if not report_text or not report_text.strip():
        logger.warning(f"Empty report text for {company_name}. Cannot extract homepage URL.")
        return None
    
    # Логирование отрывка текста отчета для отладки
    logger.debug(f"Extracting homepage URL for '{company_name}' from report text. First 500 chars: {report_text[:500]}...")
    
    # Поиск очевидных URL напрямую в тексте до запроса LLM
    url_pattern = r'https?://[\w\.-/]+\.[a-zA-Z]{2,}(?:/[\w\康熙字典统一码擴充區乙\.\-\%_]*)?'
    
    # Обновленный паттерн, который учитывает форматирование Markdown в виде [URL](URL) или [текст](URL)
    # Ищем URL после упоминания "Official Homepage URL" или подобных фраз, поддерживая различные форматы
    homepage_section_pattern = r'(?i)official\s+(?:homepage|website|site)\s*(?:url)?[:\s]*(?:\[([^\]]+)\])?\s*(?:\(https?://[^\)]+\))?\s*(https?://[^\s\)\]]+)?'
    
    # Проверка прямых упоминаний в секции про официальный сайт
    direct_homepage_match = re.search(homepage_section_pattern, report_text)
    if direct_homepage_match:
        # Проверяем, какая группа содержит URL
        direct_url = None
        if direct_homepage_match.group(2):  # Простой URL формат
            direct_url = direct_homepage_match.group(2)
            logger.info(f"DIRECT MATCH (plain URL): Found homepage URL in report text for '{company_name}': {direct_url}")
        elif direct_homepage_match.group(1) and "http" in direct_homepage_match.group(1):  # URL внутри квадратных скобок
            direct_url = direct_homepage_match.group(1)
            logger.info(f"DIRECT MATCH (markdown text): Found homepage URL in report text for '{company_name}': {direct_url}")
        
        if direct_url:
            return direct_url
    
    # Поиск Markdown-ссылок в секциях о сайте компании, например [текст](URL)
    markdown_link_pattern = r'(?i)official\s+(?:homepage|website|site)(?:url)?[:\s]*\[([^\]]+)\]\(([^\)]+)\)'
    markdown_match = re.search(markdown_link_pattern, report_text)
    if markdown_match:
        url_from_markdown = markdown_match.group(2)  # URL в скобках
        logger.info(f"MARKDOWN MATCH: Found homepage URL in markdown format for '{company_name}': {url_from_markdown}")
        return url_from_markdown
    
    # Поиск в структурированных секциях
    homepage_sections = [
        r'(?i)## *Basic Company Information[\s\S]*?(?:Official|Main)[\s\S]*?(?:Homepage|Website|URL)[^\n]*?\n*([^\n]*)',
        r'(?i)Official\s+(?:Website|Homepage|URL)[^\n]*?\n*([^\n]*)',
        r'(?i)Website[^\n]*?\n*([^\n]*)'
    ]
    
    for pattern in homepage_sections:
        section_match = re.search(pattern, report_text)
        if section_match:
            section_text = section_match.group(1)
            logger.debug(f"Found potential homepage section for '{company_name}': '{section_text}'")
            
            # Проверяем наличие Markdown-ссылки в этой секции
            markdown_in_section = re.search(r'\[([^\]]+)\]\(([^\)]+)\)', section_text)
            if markdown_in_section:
                extracted_url = markdown_in_section.group(2)  # URL в скобках
                logger.info(f"SECTION MATCH (markdown): Found homepage URL in structured section for '{company_name}': {extracted_url}")
                return extracted_url
            
            # Если нет Markdown-ссылки, ищем обычный URL
            url_in_section = re.search(url_pattern, section_text)
            if url_in_section:
                extracted_url = url_in_section.group(0)
                logger.info(f"SECTION MATCH (plain): Found homepage URL in structured section for '{company_name}': {extracted_url}")
                return extracted_url
    
    # Если не удалось найти URL прямым анализом, используем LLM
    logger.info(f"No direct URL matches found in report for '{company_name}'. Querying LLM...")
    
    prompt_messages = [
        {
            "role": "system", 
            "content": (
                "You are an expert assistant that extracts the official homepage URL of a company from a given text. "
                "The text is a business report that might contain multiple URLs, including sources, news articles, etc. "
                "Your task is to identify and return ONLY the main official website (homepage) of the company. "
                "If multiple potential homepages are mentioned, choose the most likely one. "
                "If no clear official homepage URL is found, return 'None'. "
                "The URL should be a complete, valid URL (e.g., https://www.example.com)."
            )
        },
        {
            "role": "user", 
            "content": f"Company Name: {company_name}\n\nBusiness Report Text:\n```\n{report_text[:15000]} \n```\n\nBased on the text above, what is the official homepage URL for '{company_name}'? Return only the URL or 'None'."
        }
    ]
    
    try:
        logger.info(f"Querying LLM to extract homepage for '{company_name}' using {model}.")
        completion = await openai_client.chat.completions.create(
            model=model,
            messages=prompt_messages,
            temperature=temperature,
            max_tokens=200, # Немного увеличим, если LLM возвращает предложение
            stop=["\n"]
        )
        llm_response_text = completion.choices[0].message.content.strip()
        logger.info(f"LLM response for '{company_name}' homepage extraction: '{llm_response_text}'")

        if llm_response_text and llm_response_text.lower() != 'none':
            # Ищем URL с помощью регулярного выражения
            # Это выражение ищет стандартные URL, а также URL в Markdown формате [текст](URL)
            url_pattern = r'https?://[\w\.-/]+\.[a-zA-Z]{2,}(?:/[\w\康熙字典统一码擴充區乙\.\-\%_]*)?' # Базовый паттерн URL
            markdown_url_pattern = r'\[[^\]]+\]\((https?://[^\)]+)\)' # Markdown [text](url)
            
            # Сначала ищем Markdown URL
            markdown_match = re.search(markdown_url_pattern, llm_response_text)
            if markdown_match:
                extracted_url = markdown_match.group(1)
                logger.info(f"Extracted homepage for '{company_name}' from LLM response (Markdown): {extracted_url}")
                return extracted_url
            
            # Если Markdown URL не найден, ищем обычный URL
            plain_url_match = re.search(url_pattern, llm_response_text)
            if plain_url_match:
                extracted_url = plain_url_match.group(0)
                logger.info(f"Extracted homepage for '{company_name}' from LLM response (Plain URL): {extracted_url}")
                return extracted_url
            
            # Если регулярное выражение не нашло URL, но ответ не "None", пробуем найти что-то похожее на URL
            if "." in llm_response_text and ("http" in llm_response_text.lower() or "www" in llm_response_text.lower()):
                logger.warning(f"LLM response for '{company_name}' looks like URL but regex didn't match: '{llm_response_text}'")
                # Попытка с более слабым регулярным выражением
                weak_url_pattern = r'(https?://)?[\w\.-]+\.[a-zA-Z]{2,}(?:/[\w\康熙字典统一码擴充區乙\.\-\%_]*)?'
                weak_match = re.search(weak_url_pattern, llm_response_text)
                if weak_match:
                    weak_url = weak_match.group(0)
                    # Если URL не начинается с http, добавляем https://
                    if not weak_url.startswith(('http://', 'https://')):
                        weak_url = 'https://' + weak_url
                    logger.info(f"Using weak regex match for '{company_name}': {weak_url}")
                    return weak_url
            
            logger.warning(f"LLM response for '{company_name}' was '{llm_response_text}', but no clean URL could be extracted.")
            return None
        else:
            logger.info(f"LLM did not find a clear homepage URL for '{company_name}' in the report (returned: {llm_response_text}).")
            return None
    except Exception as e:
        logger.error(f"Error extracting homepage for '{company_name}' from report text: {e}", exc_info=True)
        return None

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
        self.model = "gpt-4o-search-preview"  # Модель с поддержкой поиска
        
    async def find(self, company_name: str, **context) -> dict:
        """
        Ищет подробную информацию о компании, используя LLM с возможностью поиска в интернете.
        
        Args:
            company_name: Название компании
            context: Словарь с контекстом, может содержать:
                     - 'specific_aspects': список аспектов, которые нужно исследовать
                     - 'user_context': дополнительный контекст от пользователя
                     - 'company_homepage_url': URL домашней страницы компании (если уже известен)
                     
        Returns:
            dict: Результат поиска {
                "source": "llm_deep_search", 
                "result": str или None,  # текст отчета
                "raw_result": str или None,  # Добавляем дублирование в raw_result для совместимости
                "sources": list  # список источников в формате [{"title": str, "url": str}, ...]
            }
        """
        specific_aspects = context.get('specific_aspects', self._get_default_aspects())
        user_context = context.get('user_context', None)
        
        if self.verbose:
            logger.info(f"\n--- LLM Deep Search для компании '{company_name}' ---")
            logger.info(f"Модель: {self.model}")
            logger.info(f"Исследуемые аспекты: {len(specific_aspects)} пунктов")
            if context.get('company_homepage_url'):
                logger.info(f"Предоставленный URL компании: {context.get('company_homepage_url')}")
        
        try:
            report_dict = await self._query_llm_for_deep_info(
                company_name=company_name,
                specific_aspects_to_cover=specific_aspects,
                user_context_text=user_context,
                context=context  # Передаем весь контекст в метод _query_llm_for_deep_info
            )
            
            if "error" in report_dict:
                if self.verbose:
                    logger.error(f"Ошибка при поиске: {report_dict['error']}")
                return {
                    "source": "llm_deep_search", 
                    "result": None, 
                    "raw_result": None,
                    "error": report_dict["error"],
                    "sources": [],
                    "extracted_homepage_url": None,
                    "_finder_instance_type": self.__class__.__name__
                }
            
            report_text = report_dict.get("report_text", "")
            sources = report_dict.get("sources", [])
            extracted_homepage_url = report_dict.get("extracted_homepage_url")
            
            # ПРИНУДИТЕЛЬНЫЙ ПЕРЕВОД ОТЧЕТА НА АНГЛИЙСКИЙ ЯЗЫК
            logger.info(f"Translating report for company '{company_name}'")
            translated_report = await translate_to_english(report_text, self.client)
            
            if self.verbose:
                logger.info(f"Получен отчет ({len(report_text)} символов) с {len(sources)} источниками. Извлеченный homepage: {extracted_homepage_url}")
                logger.info(f"Report translated to English ({len(translated_report)} symbols)")
            else:
                logger.info(f"LLM Deep Search для '{company_name}': получен отчет с {len(sources)} источниками, homepage: {extracted_homepage_url}")
                logger.info(f"Report translated to English ({len(translated_report)} symbols)")
                
            return {
                "source": "llm_deep_search", 
                "result": translated_report, 
                "raw_result": translated_report,
                "sources": sources,
                "extracted_homepage_url": extracted_homepage_url,
                "_finder_instance_type": self.__class__.__name__
            }
        except Exception as e:
            error_msg = f"Непредвиденная ошибка при поиске для '{company_name}': {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return {
                "source": "llm_deep_search",
                "result": None,
                "raw_result": None,
                "error": error_msg,
                "sources": [],
                "extracted_homepage_url": None,
                "_finder_instance_type": self.__class__.__name__
            }
    
    def _get_default_aspects(self) -> List[str]:
        """
        Возвращает список аспектов для исследования по умолчанию.
        Аспекты выбраны таким образом, чтобы соответствовать полям JSON-схемы.
        
        Returns:
            List[str]: Список аспектов
        """
        return [
            "precise founding year of the company (exact date if available)",
            "detailed headquarters location including city, country, and address if available",
            "full names of the founding team members and current CEO",
            "detailed ownership structure (e.g., public company with stock symbol, private company with major investors, etc.)",
            "last 2-3 years of annual revenue with exact figures and currency (specify fiscal year periods)",
            "exact employee count (current or most recently reported) with source and date",
            "all funding rounds with exact amounts, dates, and lead investors",
            "detailed product portfolio with specific product names and core features, including year of launch if available",
            "underlying technologies used by the company for their products/services",
            "primary customer types (B2B, B2C, B2G) with specific industry focus",
            "industries served or targeted by the company",
            "geographic markets where the company operates or sells its products",
            "major clients or case studies with specific names",
            "strategic initiatives, partnerships, or mergers & acquisitions",
            "key competitors mentioned within the company's industry",
            "any pending mergers, acquisitions, or significant organizational changes",
            "open job positions of professional level (engineering, development, industry specialists, etc. - no administrative/support roles) that might indicate company's technical focus areas",
            "languages used by the company for business communications and documentation (working languages, official languages)",
            "presence of a user-facing portal, app login, or transactional interface on the company's website/products (specify if users can log in, make transactions, or interact with a dashboard)",
            "evidence of secure transactions or compliance with regulatory standards (e.g. PCI DSS, ISO 27001, GDPR, KYC, SOC 2) - search thoroughly for ANY security or compliance mentions"
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
        user_context_text: Optional[str] = None,
        context: Dict[str, Any] = {}
    ) -> Dict[str, Any]:
        """
        Запрашивает у LLM с поиском подробную информацию о компании.
        Промпт структурирован в соответствии с JSON-схемой для лучшей обработки.
        
        Args:
            company_name: Название компании
            specific_aspects_to_cover: Список аспектов, которые нужно исследовать
            user_context_text: Дополнительный контекст от пользователя
            context: Словарь с контекстом
            
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

**Crucially, make a specific effort to find and clearly state the company's official homepage URL. This URL is a key piece of information.**

The report MUST follow this structure that corresponds to our JSON schema:

1. **Basic Company Information:**
   * Company Name: Official legal name of the company.
   * Founding Year: Exact year when the company was founded.
   * Headquarters Location: City and country of the company's headquarters.
   * Founders: Names of all company founders.
   * Ownership Background: Information about ownership structure (public/private, parent companies, etc.)
   * **Official Homepage URL:** [Clearly state the primary official website URL here if found during your search]

2. **Products and Technology:**
   * Core Products & Services: List each major product/service with its launch year (if available).
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

6. **Additional Business Information:**
   * Professional Open Positions: List technical/professional job openings (engineering, development, industry specialists) that indicate company's focus areas. Exclude administrative/support roles.
   * Working Languages: Languages used by the company for business communications and documentation.

7. **Technical and Compliance Information:**
   * User Portal/Login System: Describe ANY user-facing platform, portal, profile, dashboard, or interactive interface found on the company's website or products. Look beyond explicit login buttons - check for streaming apps, dashboards, client portals, membership areas, e-commerce features, subscription services, or any interactive platform that implies user access control or personalization. If no explicit login system is found, report on any features that would logically require users to have accounts (like personalized content, saved preferences, or multi-step transactions).
   * Compliance Standards: Thoroughly investigate and report on ANY evidence of secure transactions or compliance with regulatory standards (PCI DSS, ISO 27001, GDPR, KYC, SOC 2, etc.). Check footer links, terms of service, privacy policy pages, and about/security sections. Include even minor mentions of security certifications, encryption, data protection practices, SSL certificates, or compliance statements. If no explicit standards are found, look for security-related statements like "secure environment", "encrypted connections", or "data protection measures".

{additional_aspects_placeholder}{user_context_placeholder}

Provide COMPLETE and THOROUGH information in each section. Do not abbreviate or summarize the data. Include as much detail as you can find. All factual data, especially figures like revenue, subscriber counts, and pricing, should be cited with sources, either inline or in a concluding 'Sources' list. Ensure the official homepage URL is explicitly mentioned if found."""

        # Формируем полный пользовательский промпт
        user_content = prompt_template.format(
            company_name_placeholder=safe_company_name, 
            additional_aspects_placeholder=additional_aspects_str,
            user_context_placeholder=context_injection_str
        )
        
        # Системный промпт для модели
        system_prompt = (
            "You are an AI Business Analyst. Your task is to generate a detailed, structured, and factual business report on a given company. "
            "Utilize your web search capabilities to find the most current information. **A key part of your task is to identify and report the company's official homepage URL.** "
            "When financial data is requested, if multiple recent years are found, include data for each distinct year, clearly stating the period. Prioritize the most recent full fiscal year data. "
            "The report MUST follow the exact sections in the prompt, as these will be used to extract structured data into a JSON schema. "
            "Provide FULL and DETAILED information in each section - do not abbreviate or summarize the data. Include as much detail as you can find. "
            "Do not include conversational intros, outros, or disclaimers. "
            "For sections where you cannot find information, simply include a brief note like 'No specific data found on [topic]' rather than leaving the section empty."
        )
        
        if self.verbose:
            logger.info(f"Отправка запроса к {self.model} для компании '{company_name}'")
        
        extracted_homepage_url_from_report = None
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
                    
                    # Проверяем, был ли URL уже предоставлен во входных данных
                    if context and 'company_homepage_url' in context and context.get('company_homepage_url'):
                        # Используем уже предоставленный URL без вызова модели
                        extracted_homepage_url_from_report = context.get('company_homepage_url')
                        logger.info(f"Using provided URL from input data for '{company_name}': {extracted_homepage_url_from_report}")
                    else:
                        # Если URL не был предоставлен, пытаемся извлечь его из отчета
                        extracted_homepage_url_from_report = await _extract_homepage_from_report_text_async(
                            company_name, answer_content, self.client
                        )
                
                # Извлекаем источники из аннотаций, если они есть
                if hasattr(message, 'annotations') and message.annotations:
                    for ann in message.annotations:
                        if ann.type == "url_citation" and hasattr(ann, 'url_citation'):
                            try:
                                cited_title = getattr(ann.url_citation, 'title', "N/A") or "N/A"
                                cited_url = getattr(ann.url_citation, 'url', "N/A") or "N/A"
                                extracted_sources.append({"title": cited_title, "url": cited_url})
                            except Exception as e_ann:
                                logger.warning(f"Ошибка при извлечении URL-цитаты из аннотации: {e_ann}")
            
            return {"report_text": answer_content, "sources": extracted_sources, "extracted_homepage_url": extracted_homepage_url_from_report}
            
        except APITimeoutError as e:
            error_msg = f"OpenAI Timeout error для '{company_name}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "report_text": None, "sources": [], "extracted_homepage_url": None}
        except RateLimitError as e:
            error_msg = f"OpenAI Rate Limit error для '{company_name}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "report_text": None, "sources": [], "extracted_homepage_url": None}  
        except APIError as e:
            error_msg = f"OpenAI API error для '{company_name}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "report_text": None, "sources": [], "extracted_homepage_url": None}
        except Exception as e:
            error_msg = f"Unexpected error для '{company_name}': {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return {"error": error_msg, "report_text": None, "sources": [], "extracted_homepage_url": None}


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