# src/llm_deep_search.py
import asyncio
import logging
import os # Для тестового запуска
import sys # Для тестового запуска
from pathlib import Path # Для тестового запуска
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
from typing import Optional, Dict, List, Any
import aiohttp
from .external_apis.serper_client import find_urls_with_serper_async
from .external_apis.scrapingbee_client import scrape_page_data_async
from .processing import get_wikipedia_summary_async

# Пока не будем добавлять tenacity, чтобы сначала проверить базовую работоспособность
# и не конфликтовать с возможными встроенными retries search-моделей.

logger = logging.getLogger(__name__)

# Список специфичных запросов (можно будет вынести в конфигурацию)
DEFAULT_DEEP_SEARCH_QUERIES = [
    "What is the company's latest reported annual revenue or ARR?",
    "What is the approximate number of employees at the company?",
    "What are the company's key products, services, or technologies?"
]

async def query_llm_deep_search_async(
    openai_client: AsyncOpenAI,
    company_name: str,
    specific_queries: Optional[List[str]] = None,
    # text_sources_for_deep_search: Optional[str] = None, # Пока не используем, модель сама ищет
    model_name: str = "gpt-4o-mini-search-preview" # Используем search-модель
) -> Dict[str, Any]:
    """
    Запрашивает у LLM (search-preview модель) специфическую информацию о компании,
    позволяя модели самой искать информацию в вебе.
    Возвращает словарь, где ключи - это стандартизированные идентификаторы запросов,
    а значения - словари с текстом запроса, ответом LLM и цитатами.
    """
    results: Dict[str, Any] = {}
    queries_to_run = specific_queries if specific_queries else DEFAULT_DEEP_SEARCH_QUERIES

    logger.info(f"[DeepSearch] Starting deep search for {company_name} with {len(queries_to_run)} queries using model {model_name}.")

    for i, query_text in enumerate(queries_to_run):
        # Используем порядковый номер + часть вопроса как ключ, чтобы было проще потом мапить, если список вопросов меняется
        # или можно использовать сам текст вопроса как ключ, если он достаточно уникален.
        # Для CSV лучше иметь предсказуемые ключи.
        query_key_base = "".join(filter(str.isalnum, query_text)).lower()[:30] # База для ключа
        query_key = f"deep_query_{i+1}_{query_key_base}"


        # Формулируем запрос к LLM так, чтобы он был сфокусирован на компании
        user_content = f"For the company named '{company_name}', find information about: {query_text}"
        # Альтернативный вариант:
        # user_content = f"Regarding the company '{company_name}', {query_text}"


        logger.debug(f"[DeepSearch] For {company_name}, Query {i+1} ('{query_key}'): '{user_content}'")

        try:
            completion_params = {
                "model": model_name,
                "messages": [{
                    "role": "user",
                    "content": user_content
                }],
                "max_tokens": 350,
            }
            # Параметр temperature убираем, так как он несовместим с search-моделями
            # if model_name not in ["gpt-4o-mini-search-preview", "gpt-4o-search-preview"]:
            #     completion_params["temperature"] = 0.1 # Можно вернуть для не-search моделей

            completion = await openai_client.chat.completions.create(**completion_params)

            if completion.choices and completion.choices[0].message and completion.choices[0].message.content:
                message_content = completion.choices[0].message.content # Сохраняем весь контент сообщения
                answer_content = message_content.strip()
                annotations = completion.choices[0].message.annotations
                
                citations_list = []
                if annotations:
                    for ann in annotations:
                        if ann.type == "url_citation" and ann.url_citation:
                            # Извлекаем цитируемый текст из основного контента сообщения
                            cited_text_segment = message_content[ann.url_citation.start_index:ann.url_citation.end_index]
                            citations_list.append({
                                "cited_text": cited_text_segment, # <--- ИЗМЕНЕНО
                                "url": ann.url_citation.url,
                                "title": ann.url_citation.title,
                                "start_index": ann.url_citation.start_index,
                                "end_index": ann.url_citation.end_index
                            })
                
                results[query_key] = {
                    "original_query": query_text, # Сохраняем исходный текст запроса
                    "answer": answer_content,
                    "citations": citations_list
                }
                logger.info(f"[DeepSearch] For {company_name}, Query: '{query_text}', LLM Answer: '{answer_content[:100]}...' (Citations: {len(citations_list)})")
            else:
                logger.warning(f"[DeepSearch] LLM returned no content for query '{query_text}' for {company_name}. Response: {completion}")
                results[query_key] = {
                    "original_query": query_text,
                    "answer": "LLM did not provide an answer.",
                    "citations": []
                }
        
        except (APIError, APITimeoutError, RateLimitError) as e_openai:
            logger.error(f"[DeepSearch] OpenAI API error for query '{query_text}' for {company_name}: {type(e_openai).__name__} - {e_openai}")
            results[query_key] = {
                "original_query": query_text,
                "answer": f"OpenAI API Error: {type(e_openai).__name__}",
                "citations": []
            }
        except Exception as e_generic:
            logger.error(f"[DeepSearch] Generic error for query '{query_text}' for {company_name}: {type(e_generic).__name__} - {e_generic}", exc_info=True)
            results[query_key] = {
                "original_query": query_text,
                "answer": f"Generic Error: {type(e_generic).__name__}",
                "citations": []
            }
        
        # OpenAI рекомендует не слать запросы слишком часто, если это не streaming.
        # Для search-моделей может быть свой rate limit.
        await asyncio.sleep(1.5) # Небольшая пауза между запросами к LLM на всякий случай

    if not results:
        logger.warning(f"[DeepSearch] No results obtained for any query for {company_name}.")
        # Возвращаем пустой словарь, чтобы вызывающая функция могла это обработать
        # или специфичный маркер ошибки, если это предпочтительнее.
        return {"error_summary": "No results from LLM deep search for any query."} 
        
    return results

