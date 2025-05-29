"""
Скрипт для нормализации URL во входных данных.

Этот скрипт читает файл CSV/Excel, нормализует URL во второй колонке
и сохраняет файл с нормализованными URL обратно.
"""

import pandas as pd
import os
import logging
import argparse
from pathlib import Path
import aiohttp
import asyncio
import socket
from urllib.parse import urlparse
import time
from typing import Optional, Tuple, List
import ssl
from src.input_validators import normalize_domain
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def get_url_status_and_final_location_async(
    url: str, 
    session: aiohttp.ClientSession, 
    timeout: float = 10.0,
    scrapingbee_client: Optional[CustomScrapingBeeClient] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Асинхронно проверяет "жизнеспособность" URL, следует редиректам и возвращает финальный URL.

    Args:
        url: URL для проверки.
        session: Экземпляр aiohttp.ClientSession.
        timeout: Общий таймаут для запроса в секундах.
        scrapingbee_client: Опциональный клиент ScrapingBee для продвинутой проверки URL.

    Returns:
        Кортеж (is_live: bool, final_url: Optional[str], error_message: Optional[str]):
        - is_live: True, если URL доступен и отвечает успешно (или редиректит на успешный URL).
        - final_url: Конечный URL после всех редиректов. None, если URL неживой или ошибка.
        - error_message: Сообщение об ошибке, если URL неживой или произошла ошибка.
    """
    if not url or not isinstance(url, str):
        return False, None, "URL отсутствует или имеет неверный тип"

    common_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
    }

    original_url = url
    # Если URL не начинается с протокола, добавляем https:// по умолчанию
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    # Определяем порядок попыток
    # Первая попытка - это URL "как есть" после добавления https:// если протокола не было
    # Вторая попытка - инвертированный протокол (с https на http, или с http на https)

    urls_to_try = []
    first_try_url = url # Уже с https://, если нужно
    urls_to_try.append(first_try_url)

    if first_try_url.startswith("https://"):
        urls_to_try.append(f"http://{original_url.replace('https://','').replace('http://','')}")
    elif first_try_url.startswith("http://"):
         urls_to_try.append(f"https://{original_url.replace('https://','').replace('http://','')}")
    else: # Если URL был без протокола и https был добавлен по умолчанию
        urls_to_try.append(f"http://{original_url}")

    processed_url = url # URL, который будет использоваться для попыток (может меняться с http на https и наоборот)
    
    last_aiohttp_error_message = f"Все попытки проверки для {original_url} через aiohttp не удались"

    for attempt_num, current_url_to_try in enumerate(filter(None, urls_to_try)): # filter(None, ...) уберет возможный None из списка
        if not current_url_to_try: # Пропускаем вторую попытку, если первая была http или URL был без протокола
            continue

        logger.info(f"[URL_CHECK] Aiohttp Попытка {attempt_num + 1} для URL: {current_url_to_try}")
        try:
            parsed_url = urlparse(current_url_to_try)
            hostname = parsed_url.hostname

            if not hostname:
                logger.warning(f"[URL_CHECK] Не удалось извлечь хост из URL: {current_url_to_try}")
                if attempt_num == 0 and processed_url.startswith("https://"): continue # Даем шанс http
                last_aiohttp_error_message = f"Не удалось извлечь хост из URL: {current_url_to_try}"
                continue # К следующей попытке aiohttp

            # 1. Проверка DNS (опционально, но может ускорить отказ для неверных доменов)
            try:
                await asyncio.get_event_loop().getaddrinfo(hostname, None)
                logger.debug(f"[URL_CHECK] DNS для {hostname} успешно разрешен.")
            except socket.gaierror:
                logger.warning(f"[URL_CHECK] Ошибка разрешения DNS для {hostname} (из URL: {current_url_to_try})")
                if attempt_num == 0 and processed_url.startswith("https://"): continue # Даем шанс http
                last_aiohttp_error_message = f"Ошибка разрешения DNS для {hostname}"
                continue # К следующей попытке aiohttp
            except Exception as e_dns: # Другие ошибки DNS
                logger.warning(f"[URL_CHECK] Неожиданная ошибка DNS для {hostname}: {e_dns}")
                # Не прерываем здесь, дадим шанс HTTP запросу

            # 2. HEAD запрос для проверки доступности и редиректов
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with session.head(current_url_to_try, timeout=client_timeout, allow_redirects=True, headers=common_headers) as response:
                final_url_after_redirect = str(response.url)
                logger.info(f"[URL_CHECK] HEAD для {current_url_to_try}: статус {response.status}, финальный URL: {final_url_after_redirect}")

                if 200 <= response.status < 400: # Успешный статус или редирект, который разрешился успешно
                    return True, final_url_after_redirect, None
                elif response.status == 500 and final_url_after_redirect != current_url_to_try:
                    # Если сервер вернул 500, но есть редирект на другой URL - проверим конечный URL
                    logger.info(f"[URL_CHECK] Статус 500 для {current_url_to_try}, но есть редирект на {final_url_after_redirect}. Считаем успешным.")
                    return True, final_url_after_redirect, None
                elif response.status == 403: # Forbidden часто означает, что сайт жив, но блокирует HEAD
                     logger.warning(f"[URL_CHECK] HEAD для {current_url_to_try} вернул 403. Пробуем GET.")
                     async with session.get(current_url_to_try, timeout=client_timeout, allow_redirects=True, headers=common_headers) as get_response:
                        final_get_url = str(get_response.url)
                        logger.info(f"[URL_CHECK] GET (после 403) для {current_url_to_try}: статус {get_response.status}, финальный URL: {final_get_url}")
                        if 200 <= get_response.status < 400:
                            return True, final_get_url, None
                        else:
                            if attempt_num == 0 and processed_url.startswith("https://"): continue
                            # return False, None, f"Статус GET (после 403) {get_response.status} для {current_url_to_try}"
                            last_aiohttp_error_message = f"Статус GET (после 403) {get_response.status} для {current_url_to_try}"
                            continue # К следующей попытке aiohttp
                else: # Другие ошибки (404, 5xx и т.д.)
                    error_msg = f"Статус HEAD {response.status} для {current_url_to_try}"
                    logger.warning(f"[URL_CHECK] {error_msg}")
                    if attempt_num == 0 and processed_url.startswith("https://"): continue
                    # return False, None, error_msg
                    last_aiohttp_error_message = error_msg
                    continue # К следующей попытке aiohttp

        except asyncio.TimeoutError:
            logger.warning(f"[URL_CHECK] Таймаут запроса к {current_url_to_try} (лимит: {timeout}с)")
            if attempt_num == 0 and processed_url.startswith("https://"): continue
            # return False, None, f"Таймаут запроса к {current_url_to_try}"
            last_aiohttp_error_message = f"Таймаут запроса к {current_url_to_try}"
            continue # К следующей попытке aiohttp
        except aiohttp.ClientSSLError as e_ssl:
            logger.warning(f"[URL_CHECK] Ошибка SSL для {current_url_to_try}: {e_ssl}. Пробуем без SSL проверки или http.")
            # Попробуем без SSL верификации (если это первая попытка с https)
            if attempt_num == 0 and current_url_to_try.startswith("https://"):
                 try:
                    # Временный SSLContext без проверки
                    no_verify_ssl_context = ssl.create_default_context()
                    no_verify_ssl_context.check_hostname = False
                    no_verify_ssl_context.verify_mode = ssl.CERT_NONE
                    custom_connector = aiohttp.TCPConnector(ssl=no_verify_ssl_context)
                    async with aiohttp.ClientSession(connector=custom_connector, headers=common_headers) as temp_session: # Создаем временную сессию с кастомным коннектором
                        async with temp_session.head(current_url_to_try, timeout=client_timeout, allow_redirects=True) as response_no_ssl:
                            final_url_no_ssl = str(response_no_ssl.url)
                            logger.info(f"[URL_CHECK] HEAD (без SSL проверки) для {current_url_to_try}: статус {response_no_ssl.status}, финальный URL: {final_url_no_ssl}")
                            if 200 <= response_no_ssl.status < 400:
                                return True, final_url_no_ssl, None
                            # Если и это не помогло, вторая итерация цикла (с http) все равно будет
                 except Exception as e_no_ssl:
                     logger.warning(f"[URL_CHECK] Ошибка при попытке без SSL проверки для {current_url_to_try}: {e_no_ssl}")
            # Если это была вторая попытка (http) или ошибка SSL не на https, то это неудача
            if attempt_num == 1 or not current_url_to_try.startswith("https://"):
                 # return False, None, f"Ошибка SSL для {current_url_to_try}: {e_ssl}"
                 last_aiohttp_error_message = f"Ошибка SSL для {current_url_to_try}: {e_ssl}"
                 # Не выходим, а продолжаем, чтобы дать шанс ScrapingBee
            # Иначе, даем шанс второй итерации (с http)
            continue

        except aiohttp.ClientConnectorError as e_conn: # Ошибки соединения (например, Connection Refused)
            logger.warning(f"[URL_CHECK] Ошибка соединения для {current_url_to_try}: {e_conn}")
            if attempt_num == 0 and processed_url.startswith("https://"): continue
            # return False, None, f"Ошибка соединения для {current_url_to_try}: {e_conn}"
            last_aiohttp_error_message = f"Ошибка соединения для {current_url_to_try}: {e_conn}"
            continue # К следующей попытке aiohttp
        except aiohttp.ClientError as e_client: # Другие ошибки клиента aiohttp
            logger.warning(f"[URL_CHECK] Ошибка клиента Aiohttp для {current_url_to_try}: {e_client}")
            if attempt_num == 0 and processed_url.startswith("https://"): continue
            # return False, None, f"Ошибка клиента Aiohttp для {current_url_to_try}: {e_client}"
            last_aiohttp_error_message = f"Ошибка клиента Aiohttp для {current_url_to_try}: {e_client}"
            continue # К следующей попытке aiohttp
        except Exception as e: # Любые другие неожиданные ошибки
            logger.error(f"[URL_CHECK] Неожиданная ошибка при проверке {current_url_to_try}: {e}", exc_info=True)
            if attempt_num == 0 and processed_url.startswith("https://"): continue
            # return False, None, f"Неожиданная ошибка при проверке {current_url_to_try}: {str(e)}"
            last_aiohttp_error_message = f"Неожиданная ошибка при проверке {current_url_to_try}: {str(e)}"
            continue # К следующей попытке aiohttp
            
    # Если все попытки aiohttp не увенчались успехом, пробуем проверить базовый домен (без пути)
    # перед тем как переходить к ScrapingBee
    parsed_original = urlparse(url if url.startswith(('http://', 'https://')) else f'https://{original_url}')
    base_domain_url = f"{parsed_original.scheme}://{parsed_original.netloc}"
    
    # Проверяем базовый домен только если исходный URL содержал путь
    if parsed_original.path and parsed_original.path != '/' and base_domain_url != url:
        logger.info(f"[URL_CHECK] Основной URL не прошел проверку. Проверяем базовый домен: {base_domain_url}")
        try:
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with session.head(base_domain_url, timeout=client_timeout, allow_redirects=True, headers=common_headers) as response:
                final_url_base = str(response.url)
                logger.info(f"[URL_CHECK] HEAD базового домена {base_domain_url}: статус {response.status}, финальный URL: {final_url_base}")
                
                if 200 <= response.status < 400:
                    return True, final_url_base, None
                elif response.status == 500 and final_url_base != base_domain_url:
                    logger.info(f"[URL_CHECK] Статус 500 для базового домена {base_domain_url}, но есть редирект на {final_url_base}. Считаем успешным.")
                    return True, final_url_base, None
        except Exception as e_base:
            logger.warning(f"[URL_CHECK] Ошибка при проверке базового домена {base_domain_url}: {e_base}")
    
    # Если все попытки aiohttp не увенчались успехом, пробуем ScrapingBee, если клиент предоставлен
    if scrapingbee_client:
        logger.info(f"[URL_CHECK] Aiohttp не смог проверить URL: {original_url}. Пробуем через ScrapingBee.")
        try:
            # Используем оригинальный URL (до добавления http/https) для ScrapingBee, 
            # так как он может сам определить протокол или иметь свои предпочтения
            # Хотя, передача URL с протоколом (например, https) обычно надежнее
            url_for_sb = url if url.startswith(("http://", "https://")) else f"https://{original_url}"

            # Параметры для ScrapingBee: render_js=False для экономии, если нам нужен только статус и редиректы
            # Для сайтов типа Fiverr, где может быть JS-защита, render_js=True может быть необходим
            params = {'render_js': True, 'follow_redirect': True} # follow_redirect уже по умолчанию True у SB
            
            # Предполагается, что у ScrapingBeeClient есть метод get_website_data_async, который должен возвращать (html_content, status_code, final_url_or_error)
            html_content, status_code, final_url_or_error = await scrapingbee_client.fetch_website_data_via_sb_async(url_for_sb, render_js=True)

            if status_code and 200 <= status_code < 400:
                final_sb_url = final_url_or_error # Если успешно, это должен быть final_url
                logger.info(f"[URL_CHECK] ScrapingBee для {url_for_sb}: статус {status_code}, финальный URL: {final_sb_url}")
                return True, final_sb_url, None
            else:
                error_msg_sb = f"ScrapingBee не смог получить {url_for_sb}, статус: {status_code}, ответ: {final_url_or_error}"
                logger.warning(f"[URL_CHECK] {error_msg_sb}")
                # Возвращаем исходную ошибку aiohttp и добавляем ошибку ScrapingBee
                return False, None, f"{last_aiohttp_error_message}; ScrapingBee: {error_msg_sb}"


        except Exception as e_sb:
            logger.error(f"[URL_CHECK] Ошибка при использовании ScrapingBee для {original_url}: {e_sb}", exc_info=True)
            # Возвращаем исходную ошибку aiohttp и добавляем ошибку ScrapingBee
            return False, None, f"{last_aiohttp_error_message}; ScrapingBee error: {str(e_sb)}"

    # Если и ScrapingBee не помог (или не был доступен), возвращаем последнюю ошибку от aiohttp
    logger.warning(f"[URL_CHECK] Все попытки проверки для {original_url} не удались (включая ScrapingBee, если использовался).")
    return False, None, last_aiohttp_error_message

def normalize_urls_in_file(input_file: str, output_file: str = None) -> str:
    """
    Нормализует URL во второй колонке файла и сохраняет результат.
    
    Args:
        input_file: Путь к входному файлу (CSV или Excel)
        output_file: Путь для сохранения результата (если не указан, перезаписывает входной файл)
        
    Returns:
        str: Путь к файлу с нормализованными URL
    """
    # Если output_file не указан, используем input_file
    if not output_file:
        output_file = input_file
    
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Файл не найден: {input_file}")
    
    # Определяем формат файла
    is_excel = input_path.suffix.lower() in ['.xlsx', '.xls']
    
    try:
        # Загружаем файл
        df = pd.read_excel(input_file) if is_excel else pd.read_csv(input_file)
        
        # Проверяем, есть ли хотя бы две колонки
        if df.shape[1] < 2:
            logger.error(f"В файле {input_file} меньше двух колонок")
            return None
        
        # Получаем имена колонок
        column_names = df.columns.tolist()
        first_column = column_names[0]
        second_column = column_names[1]
        
        # Нормализуем URL во второй колонке
        logger.info(f"Нормализация URL в колонке '{second_column}'")
        normalized_urls = []
        changes_count = 0
        
        for url in df[second_column]:
            if pd.isna(url) or not url:
                normalized_urls.append(url)
            else:
                url_str = str(url).strip()
                normalized_url = normalize_domain(url_str)
                normalized_urls.append(normalized_url)
                if normalized_url != url_str:
                    changes_count += 1
                    logger.info(f"Нормализовано: '{url_str}' -> '{normalized_url}'")
        
        # Заменяем значения во второй колонке
        df[second_column] = normalized_urls
        
        # Сохраняем файл
        if is_excel:
            df.to_excel(output_file, index=False)
        else:
            df.to_csv(output_file, index=False)
        
        logger.info(f"Нормализовано {changes_count} URL")
        logger.info(f"Файл сохранен: {output_file}")
        
        return output_file
    
    except Exception as e:
        logger.error(f"Ошибка при нормализации URL: {e}")
        return None

def remove_duplicates_by_domain(input_file: str, output_file: str = None) -> tuple[str, dict]:
    """
    Удаляет дубликаты компаний по нормализованным доменам.
    
    Args:
        input_file: Путь к входному файлу с нормализованными URL (CSV или Excel)
        output_file: Путь для сохранения результата (если не указан, перезаписывает входной файл)
        
    Returns:
        tuple: (путь к файлу без дубликатов, словарь с информацией о дедупликации)
    """
    # Если output_file не указан, используем input_file
    if not output_file:
        output_file = input_file
    
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Файл не найден: {input_file}")
    
    # Определяем формат файла
    is_excel = input_path.suffix.lower() in ['.xlsx', '.xls']
    
    try:
        # Загружаем файл
        if is_excel:
            df = pd.read_excel(input_file, engine='openpyxl')
        else:
            df = pd.read_csv(input_file)
        
        # Определяем колонку с URL
        url_column = None
        
        # Проверяем первые две колонки
        for i in range(min(2, len(df.columns))):
            col = df.columns[i]
            if df[col].dtype == 'object' and df[col].str.contains('http|www', case=False, na=False).any():
                url_column = col
                break
        
        # Если колонка с URL не найдена, ищем по индексу 1 (вторая колонка)
        if url_column is None and len(df.columns) > 1:
            url_column = df.columns[1]
        
        # Если колонка все равно не найдена, используем первую колонку
        if url_column is None:
            url_column = df.columns[0]
        
        original_row_count = len(df)
        logger.info(f"Поиск дубликатов по доменам в колонке '{url_column}'")
        logger.info(f"Всего строк в файле до удаления дубликатов: {original_row_count}")
        
        # Словарь для отслеживания уникальных доменов
        unique_domains = {}
        # Список для хранения дубликатов
        duplicate_rows = []
        
        # Проходим по всем строкам датафрейма
        for index, row in df.iterrows():
            # Получаем URL или домен и название компании
            url = str(row[url_column]) if pd.notna(row[url_column]) else ""
            company_name = str(row[df.columns[0]]) if pd.notna(row[df.columns[0]]) else "Unknown"
            
            # Нормализуем домен
            domain = normalize_domain(url)
            
            logger.info(f"Проверка компании: '{company_name}' с доменом '{domain}'")
            
            # Если домен уже был встречен, это дубликат
            if domain in unique_domains and domain:  # Проверяем, что домен не пустой
                logger.info(f"Найден дубликат домена '{domain}' для компании '{company_name}'")
                duplicate_rows.append(index)
            else:
                # Запоминаем домен и индекс строки
                unique_domains[domain] = index
        
        # Если есть дубликаты, удаляем их и сохраняем датафрейм
        duplicate_count = len(duplicate_rows)
        
        if duplicate_count > 0:
            duplicate_domains = []
            for index in duplicate_rows:
                url = str(df.loc[index, url_column]) if pd.notna(df.loc[index, url_column]) else ""
                domain = normalize_domain(url)
                if domain and domain not in duplicate_domains:
                    duplicate_domains.append(domain)
            
            logger.info(f"Удаление {duplicate_count} дубликатов по следующим доменам: {', '.join(duplicate_domains)}")
            
            # Сохраняем дубликаты в отдельный файл
            duplicates_df = df.loc[duplicate_rows]
            duplicates_output_file = f"{os.path.splitext(output_file)[0]}_duplicates{os.path.splitext(output_file)[1]}"
            
            # Удаляем дубликаты
            df = df.drop(duplicate_rows)
            logger.info(f"Осталось {len(df)} компаний с уникальными доменами")
            
            # Сохраняем датафрейм без дубликатов
            if is_excel:
                df.to_excel(output_file, index=False, engine='openpyxl')
            else:
                df.to_csv(output_file, index=False)
            
            # Сохраняем дубликаты
            if is_excel:
                duplicates_df.to_excel(duplicates_output_file, index=False, engine='openpyxl')
            else:
                duplicates_df.to_csv(duplicates_output_file, index=False)
            
            logger.info(f"Удалено {duplicate_count} дубликатов")
            logger.info(f"Файл без дубликатов сохранен: {output_file}")
            logger.info(f"Дубликаты сохранены в файл: {duplicates_output_file}")
        else:
            logger.info("Дубликаты по доменам не найдены")
            
        # Собираем информацию о дедупликации
        deduplication_info = {
            "original_count": original_row_count,
            "duplicates_removed": duplicate_count,
            "final_count": len(df)
        }
        
        return output_file, deduplication_info
        
    except Exception as e:
        logger.error(f"Ошибка при удалении дубликатов: {e}")
        raise

async def normalize_and_remove_duplicates(
    input_file: str, 
    output_file: str = None, 
    session_id_for_metadata: Optional[str] = None,
    scrapingbee_client: Optional[CustomScrapingBeeClient] = None
) -> tuple[Optional[str], dict]:
    """
    Асинхронно нормализует URL, проверяет их жизнеспособность, помечает дубликаты 
    и сохраняет результат с метками статуса. Обновляет метаданные сессии.
    
    ВАЖНО: Теперь дубликаты и мертвые ссылки НЕ удаляются, а помечаются для 
    дальнейшей обработки в пайплайне с шаблонными описаниями.
    """
    if not output_file:
        # Если output_file не указан, создаем имя на основе input_file
        input_path = Path(input_file)
        # Пример: input_file = "path/to/companies.xlsx"
        # output_file_name = "processed_companies.xlsx"
        output_file_name = f"processed_{input_path.name}"
        # Сохраняем в той же директории, где и input_file, если это сессия
        # или в текущей директории, если это не путь с 'sessions'
        if input_path.parent and 'sessions' in str(input_path.parent):
             output_file_path = input_path.parent / output_file_name
        else:
            # Если input_file просто имя файла, сохраняем в текущую директорию
            output_file_path = Path(output_file_name)
    else:
        output_file_path = Path(output_file)

    # Убедимся, что директория для output_file существует
    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    
    input_path = Path(input_file)
    if not input_path.exists():
        error_msg = f"Файл не найден: {input_file}"
        logger.error(error_msg)
        return None, {"error": error_msg, "processing_messages": [{"type": "error", "message": error_msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}]}

    is_excel = input_path.suffix.lower() in ['.xlsx', '.xls']
    try:
        df = pd.read_excel(input_file) if is_excel else pd.read_csv(input_file)
        if df.empty:
             logger.warning(f"Входной файл {input_file} пуст.")
             # Создаем пустой файл результата с ожидаемыми колонками
             pd.DataFrame(columns=['Company Name', 'Website', 'Status']).to_excel(output_file_path, index=False) if is_excel else pd.DataFrame(columns=['Company Name', 'Website', 'Status']).to_csv(output_file_path, index=False)
             details = {
                "original_count": 0, "live_urls_count": 0, "dead_urls_count": 0,
                "redirected_urls_updated": 0, "duplicates_count": 0, "final_count": 0,
                "processing_messages": [{"type": "warning", "message": f"Входной файл {input_file} был пуст.", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}]
             }
             if session_id_for_metadata:
                _update_session_metadata_light(session_id_for_metadata, details)
             return str(output_file_path), details
    except Exception as e:
        error_msg = f"Ошибка при чтении файла {input_file}: {e}"
        logger.error(error_msg, exc_info=True)
        return None, {"error": error_msg, "processing_messages": [{"type": "error", "message": error_msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}]}

    if df.shape[1] < 2:
        error_msg = "Файл должен содержать как минимум две колонки: 'Company Name' и 'Website'."
        logger.error(error_msg)
        return None, {"error": error_msg, "processing_messages": [{"type": "error", "message": error_msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}]}

    # Используем первые две колонки
    company_name_col = df.columns[0]
    website_col = df.columns[1]
    
    original_company_count = len(df)
    logger.info(f"Начальная обработка {original_company_count} компаний из файла {input_file}")

    all_companies_data = []  # Все компании с их статусами
    dead_urls_count = 0
    redirected_urls_updated_count = 0
    processing_messages = [] # Локальный список сообщений для этой операции

    conn = aiohttp.TCPConnector(ssl=False) # Отключаем проверку SSL глобально для этой сессии aiohttp
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = []
        for index, row in df.iterrows():
            company_name = str(row[company_name_col])
            original_url = str(row[website_col])
            tasks.append(get_url_status_and_final_location_async(original_url, session, scrapingbee_client=scrapingbee_client))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        company_name = str(df.iloc[i][company_name_col])
        original_url = str(df.iloc[i][website_col])

        if isinstance(result, Exception):
            logger.error(f"Ошибка при обработке URL {original_url} для компании {company_name}: {result}")
            processing_messages.append({"type": "error", "message": f"URL {original_url} ({company_name}) вызвал ошибку: {result}", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
            all_companies_data.append({
                "name": company_name, 
                "original_url": original_url, 
                "final_url": original_url,
                "status": "DEAD_URL",
                "error_message": str(result)
            })
            dead_urls_count += 1 
            continue

        is_live, final_url, error_message = result
        if is_live and final_url:
            all_companies_data.append({
                "name": company_name, 
                "original_url": original_url, 
                "final_url": final_url,
                "status": "VALID"
            })
            if final_url != original_url and normalize_domain(final_url) != normalize_domain(original_url): # Считаем редиректом, только если домен изменился
                redirected_urls_updated_count += 1
                msg = f"URL для '{company_name}' изменен с {original_url} на {final_url} из-за редиректа."
                logger.info(msg)
                processing_messages.append({"type": "info", "message": msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        else:
            dead_urls_count += 1
            msg = f"URL {original_url} для компании '{company_name}' неживой. Причина: {error_message}. Компания будет помечена как DEAD_URL."
            logger.warning(msg)
            processing_messages.append({"type": "warning", "message": msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
            all_companies_data.append({
                "name": company_name, 
                "original_url": original_url, 
                "final_url": original_url,
                "status": "DEAD_URL",
                "error_message": error_message or "URL неживой"
            })
            
    logger.info(f"Проверка URL завершена. Живых URL: {len([c for c in all_companies_data if c['status'] == 'VALID'])}, Неживых URL: {dead_urls_count}, Обновлено редиректов: {redirected_urls_updated_count}")

    # Определение дубликатов по финальному URL (домену)
    seen_domains = {}  # domain -> first_company_data
    duplicates_count = 0
    
    for company_data in all_companies_data:
        if company_data["status"] == "VALID":  # Проверяем дубликаты только среди валидных URL
            domain = normalize_domain(company_data["final_url"])
            if domain in seen_domains:
                # Это дубликат
                company_data["status"] = "DUPLICATE"
                duplicates_count += 1
                msg = f"Компания '{company_data['name']}' (URL: {company_data['final_url']}) помечена как дубликат домена '{domain}'."
                logger.info(msg)
                processing_messages.append({"type": "info", "message": msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
            else:
                # Первая компания с этим доменом
                seen_domains[domain] = company_data
            
    logger.info(f"Проверка дубликатов завершена. Найдено дубликатов: {duplicates_count}.")
    
    # Создание DataFrame для сохранения (сохраняем ВСЕ компании с их статусами)
    output_df = pd.DataFrame([{
        "Company Name": cd["name"], 
        "Website": normalize_domain(cd["final_url"]) if cd["status"] == "VALID" else normalize_domain(cd["original_url"]),  # Сохраняем нормализованный домен
        "Status": cd["status"],
        "Error_Message": cd.get("error_message", "")
    } for cd in all_companies_data])

    try:
        if output_file_path.suffix.lower() in ['.xlsx', '.xls']:
            output_df.to_excel(output_file_path, index=False)
        else:
            output_df.to_csv(output_file_path, index=False)
        logger.info(f"Файл с обработанными компаниями сохранен: {output_file_path}")
    except Exception as e:
        error_msg = f"Ошибка при сохранении файла {output_file_path}: {e}"
        logger.error(error_msg, exc_info=True)
        processing_messages.append({"type": "error", "message": error_msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})

    valid_companies_count = len([c for c in all_companies_data if c["status"] == "VALID"])
    
    deduplication_details = {
        "original_count": original_company_count,
        "live_urls_count": valid_companies_count,  # Количество живых и уникальных
        "dead_urls_count": dead_urls_count,  # Изменили название с dead_urls_removed
        "redirected_urls_updated": redirected_urls_updated_count,
        "duplicates_count": duplicates_count,  # Изменили название с duplicates_removed
        "final_count": len(output_df)  # Общее количество (включая помеченные)
    }

    if session_id_for_metadata:
        # Для обратной совместимости добавляем старые поля
        deduplication_details["dead_urls_removed"] = dead_urls_count
        deduplication_details["duplicates_removed"] = duplicates_count
        _update_session_metadata_light(session_id_for_metadata, deduplication_details, processing_messages)

    return str(output_file_path), deduplication_details

def _update_session_metadata_light(session_id: str, dedup_info: dict, new_messages: Optional[List[dict]] = None):
    """Вспомогательная функция для обновления метаданных сессии."""
    try:
        from src.data_io import load_session_metadata, save_session_metadata
        logger.info(f"Обновление метаданных (light) для сессии {session_id}...")
        all_metadata = load_session_metadata()
        session_updated = False
        for session_meta in all_metadata:
            if session_meta.get("session_id") == session_id:
                session_meta["total_companies"] = dedup_info.get("final_count", 0)
                session_meta["companies_count"] = dedup_info.get("final_count", 0)
                session_meta["deduplication_info"] = dedup_info # Сохраняем все детали сюда

                current_messages = session_meta.get("processing_messages", [])
                if new_messages:
                    # Добавляем только действительно новые сообщения, проверяя по тексту и типу
                    existing_message_tuples = {(m.get("type"), m.get("message")) for m in current_messages}
                    messages_to_add_now = [
                        msg for msg in new_messages
                        if (msg.get("type"), msg.get("message")) not in existing_message_tuples
                    ]
                    if messages_to_add_now:
                         session_meta["processing_messages"] = current_messages + messages_to_add_now
                session_updated = True
                break
        
        if session_updated:
            save_session_metadata(all_metadata)
            logger.info(f"Метаданные сессии {session_id} обновлены (light).")
        else:
            logger.warning(f"Сессия {session_id} не найдена в метаданных для обновления (light).")
    except Exception as e:
        logger.error(f"Ошибка при обновлении метаданных сессии {session_id} (light): {e}", exc_info=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Нормализация URL, проверка жизнеспособности и удаление дубликатов во входных данных")
    parser.add_argument("input_file", help="Путь к входному файлу (CSV или Excel)")
    parser.add_argument("--output", "-o", help="Путь для сохранения результата (если не указан, перезаписывает входной файл)")
    parser.add_argument("--scrapingbee-api-key", help="API ключ для ScrapingBee (опционально, для улучшенной проверки URL)")
    
    args = parser.parse_args()
    
    output_file_path = args.output if args.output else args.input_file

    # Поскольку normalize_and_remove_duplicates теперь асинхронная, запускаем ее через asyncio.run()
    # Передаем None для session_id, так как из CLI мы не управляем сессиями FastAPI
    
    sb_client = None
    if args.scrapingbee_api_key:
        try:
            sb_client = CustomScrapingBeeClient(api_key=args.scrapingbee_api_key)
            logger.info("ScrapingBee client initialized for CLI.")
        except Exception as e_sb_init:
            logger.error(f"Failed to initialize ScrapingBee client: {e_sb_init}")

    loop = asyncio.get_event_loop()
    try:
        result_file, deduplication_details = loop.run_until_complete(
            normalize_and_remove_duplicates(
                args.input_file, 
                output_file_path, 
                session_id_for_metadata=None,
                scrapingbee_client=sb_client
            )
        )
        if result_file:
            logger.info(f"Обработка завершена. Результат в файле: {result_file}")
        else:
            logger.error(f"Обработка завершилась с ошибкой. Детали: {deduplication_details.get('error')}")
        
        logger.info("Детали обработки:")
        for key, value in deduplication_details.items():
            logger.info(f"  {key}: {value}")

    except Exception as e:
        logger.error(f"Критическая ошибка при запуске обработки из CLI: {e}", exc_info=True)
    finally:
        # В некоторых случаях может потребоваться закрыть event loop, особенно если были созданы специфичные ресурсы
        # loop.close() # Раскомментировать, если будут проблемы с "Event loop is closed" в некоторых окружениях
        if sb_client: # Закрываем сессию ScrapingBee, если она была создана и имеет метод close_async
            if hasattr(sb_client, 'close_async') and asyncio.iscoroutinefunction(sb_client.close_async):
                try:
                    loop.run_until_complete(sb_client.close_async())
                    logger.info("ScrapingBee сессия закрыта.")
                except Exception as e_sb_close:
                    logger.error(f"Ошибка при закрытии сессии ScrapingBee: {e_sb_close}")
        pass 