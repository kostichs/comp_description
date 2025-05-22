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
from typing import Optional, Tuple
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
    Асинхронно нормализует URL, проверяет их жизнеспособность, обрабатывает редиректы,
    удаляет дубликаты по доменам и компании с неживыми URL.
    
    Args:
        input_file: Путь к входному файлу (CSV или Excel)
        output_file: Путь для сохранения результата (если не указан, перезаписывает входной файл)
        session_id_for_metadata: ID сессии для обновления метаданных (если None, метаданные не обновляются)
        scrapingbee_client: Опциональный клиент ScrapingBee для продвинутой проверки URL.
        
    Returns:
        tuple: (путь к файлу без дубликатов, словарь с информацией об обработке)
               Возвращает (None, info_dict) если произошла критическая ошибка при загрузке файла.
    """
    if not output_file:
        output_file = input_file
    
    input_path = Path(input_file)
    if not input_path.exists():
        logger.error(f"Файл не найден: {input_file}")
        # Возвращаем None для пути файла и информацию об ошибке
        return None, {
            "error": f"Файл не найден: {input_file}",
            "original_count": 0,
            "live_urls_count": 0,
            "dead_urls_removed": 0,
            "redirected_urls_updated": 0,
            "duplicates_removed": 0,
            "final_count": 0,
            "processing_messages": [{"type": "error", "message": f"Файл не найден: {input_file}", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}]
        }

    is_excel = input_path.suffix.lower() in ['.xlsx', '.xls']
    
    processing_info = {
        "original_count": 0,
        "live_urls_count": 0,
        "dead_urls_removed": 0,
        "redirected_urls_updated": 0,
        "duplicates_removed": 0,
        "final_count": 0,
        "processing_messages": []
    }

    try:
        df = pd.read_excel(input_file, engine='openpyxl') if is_excel else pd.read_csv(input_file)
    except Exception as e:
        logger.error(f"Ошибка загрузки файла {input_file}: {e}")
        processing_info["error"] = f"Ошибка загрузки файла: {e}"
        processing_info["processing_messages"].append({"type": "error", "message": f"Ошибка загрузки файла: {e}", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        return None, processing_info


    processing_info["original_count"] = len(df)
    if df.empty:
        logger.info(f"Файл {input_file} пуст. Пропускаем обработку.")
        processing_info["processing_messages"].append({"type": "info", "message": "Исходный файл пуст.", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        # Сохраняем пустой файл, если output_file отличается или если это требуется
        if is_excel:
            df.to_excel(output_file, index=False, engine='openpyxl')
        else:
            df.to_csv(output_file, index=False)
        return output_file, processing_info


    # Определяем колонку с URL (обычно вторая)
    url_column_name = df.columns[1] if len(df.columns) > 1 else df.columns[0]
    company_column_name = df.columns[0]

    # --- Шаг 1: Асинхронная проверка жизнеспособности URL и обновление ---
    valid_rows = []
    tasks = []
    
    # Используем общий SSLContext, который не проверяет сертификаты, если основная проверка SSL не удалась в get_url_status_and_final_location_async
    # Однако, get_url_status_and_final_location_async уже имеет логику повторных попыток с отключением SSL, так что здесь стандартный
    connector = aiohttp.TCPConnector(ssl=False) # Отключаем проверку SSL на уровне коннектора для большей устойчивости, если это глобально приемлемо
                                               # или можно оставить ssl=None для стандартной проверки и положиться на логику в get_url_status_and_final_location_async
    
    async with aiohttp.ClientSession(connector=connector) as http_session:
        for index, row in df.iterrows():
            original_url = str(row[url_column_name]).strip() if pd.notna(row[url_column_name]) else ""
            company_name = str(row[company_column_name]).strip() if pd.notna(row[company_column_name]) else "Unknown Company"
            
            if not original_url:
                logger.info(f"Для компании '{company_name}' URL отсутствует. Строка будет сохранена без изменений URL.")
                # Мы все еще можем захотеть сохранить эту строку, если она не будет удалена как дубликат позже
                # Поэтому просто добавляем ее с пустым 'processed_url'
                # valid_rows.append({**row.to_dict(), '_original_url': original_url, '_processed_url': "", '_domain_for_dedup': ""})
                # Вместо valid_rows, мы будем сразу добавлять в tasks None или placeholder, 
                # чтобы сохранить порядок для сопоставления с df.iterrows()
                tasks.append(None) # Placeholder для строк без URL
                continue

            tasks.append(get_url_status_and_final_location_async(original_url, http_session, scrapingbee_client=scrapingbee_client))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    temp_df_rows = []
    # current_df_idx = 0 # Индекс для сопоставления с исходным df - теперь не нужен, т.к. results имеет ту же длину, что и df

    # for i, row_data in enumerate(df.to_dict(orient='records')):
    for i, (df_index, row_series) in enumerate(df.iterrows()): # Используем iterrows для доступа к данным строки как Series
        row_data = row_series.to_dict()
        original_url_for_row = str(row_data.get(url_column_name, "")).strip()
        company_name_for_row = str(row_data.get(company_column_name, "Unknown Company")).strip()

        res = results[i] # Получаем результат по тому же индексу, что и строка в df

        if res is None: # Это placeholder для строк, где URL отсутствовал
            temp_df_rows.append({**row_data, '_original_url': "", '_processed_url': "", '_domain_for_dedup': ""})
            continue 

        # if not original_url_for_row: # Если URL изначально отсутствовал - эта логика теперь выше, через placeholder
        #     temp_df_rows.append({**row_data, '_original_url': "", '_processed_url': "", '_domain_for_dedup': ""})
        #     continue # Переходим к следующей строке из df

        # # Теперь берем результат из `results`
        # res = results[current_df_idx]
        # current_df_idx +=1 # Увеличиваем индекс для следующего непустого URL


        if isinstance(res, Exception):
            logger.error(f"Ошибка при проверке URL {original_url_for_row} для компании '{company_name_for_row}': {res}")
            processing_info["dead_urls_removed"] += 1
            msg = f"Компания '{company_name_for_row}' ({original_url_for_row}) удалена: ошибка проверки URL ({res})."
            processing_info["processing_messages"].append({"type": "warning", "message": msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
            continue # Пропускаем эту компанию

        is_live, final_url, error_message = res

        if not is_live:
            logger.warning(f"URL {original_url_for_row} для компании '{company_name_for_row}' неживой. Причина: {error_message}. Компания будет удалена.")
            processing_info["dead_urls_removed"] += 1
            msg = f"Компания '{company_name_for_row}' ({original_url_for_row}) удалена: URL неактивен ({error_message})."
            processing_info["processing_messages"].append({"type": "info", "message": msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
            continue # Пропускаем эту компанию

        processing_info["live_urls_count"] += 1
        updated_url = final_url if final_url else original_url_for_row # Используем final_url если он есть
        
        if final_url and original_url_for_row != final_url:
            logger.info(f"URL для компании '{company_name_for_row}' обновлен с {original_url_for_row} на {final_url} (редирект).")
            processing_info["redirected_urls_updated"] += 1
            msg = f"URL для '{company_name_for_row}' изменен с {original_url_for_row} на {final_url} из-за редиректа."
            processing_info["processing_messages"].append({"type": "info", "message": msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        
        normalized_final_domain = normalize_domain(updated_url)
        
        new_row_data = {**row_data}
        new_row_data[url_column_name] = updated_url # Обновляем URL в данных
        new_row_data['_original_url'] = original_url_for_row
        new_row_data['_processed_url'] = updated_url
        new_row_data['_domain_for_dedup'] = normalized_final_domain
        temp_df_rows.append(new_row_data)

    if not temp_df_rows:
        logger.info("После проверки жизнеспособности URL не осталось валидных компаний.")
        df_processed = pd.DataFrame(columns=df.columns) # Создаем пустой DataFrame с теми же колонками
    else:
        df_processed = pd.DataFrame(temp_df_rows)
        # Удаляем временные колонки, если они не нужны в финальном файле
        # df_processed = df_processed.drop(columns=['_original_url', '_processed_url', '_domain_for_dedup'], errors='ignore')

    # --- Шаг 2: Нормализация URL в DataFrame (если еще не сделано для final_url) и Дедупликация ---
    # Убедимся, что URL-колонка содержит именно те URL, по которым будем делать дедупликацию.
    # '_domain_for_dedup' уже содержит нормализованный домен от final_url (или пусто, если URL не было).

    # Логика дедупликации:
    unique_domains_map = {} # {domain: index_in_df_processed}
    rows_to_drop_indices = []
    
    # Проходим по df_processed для дедупликации
    # Важно: df_processed уже отфильтрован от "мертвых" URL
    for index, row_series in df_processed.iterrows():
        # Используем _domain_for_dedup, который мы рассчитали ранее
        domain_to_check = row_series['_domain_for_dedup']
        company_name = str(row_series[company_column_name]) if pd.notna(row_series[company_column_name]) else "Unknown"

        if not domain_to_check: # Если домена нет (например, URL отсутствовал изначально), не считаем дубликатом
            logger.info(f"Компания '{company_name}' не имеет домена для проверки дубликатов, строка сохраняется.")
            continue

        if domain_to_check in unique_domains_map:
            logger.info(f"Найден дубликат домена '{domain_to_check}' для компании '{company_name}'. Компания будет удалена.")
            rows_to_drop_indices.append(index)
            processing_info["duplicates_removed"] += 1
            # Можно добавить сообщение в processing_messages, если нужно детализировать какой дубликат удален
            msg = f"Компания '{company_name}' (URL: {row_series['_processed_url']}) удалена как дубликат домена '{domain_to_check}'."
            processing_info["processing_messages"].append({"type": "info", "message": msg, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        else:
            unique_domains_map[domain_to_check] = index
            logger.info(f"Компания '{company_name}' с доменом '{domain_to_check}' добавлена как уникальная.")

    if rows_to_drop_indices:
        df_final = df_processed.drop(rows_to_drop_indices)
        logger.info(f"Удалено {len(rows_to_drop_indices)} дубликатов по домену.")
    else:
        df_final = df_processed
        logger.info("Дубликаты по доменам не найдены после проверки жизнеспособности URL.")

    # Удаляем временные колонки перед сохранением
    df_final = df_final.drop(columns=['_original_url', '_processed_url', '_domain_for_dedup'], errors='ignore')
    
    processing_info["final_count"] = len(df_final)

    # --- Шаг 3: Сохранение результата ---
    try:
        if is_excel:
            df_final.to_excel(output_file, index=False, engine='openpyxl')
        else:
            df_final.to_csv(output_file, index=False)
        logger.info(f"Файл с обработанными компаниями сохранен: {output_file}")
    except Exception as e:
        logger.error(f"Ошибка сохранения файла {output_file}: {e}")
        processing_info["error"] = f"Ошибка сохранения файла: {e}"
        # Обновляем сообщение об ошибке, если оно уже есть, или добавляем новое
        error_msg_obj = next((msg for msg in processing_info["processing_messages"] if msg.get("type") == "error"), None)
        if error_msg_obj:
            error_msg_obj["message"] += f"; Ошибка сохранения файла: {e}"
        else:
            processing_info["processing_messages"].append({"type": "error", "message": f"Ошибка сохранения файла: {e}", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        # В этом случае output_file может быть не создан или быть неполным
        # но мы все равно возвращаем имя файла, куда пытались сохранить

    # --- Шаг 4: Обновление метаданных сессии (если session_id предоставлен) ---
    if session_id_for_metadata:
        try:
            from src.data_io import load_session_metadata, save_session_metadata
            
            all_metadata = load_session_metadata()
            session_found_and_updated = False
            for meta_idx, meta in enumerate(all_metadata):
                if meta.get("session_id") == session_id_for_metadata:
                    logger.info(f"Обновление метаданных для сессии {session_id_for_metadata}...")
                    meta["original_companies_count"] = processing_info["original_count"] # Исходное до всех проверок
                    meta["companies_count"] = processing_info["final_count"] # Итоговое после всех проверок и дедупликации
                    meta["total_companies"] = processing_info["final_count"] # Это поле используется фронтендом
                    
                    # Объединяем существующие processing_messages с новыми
                    if "processing_messages" not in meta:
                        meta["processing_messages"] = []
                    
                    # Добавляем новые сообщения, избегая дублирования по тексту и типу
                    existing_messages_tuples = {(m.get("type"), m.get("message")) for m in meta["processing_messages"]}
                    for new_msg in processing_info["processing_messages"]:
                        if (new_msg.get("type"), new_msg.get("message")) not in existing_messages_tuples:
                            meta["processing_messages"].append(new_msg)
                            existing_messages_tuples.add((new_msg.get("type"), new_msg.get("message")))

                    # Добавляем общую информацию о дедупликации и проверке URL
                    # Это поле может быть расширено, если фронтенд ожидает более структурированную информацию
                    meta["extended_deduplication_info"] = {
                        "original_upload_count": processing_info["original_count"],
                        "dead_urls_removed": processing_info["dead_urls_removed"],
                        "redirected_urls_updated": processing_info["redirected_urls_updated"],
                        "duplicates_removed_after_url_check": processing_info["duplicates_removed"],
                        "final_company_count": processing_info["final_count"]
                    }
                    
                    # Сохраняем старое поле deduplication_info для обратной совместимости, если оно ожидается где-то
                    # но делаем его более простым, основываясь на общем количестве удаленных строк
                    total_removed_for_simple_dedup = processing_info["dead_urls_removed"] + processing_info["duplicates_removed"]
                    meta["deduplication_info"] = {
                         "original_count": processing_info["original_count"],
                         "duplicates_removed": total_removed_for_simple_dedup, # Общее количество "потерянных" строк
                         "final_count": processing_info["final_count"]
                    }

                    all_metadata[meta_idx] = meta
                    save_session_metadata(all_metadata)
                    logger.info(f"Метаданные сессии {session_id_for_metadata} обновлены.")
                    session_found_and_updated = True
                    break
            if not session_found_and_updated:
                logger.warning(f"Сессия {session_id_for_metadata} не найдена в метаданных. Метаданные не обновлены.")
        except ImportError:
             logger.error("Не удалось импортировать data_io для обновления метаданных сессии.")
        except Exception as e:
            logger.error(f"Ошибка при обновлении метаданных сессии {session_id_for_metadata}: {e}")
            # Добавляем эту ошибку в processing_info, чтобы она могла быть возвращена
            processing_info["processing_messages"].append({"type": "error", "message": f"Ошибка обновления метаданных сессии: {e}", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})


    # Удаляем больше не нужные функции, так как их логика теперь встроена
    # normalize_urls_in_file и remove_duplicates_by_domain
    # Оставляем их, если они используются где-то еще или для CLI.
    # Для чистоты кода их можно было бы удалить или сделать приватными, если они больше не нужны извне.

    return output_file, processing_info
    
# def normalize_and_remove_duplicates(input_file: str, output_file: str = None) -> tuple[str, dict]:
#     """
#     Нормализует URL и удаляет дубликаты по доменам в одной операции.
    