async def query_llm_for_deep_info(
    openai_client: AsyncOpenAI,
    company_name: str,
    text_sources_for_deep_search: str,
    specific_queries: List[str]
) -> Dict[str, Any]:
    """
    Асинхронно запрашивает у LLM OpenAI подробную информацию о компании по списку конкретных запросов.

    Args:
        openai_client: Асинхронный клиент OpenAI.
        company_name: Название компании.
        text_sources_for_deep_search: Собранные текстовые данные о компании для глубокого анализа.
        specific_queries: Список конкретных вопросов для LLM.

    Returns:
        Словарь, где ключи - это исходные запросы, а значения - ответы LLM.
        В случае общей ошибки возвращает словарь с ключом "error".
    """
    results: Dict[str, Any] = {}
    # Рекомендуется использовать GPT-4 Turbo для таких задач из-за его способности обрабатывать большие контексты
    # и предоставлять более точные и подробные ответы.
    # Однако, для экономии или если GPT-4 Turbo недоступен, можно использовать gpt-3.5-turbo.
    # При использовании gpt-3.5-turbo, возможно, потребуется более тщательная обработка промптов
    # и разбивка информации, если text_sources_for_deep_search очень большой.
    # Актуальные модели: https://platform.openai.com/docs/models
    llm_model = "gpt-4-turbo-preview" # или "gpt-3.5-turbo" 

    for query in specific_queries:
        try:
            prompt = f"""
            Проанализируй предоставленный текст о компании '{company_name}' и ответь на следующий конкретный вопрос.
            Если информация для ответа отсутствует в тексте, укажи "Информация не найдена".
            Не добавляй никакой дополнительной информации или комментариев, которых нет в тексте.

            Текст для анализа:
            ---
            {text_sources_for_deep_search}
            ---

            Вопрос: {query}

            Ответ:
            """

            logger.info(f"Отправка запроса LLM для компании '{company_name}' по вопросу: '{query[:100]}...'")
            
            response = await openai_client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": "Ты — ИИ-ассистент, специализирующийся на извлечении конкретной бизнес-информации из текста."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0, # Низкая температура для более детерминированных и фактических ответов
                max_tokens=500  # Ограничение на длину ответа, можно настроить
            )
            
            answer = response.choices[0].message.content.strip() if response.choices and response.choices[0].message else "Не удалось получить ответ от LLM."
            results[query] = answer
            logger.info(f"Получен ответ LLM для компании '{company_name}' по вопросу '{query[:100]}...': '{answer[:100]}...'")

        except APIError as e:
            logger.error(f"Ошибка API OpenAI при запросе для компании '{company_name}' (вопрос: '{query}'): {e}")
            results[query] = f"Ошибка API: {e}"
        except Timeout as e:
            logger.error(f"Тайм-аут запроса OpenAI для компании '{company_name}' (вопрос: '{query}'): {e}")
            results[query] = f"Тайм-аут: {e}"
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при запросе LLM для компании '{company_name}' (вопрос: '{query}'): {e}")
            results[query] = f"Непредвиденная ошибка: {e}"
            # В случае общей неудачи, можно вернуть флаг ошибки для всей функции,
            # но здесь мы собираем ошибки по каждому запросу.
            # Если критично, чтобы вся операция фейлилась при одной ошибке, нужно изменить логику.

    if not results: # Если specific_queries был пуст
        return {"error": "Список специфичных запросов был пуст."}
        
    return results

