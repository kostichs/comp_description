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

def normalize_markdown_format(markdown_text: str) -> str:
    """
    Нормализует форматирование markdown-текста, удаляя лишние пустые строки.
    Функция применяет минимальные необходимые изменения, чтобы сделать форматирование
    более согласованным, не добавляя при этом лишних пустых строк.
    
    Args:
        markdown_text: Исходный markdown-текст
        
    Returns:
        str: Нормализованный markdown-текст
    """
    if not markdown_text:
        return markdown_text
    
    logger.info("Normalizing markdown format...")
    
    # Обязательно заменяем слишком большое количество пустых строк (более двух подряд)
    normalized = re.sub(r'\n{3,}', r'\n\n', markdown_text)
    
    # Удаляем пустые строки между последовательными элементами списка с тем же маркером,
    # но только если их больше одной
    normalized = re.sub(r'(\n- [^\n]+)\n\n+(?=- )', r'\1\n', normalized)
    normalized = re.sub(r'(\n\* [^\n]+)\n\n+(?=\* )', r'\1\n', normalized)
    
    # Заменяем все оставшиеся последовательности из трех и более пустых строк 
    # на максимум одну пустую строку
    normalized = re.sub(r'\n{3,}', r'\n\n', normalized)
    
    logger.info("Markdown format normalization complete")
    return normalized

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
    Извлекает URL домашней страницы компании из текста отчета.
    
    Args:
        company_name: Название компании
        report_text: Текст отчета
        openai_client: Клиент OpenAI для запросов к LLM
        model: Модель для запросов к LLM
        temperature: Температура для запросов к LLM
        
    Returns:
        Optional[str]: URL домашней страницы или None, если не найден
    """
    if not report_text:
        return None
    
    # Улучшенное регулярное выражение для поиска URL
    url_pattern = r'https?://[\w\.-]+\.[a-zA-Z]{2,}(?:/[\w\.\-\%_]*)*'
    
    # Улучшенные шаблоны разделов, где обычно указывается URL домашней страницы
    homepage_sections = [
        # Базовые секции с URL
        r'(?i)official\s+homepage\s+url\s*:?\s*([^\n\r]+)',  # Official Homepage URL: ...
        r'(?i)company\'?s?\s+website\s*:?\s*([^\n\r]+)',     # Company's Website: ...
        r'(?i)website\s*:?\s*([^\n\r]+)',                    # Website: ...
        r'(?i)official\s+website\s*:?\s*([^\n\r]+)',         # Official Website: ...
        r'(?i)homepage\s*:?\s*([^\n\r]+)',                   # Homepage: ...
        r'(?i)web\s+address\s*:?\s*([^\n\r]+)',              # Web Address: ...
        r'(?i)web\s+site\s*:?\s*([^\n\r]+)',                 # Web Site: ...
        
        # Секции с возможными URL
        r'(?i)can\s+be\s+found\s+at\s+([^\n\r\.]+)',         # can be found at ...
        r'(?i)available\s+at\s+([^\n\r\.]+)',                # available at ...
        r'(?i)headquartered\s+at\s+([^\n\r\.]+)',            # headquartered at ...
        r'(?i)located\s+at\s+([^\n\r\.]+)',                  # located at ...
        
        # Поиск в более крупных секциях
        r'(?i)basic\s+company\s+information.*?homepage.*?([^\n\r]{5,150})',  # В разделе Basic Company Information
        r'(?i)company\s+name.*?website.*?([^\n\r]{5,150})',  # После имени компании, где упоминается website
        r'(?i)founded\s+in.*?website.*?([^\n\r]{5,150})',    # После года основания, где упоминается website
    ]
    
    # 1. Сначала ищем URL в ключевых секциях
    for pattern in homepage_sections:
        section_match = re.search(pattern, report_text, re.DOTALL)
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
    
    # 2. Ищем прямые упоминания доменов компании без http/https
    company_name_parts = re.sub(r'[^\w\s]', '', company_name.lower()).split()
    
    # Ищем домены, которые содержат части имени компании
    domain_pattern = r'(?<!\S)(?:www\.)?([a-zA-Z0-9][\w\-]*\.(?:com|org|net|io|co|ai|app|tech|us|uk|ca|de|fr|es|it|au|jp|cn)(?:\.[a-zA-Z]{2})?)(?!\S)'
    domain_matches = re.finditer(domain_pattern, report_text)
    
    potential_domains = []
    for match in domain_matches:
        domain = match.group(0)
        if not domain.startswith('www.'):
            domain = 'www.' + domain
        
        # Проверяем, содержит ли домен часть имени компании
        domain_lower = domain.lower()
        for part in company_name_parts:
            if len(part) >= 3 and part.lower() in domain_lower:  # Минимум 3 символа для предотвращения ложных срабатываний
                potential_domains.append("https://" + domain)
                break
    
    if potential_domains:
        logger.info(f"DOMAIN MATCH: Found potential domains for '{company_name}': {potential_domains[0]}")
        return potential_domains[0]  # Возвращаем первый найденный домен
    
    # 3. Ищем все URL в документе и проверяем, какие из них наиболее вероятно являются основным сайтом
    all_urls = re.findall(url_pattern, report_text)
    
    if all_urls:
        # Фильтруем URL, исключая известные нежелательные домены
        filtered_urls = []
        excluded_domains = ['wikipedia.org', 'linkedin.com', 'facebook.com', 'twitter.com', 'youtube.com', 
                           'instagram.com', 'google.com', 'crunchbase.com', 'bloomberg.com', 'sec.gov', 
                           'github.com', 'yahoo.com', 'forbes.com', 'businesswire.com', 'prnewswire.com']
        
        for url in all_urls:
            if not any(excluded in url.lower() for excluded in excluded_domains):
                filtered_urls.append(url)
        
        if filtered_urls:
            # Сортируем URL по "вероятности" быть основным сайтом (короткие URL, содержащие название компании)
            scored_urls = []
            for url in filtered_urls:
                score = 0
                url_lower = url.lower()
                
                # Бонус за короткий URL
                if url.count('/') <= 3:  # Только домен или домен с одним путем
                    score += 5
                
                # Бонус за наличие частей имени компании в домене
                for part in company_name_parts:
                    if len(part) >= 3 and part.lower() in url_lower:
                        score += 3
                
                # Бонус за .com домен
                if '.com' in url_lower:
                    score += 2
                
                # Бонус за отсутствие параметров запроса
                if '?' not in url:
                    score += 1
                
                scored_urls.append((url, score))
            
            # Сортируем по убыванию оценки
            scored_urls.sort(key=lambda x: x[1], reverse=True)
            
            if scored_urls and scored_urls[0][1] > 0:
                best_url = scored_urls[0][0]
                logger.info(f"URL SCORE MATCH: Found best URL for '{company_name}' with score {scored_urls[0][1]}: {best_url}")
                return best_url
    
    # 4. Если не удалось найти URL прямым анализом, используем LLM
    logger.info(f"No direct URL matches found in report for '{company_name}'. Querying LLM...")
    
    prompt_messages = [
        {"role": "system", "content": (
            "You are a specialized AI focused on extracting the official homepage URL of companies from text. "
            "Your task is to carefully read the provided business report and identify the company's official website URL. "
            "ONLY respond with the complete URL (including http:// or https://) and nothing else. "
            "If you cannot find a clear URL in the text, respond with 'None'."
        )},
        {"role": "user", "content": (
            f"Extract the official homepage URL for '{company_name}' from this business report. "
            f"Respond ONLY with the complete URL including the http:// or https:// prefix, or 'None' if no clear URL is found.\n\n"
            f"Report text:\n{report_text[:5000]}"  # Ограничиваем размер для эффективности
        )}
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
            
            # Если URL не найден, но ответ не 'None', пробуем обработать как обычный домен
            if llm_response_text.lower() != 'none':
                potential_domain = llm_response_text.strip()
                if '.' in potential_domain and ' ' not in potential_domain:
                    # Добавляем префикс https:// если его нет
                    if not potential_domain.startswith(('http://', 'https://')):
                        potential_domain = 'https://' + potential_domain
                    logger.info(f"Converted LLM response to URL for '{company_name}': {potential_domain}")
                    return potential_domain
        
    except Exception as e:
        logger.error(f"Error querying LLM for homepage extraction for '{company_name}': {e}")
    
    # Если все методы не сработали, возвращаем None
        return None

class LLMDeepSearchFinder(Finder):
    """
    Finder that uses LLM with internet search capabilities to get 
    detailed company information.
    
    Uses GPT-4o-mini-search-preview model that can
    search for current information on the internet and compile structured reports
    that conform to JSON schema for further processing.
    """
    
    def __init__(self, openai_api_key: str, verbose: bool = False):
        """
        Initialize the finder with OpenAI API key.
        
        Args:
            openai_api_key: OpenAI API key
            verbose: Output detailed search logs (default False)
        """
        self.openai_api_key = openai_api_key
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.verbose = verbose
        self.model = "gpt-4o-search-preview"  # Model with search support
        
    async def find(self, company_name: str, **context) -> dict:
        """
        Ищет подробную информацию о компании, используя LLM с возможностью поиска в интернете.
        
        Args:
            company_name: Название компании
            context: Словарь с контекстом, может содержать:
                     - 'specific_aspects': список аспектов, которые нужно исследовать
                     - 'user_context': дополнительный контекст от пользователя
                     - 'company_homepage_url': URL домашней страницы компании (если уже известен)
                     - 'url_only_mode': если True, поиск будет направлен только на получение URL компании
                     
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
        url_only_mode = context.get('url_only_mode', False)
        
        if self.verbose:
            logger.info(f"\n--- LLM Deep Search для компании '{company_name}' ---")
            logger.info(f"Модель: {self.model}")
            if url_only_mode:
                logger.info(f"Режим: только поиск URL (url_only_mode=True)")
            else:
                logger.info(f"Исследуемые аспекты: {len(specific_aspects)} пунктов")
            if context.get('company_homepage_url'):
                logger.info(f"Предоставленный URL компании: {context.get('company_homepage_url')}")
        
        try:
            # Если установлен режим поиска только URL, используем облегченный запрос
            if url_only_mode:
                return await self._find_url_only(company_name, context)
            
            # Проверяем, был ли предоставлен контекст от пользователя
            linkedin_url = context.get('linkedin_url', None)
            context_text = context.get('context_text', None)
            combined_context = {}
            
            # Передаем URL домашней страницы, если он уже известен
            if context.get('company_homepage_url'):
                combined_context['company_homepage_url'] = context.get('company_homepage_url')
            
            # Получаем текст отчета от LLM
            report_dict = await self._query_llm_for_deep_info(
                company_name, 
                specific_aspects, 
                user_context, 
                context=combined_context
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
            
            # НОРМАЛИЗАЦИЯ ФОРМАТИРОВАНИЯ MARKDOWN
            normalized_report = normalize_markdown_format(translated_report)
            
            if self.verbose:
                logger.info(f"Получен отчет ({len(report_text)} символов) с {len(sources)} источниками. Извлеченный homepage: {extracted_homepage_url}")
                logger.info(f"Report translated to English ({len(translated_report)} symbols) and format normalized")
            else:
                logger.info(f"LLM Deep Search для '{company_name}': получен отчет с {len(sources)} источниками, homepage: {extracted_homepage_url}")
                logger.info(f"Report translated to English and format normalized")
                
            return {
                "source": "llm_deep_search", 
                "result": normalized_report, 
                "raw_result": normalized_report,
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
            
    async def _find_url_only(self, company_name: str, context: Dict[str, Any] = {}) -> dict:
        """
        Облегченный метод только для поиска URL компании.
        Использует оптимизированный промпт и более быстрые настройки.
        
        Args:
            company_name: Название компании
            context: Контекст поиска
            
        Returns:
            dict: Результат поиска с URL
        """
        logger.info(f"Running URL-only search for company '{company_name}'")
        
        # Системный промпт для режима поиска только URL
        system_prompt = (
            "You are a specialized AI researcher focused exclusively on finding the official website URLs for companies. "
            "Your only task is to identify and return the most likely official homepage URL for the company name provided. "
            "Focus on finding the main corporate website, not social media profiles, third-party listings, or subsidiary sites. "
            "You must search for the most current information and provide a complete URL including http:// or https://."
        )
        
        # Пользовательский промпт для запроса только URL
        user_prompt = (
            f"Find the official homepage URL for the company: {company_name}\n\n"
            f"IMPORTANT: I need ONLY the company's official website URL. Return ONLY the complete URL with no explanations or additional text."
        )
        
        try:
            # Делаем запрос к модели с оптимизированными параметрами для быстрого ответа
            completion = await self.client.chat.completions.create(
                model=self.model,  # Используем ту же модель с поиском
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,  # Низкая температура для более детерминированного ответа
                max_tokens=100    # Ограничиваем размер ответа для скорости
            )
            
            url_response = None
            extracted_sources = []
            
            if completion.choices and completion.choices[0].message:
                message = completion.choices[0].message
                if message.content:
                    response_content = message.content.strip()
                    
                    # Извлекаем URL из ответа
                    url_pattern = r'https?://[\w\.-]+\.[a-zA-Z]{2,}(?:/[\w\.\-\%_]*)*'
                    url_match = re.search(url_pattern, response_content)
                    
                    if url_match:
                        url_response = url_match.group(0)
                        logger.info(f"URL-only search found URL for '{company_name}': {url_response}")
                    else:
                        # Если URL не найден в стандартном формате, проверяем на доменное имя без протокола
                        domain_pattern = r'(?<!\S)(?:www\.)?([a-zA-Z0-9][\w\-]*\.(?:com|org|net|io|co|ai|app|tech|us|uk|ca|de|fr|es|it|au|jp|cn)(?:\.[a-zA-Z]{2})?)(?!\S)'
                        domain_match = re.search(domain_pattern, response_content)
                        
                        if domain_match:
                            domain = domain_match.group(0)
                            if not domain.startswith(('http://', 'https://', 'www.')):
                                domain = 'https://www.' + domain
                            elif domain.startswith('www.'):
                                domain = 'https://' + domain
                            
                            url_response = domain
                            logger.info(f"URL-only search found domain for '{company_name}': {url_response}")
                        else:
                            # Если не найден даже домен, проверяем весь ответ на соответствие домену
                            clean_response = response_content.strip()
                            if '.' in clean_response and ' ' not in clean_response and len(clean_response) < 100:
                                if not clean_response.startswith(('http://', 'https://')):
                                    clean_response = 'https://' + clean_response
                                
                                url_response = clean_response
                                logger.info(f"URL-only search using full response as URL for '{company_name}': {url_response}")
                
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
            
            # Формируем результат
            return {
                "source": "llm_deep_search",
                "result": f"URL-only search for {company_name}",
                "raw_result": f"URL-only search for {company_name}",
                "sources": extracted_sources,
                "extracted_homepage_url": url_response,
                "_finder_instance_type": self.__class__.__name__,
                "url_only_mode": True
            }
        except Exception as e:
            error_msg = f"Error in URL-only search for '{company_name}': {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return {
                "source": "llm_deep_search",
                "result": None,
                "raw_result": None,
                "error": error_msg,
                "sources": [],
                "extracted_homepage_url": None,
                "_finder_instance_type": self.__class__.__name__,
                "url_only_mode": True
            }
    
    def _get_default_aspects(self) -> List[str]:
        """
        Returns a list of default research aspects.
        Aspects are chosen to correspond to JSON schema fields.
        
        Returns:
            List[str]: List of aspects
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
        Escapes special characters in string for safe insertion into prompt.
        
        Args:
            text: Source string
            
        Returns:
            str: Escaped string
        """
        return json.dumps(text)[1:-1]  # Use json.dumps and remove outer quotes
    
    async def _query_llm_for_deep_info(
        self,
        company_name: str,
        specific_aspects_to_cover: List[str],
        user_context_text: Optional[str] = None,
        context: Dict[str, Any] = {}
    ) -> Dict[str, Any]:
        """
        Queries LLM with search for detailed company information.
        Prompt is structured according to JSON schema for better processing.
        
        Args:
            company_name: Company name
            specific_aspects_to_cover: List of aspects to research
            user_context_text: Additional context from user
            context: Context dictionary
            
        Returns:
            Dict[str, Any]: Dictionary with report and sources or error
        """
        safe_company_name = self._escape_string_for_prompt(company_name)
        
        # Form prompt parts based on passed aspects
        additional_aspects_str = ""
        if specific_aspects_to_cover:
            escaped_aspects = [self._escape_string_for_prompt(aspect) for aspect in specific_aspects_to_cover]
            additional_aspects_str = "\n\nAdditionally, ensure these specific aspects are thoroughly investigated and included within the relevant sections of your report:\n- " + "\n- ".join(escaped_aspects)
        
        # Add user context if available
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
            logger.info(f"Sending request to {self.model} for company '{company_name}'")
        
        extracted_homepage_url_from_report = None
        try:
            # Make request to model with correct parameters
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
                    
                    # Check if URL was already provided in input data
                    if context and 'company_homepage_url' in context and context.get('company_homepage_url'):
                        # Use already provided URL without calling model
                        extracted_homepage_url_from_report = context.get('company_homepage_url')
                        logger.info(f"Using provided URL from input data for '{company_name}': {extracted_homepage_url_from_report}")
                    else:
                        # If URL was not provided, try to extract it from report
                        extracted_homepage_url_from_report = await _extract_homepage_from_report_text_async(
                        company_name, answer_content, self.client
                    )
                
                # Extract sources from annotations if available
                if hasattr(message, 'annotations') and message.annotations:
                    for ann in message.annotations:
                        if ann.type == "url_citation" and hasattr(ann, 'url_citation'):
                            try:
                                cited_title = getattr(ann.url_citation, 'title', "N/A") or "N/A"
                                cited_url = getattr(ann.url_citation, 'url', "N/A") or "N/A"
                                extracted_sources.append({"title": cited_title, "url": cited_url})
                            except Exception as e_ann:
                                logger.warning(f"Error extracting URL citation from annotation: {e_ann}")
            
            return {"report_text": answer_content, "sources": extracted_sources, "extracted_homepage_url": extracted_homepage_url_from_report}
            
        except APITimeoutError as e:
            error_msg = f"OpenAI Timeout error for '{company_name}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "report_text": None, "sources": [], "extracted_homepage_url": None}
        except RateLimitError as e:
            error_msg = f"OpenAI Rate Limit error for '{company_name}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "report_text": None, "sources": [], "extracted_homepage_url": None}
        except APIError as e:
            error_msg = f"OpenAI API error for '{company_name}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "report_text": None, "sources": [], "extracted_homepage_url": None}
        except Exception as e:
            error_msg = f"Unexpected error for '{company_name}': {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return {"error": error_msg, "report_text": None, "sources": [], "extracted_homepage_url": None}


# Код для тестового запуска при прямом выполнении файла
if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    
    async def test_finder():
        # Configure logging
        logging.basicConfig(level=logging.INFO, 
                           format='%(asctime)s - %(levelname)s - %(message)s')
        
        # Load environment variables
        load_dotenv()
        
        # Get API key
        openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if not openai_api_key:
            print("Error: OPENAI_API_KEY not found in .env file")
            return
        
        # Create finder
        finder = LLMDeepSearchFinder(openai_api_key, verbose=True)
        
        # Test companies
        test_companies = ["Microsoft"]
        
        # Specific aspects for research
        specific_aspects = [
            "latest annual revenue",
            "key products",
            "CEO name"
        ]
        
        for company in test_companies:
            print(f"\nTest search for company: {company}")
            result = await finder.find(
                company, 
                specific_aspects=specific_aspects,
                user_context="Focus on cloud services and AI products"
            )
            
            if result["result"]:
                print(f"Received report ({len(result['result'])} characters)")
                print(f"First 200 characters: {result['result'][:200]}...")
                
                if result["sources"]:
                    print(f"\nSources ({len(result['sources'])}):")
                    for i, source in enumerate(result['sources'][:3], 1):
                        print(f"{i}. {source['title']}: {source['url']}")
                    if len(result['sources']) > 3:
                        print(f"...and {len(result['sources']) - 3} more sources")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")
    
    # Run test function
    asyncio.run(test_finder()) 