#     Args:
#         input_file: Путь к входному файлу (CSV или Excel)
#         output_file: Путь для сохранения результата (если не указан, перезаписывает входной файл)
        
#     Returns:
#         tuple: (путь к файлу без дубликатов, словарь с информацией о дедупликации)
#     """
#     try:
#         # Шаг 1: Нормализация URL
#         normalized_file = normalize_urls_in_file(input_file, output_file)
        
#         # Шаг 2: Удаление дубликатов
#         result_file, deduplication_info = remove_duplicates_by_domain(normalized_file)
        
#         # Логируем детальную информацию о дедупликации
#         logger.info(f"normalize_and_remove_duplicates результат: файл={result_file}, удалено дубликатов={deduplication_info['duplicates_removed']}")
        
#         # Обновляем метаданные сессии, если файл находится в каталоге сессии
#         try:
#             from src.data_io import load_session_metadata, save_session_metadata
            
#             # Проверяем, содержит ли путь к файлу слово 'sessions'
#             file_path = Path(result_file)
#             if 'sessions' in str(file_path):
#                 # Предполагаем, что ID сессии - это имя родительской директории
#                 session_id = file_path.parent.name
                
#                 # Загружаем метаданные
#                 all_metadata = load_session_metadata()
#                 session_found_and_updated = False # Флаг для проверки
#                 for meta_idx, meta in enumerate(all_metadata):
#                     if meta.get("session_id") == session_id:
#                         logger.info(f"Found session {session_id} in metadata. Updating...")
#                         # Обновляем количество компаний в метаданных
#                         meta["original_companies_count"] = deduplication_info["original_count"]
#                         meta["companies_count"] = deduplication_info["final_count"]
#                         meta["total_companies"] = deduplication_info["final_count"]
                        