async def run_llm_deep_search_pipeline(
    company_name: str,
    aiohttp_session: aiohttp.ClientSession,
    openai_client: AsyncOpenAI,
    serper_api_key: str,
    specific_queries: List[str]
) -> Dict[str, Any]:
    """
    Запускает пайплайн глубокого поиска для одной компании.
    
    Args:
        company_name: Название компании
        aiohttp_session: Сессия для HTTP запросов
        openai_client: Клиент OpenAI
        serper_api_key: API ключ Serper
        specific_queries: Список вопросов для LLM
        
    Returns:
        Dict[str, Any]: Результаты поиска
    """
    result_data = {
        "name": company_name,
        "deep_search_results": {}
    }
    
    try:
        # 1. Поиск URL через Serper
        urls = await find_urls_with_serper_async(
            company_name=company_name,
            serper_api_key=serper_api_key
        )
        
        # 2. Сбор текста из различных источников
        text_sources = []
        
        # 2.1 Скрапинг домашней страницы
        if urls.get("homepage"):
            homepage_text = await scrape_page_data_async(
                url=urls["homepage"],
                aiohttp_session=aiohttp_session
            )
            if homepage_text:
                text_sources.append(f"Homepage content:\n{homepage_text}")
        
        # 2.2 Скрапинг LinkedIn
        if urls.get("linkedin"):
            linkedin_text = await scrape_page_data_async(
                url=urls["linkedin"],
                aiohttp_session=aiohttp_session
            )
            if linkedin_text:
                text_sources.append(f"LinkedIn content:\n{linkedin_text}")
        
        # 2.3 Wikipedia summary
        wiki_summary = await get_wikipedia_summary_async(
            company_name=company_name,
            aiohttp_session=aiohttp_session
        )
        if wiki_summary:
            text_sources.append(f"Wikipedia summary:\n{wiki_summary}")
        
        # 3. Объединение всех источников
        combined_text = "\n\n".join(text_sources)
        
        # 4. Запрос к LLM
        if combined_text:
            deep_search_results = await query_llm_for_deep_info(
                openai_client=openai_client,
                company_name=company_name,
                text_sources_for_deep_search=combined_text,
                specific_queries=specific_queries
            )
            result_data["deep_search_results"] = deep_search_results
        else:
            logger.warning(f"No text sources found for company {company_name}")
            result_data["deep_search_results"] = {
                query: "No information available" for query in specific_queries
            }
            
    except Exception as e:
        logger.error(f"Error in deep search pipeline for company {company_name}: {str(e)}")
        result_data["deep_search_results"] = {
            query: f"Error: {str(e)}" for query in specific_queries
        }
    
    return result_data

# Пример использования (для тестирования):
async def main_test_deep_search():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    # Убедитесь, что переменная окружения OPENAI_API_KEY установлена
    # и что ключ имеет доступ к моделям gpt-4o-mini-search-preview или gpt-4o-search-preview
    if not os.getenv("OPENAI_API_KEY"):
        print("Please set OPENAI_API_KEY environment variable.")
        return

    client = AsyncOpenAI()
    # company = "NVIDIA Corporation"
    company = "Microsoft" 
    
    # Можно протестировать с определенным списком запросов
    # test_queries = [
    #     "What were Microsoft's key acquisitions in the last 5 years?",
    #     "Describe Microsoft's main AI initiatives or products."
    # ]
    # deep_info = await query_llm_deep_search_async(client, company, specific_queries=test_queries)
    
    deep_info = await query_llm_deep_search_async(client, company)
    
    print(f"\n--- Deep Search Results for {company} ---")
    if "error_summary" in deep_info:
        print(f"Error: {deep_info['error_summary']}")
    else:
        for key, value_dict in deep_info.items():
            print(f"\n  Processed Query Key: {key}")
            print(f"  Original Query: {value_dict.get('original_query')}")
            print(f"  Answer: {value_dict.get('answer')}")
            if value_dict.get('citations'):
                print(f"  Citations:")
                for cit in value_dict['citations']:
                    print(f"    - Cited Text: \"{cit.get('cited_text', 'N/A')}\"") # <--- ИЗМЕНЕНО
                    print(f"      URL: [{cit.get('title', 'N/A')}]({cit.get('url')})")
            print("  ---")

if __name__ == '__main__':
    # Для запуска этого теста: python -m src.llm_deep_search
    # (предполагая, что ваш CWD - это корень проекта)
    # или настройте sys.path, если запускаете иначе.
    
    if __package__ is None or __package__ == '':
        SCRIPT_DIR = Path(__file__).resolve().parent
        PROJECT_ROOT_FOR_TEST = SCRIPT_DIR.parent 
        sys.path.insert(0, str(PROJECT_ROOT_FOR_TEST))
        print(f"Adjusted sys.path for direct execution: {sys.path[0]}")
    
    asyncio.run(main_test_deep_search())