#                         # Добавляем информацию о дедупликации
#                         meta["deduplication_info"] = deduplication_info
                        
#                         # Добавляем сообщение о дедупликации
#                         if "processing_messages" not in meta:
#                             meta["processing_messages"] = []
                        
#                         import time
#                         dedup_message_text = f"Removed {deduplication_info['duplicates_removed']} duplicates."
                        
#                         # Проверяем, есть ли уже такое сообщение
#                         message_exists = any(
#                             msg.get("type") == "deduplication" and msg.get("message") == dedup_message_text 
#                             for msg in meta["processing_messages"]
#                         )
                        
#                         if not message_exists:
#                             meta["processing_messages"].append({
#                                 "type": "deduplication",
#                                 "message": dedup_message_text,
#                                 "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
#                             })
                        
#                         logger.info(f"Values for session {session_id} before save: total_companies={meta.get('total_companies')}, deduplication_info={meta.get('deduplication_info')}")
#                         # Обновляем элемент в списке all_metadata напрямую по индексу, чтобы быть уверенным
#                         all_metadata[meta_idx] = meta 
#                         save_session_metadata(all_metadata)
#                         logger.info(f"Обновлены метаданные сессии {session_id} с информацией о дедупликации")
#                         session_found_and_updated = True
#                         break
#                 if not session_found_and_updated:
#                     logger.warning(f"Session {session_id} not found in metadata during deduplication update step. Metadata not updated with dedup info.")
#         except Exception as e:
#             logger.error(f"Ошибка при обновлении метаданных сессии: {e}")
        
#         return result_file, deduplication_info
    
#     except Exception as e:
#         logger.error(f"Ошибка в процессе нормализации и удаления дубликатов: {e}")
#         raise

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
            logger.info("ScrapingBee клиент инициализирован для CLI.")
        except Exception as e_sb_init:
            logger.error(f"Не удалось инициализировать ScrapingBee клиент: {e_sb_init}")

    loop = asyncio.get_event_loop()
    try:
        result_file, processing_details = loop.run_until_complete(
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
            logger.error(f"Обработка завершилась с ошибкой. Детали: {processing_details.get('error')}")
        
        logger.info("Детали обработки:")
        for key, value in processing_details.items():
            if key == "processing_messages":
                logger.info("  Сообщения:")
                for msg_data in value:
                    logger.info(f"    - [{msg_data.get('type', 'N/A')}] {msg_data.get('timestamp', '')}: {msg_data.get('message', 'Нет сообщения')}")
            else:
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