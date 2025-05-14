import re
import socket
import aiohttp
import logging
import sys
import os
import asyncio
from urllib.parse import urlparse

# Добавляем корневую директорию проекта в путь Python
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from finders.base import Finder

logger = logging.getLogger(__name__)

def normalize_name_for_domain_comparison(name: str) -> str:
    """
    Очищает название компании для сравнения с доменом.
    """
    name = re.sub(r'\s*\([^)]*\)', '', name)
    name = name.lower()
    common_suffixes = [
        ', inc.', ' inc.', ', llc', ' llc', ', ltd.', ' ltd.', ' ltd', ', gmbh', ' gmbh',
        ', s.a.', ' s.a.', ' plc', ' se', ' ag', ' oyj', ' ab', ' as', ' nv', ' bv', ' co.', ' co',
        ' corporation', ' company', ' group', ' holding', ' solutions', ' services',
        ' technologies', ' systems', ' international'
    ]
    for suffix in common_suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = re.sub(r'[^\w-]', '', name) # Оставляем только буквы, цифры, подчеркивания и дефисы
    name = name.replace('_', '-') # Заменяем подчеркивания на дефисы для доменных имен
    name = re.sub(r'-+', '-', name) # Удаляем множественные дефисы
    return name.strip('-')

async def check_url_liveness(url: str, session: aiohttp.ClientSession, timeout: float = 5.0) -> bool:
    """
    Проверяет "жизнеспособность" полного URL.
    Сначала пытается разрешить DNS для хоста, затем делает HEAD-запрос.
    Возвращает True, если URL считается рабочим, False в противном случае.
    """
    if not url or not url.startswith(("http://", "https://")):
        logger.debug(f"Invalid URL format for liveness check: {url}")
        return False
    
    try:
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname

        if not hostname:
            logger.debug(f"Could not parse hostname from URL: {url}")
            return False

        logger.debug(f"Checking DNS for host: {hostname} (from URL: {url})")
        try:
            await asyncio.get_event_loop().getaddrinfo(hostname, None)
            logger.debug(f"DNS resolved for {hostname}")
        except socket.gaierror:
            logger.warning(f"DNS resolution failed for {hostname} (from URL: {url}). Marking URL as not live.")
            return False 
        except Exception as e_dns:
            logger.warning(f"Unexpected DNS error for {hostname} (from URL: {url}): {type(e_dns).__name__} - {e_dns}. Marking URL as not live.")
            return False

        try:
            logger.debug(f"Attempting HEAD request to {url}")
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with session.head(url, timeout=client_timeout, allow_redirects=True) as response:
                logger.debug(f"HEAD request to {url} status: {response.status}")
                if 200 <= response.status < 400:
                    return True
                elif response.status == 404 or response.status >= 500:
                    logger.warning(f"URL {url} returned status {response.status}. Marking as not live.")
                    return False
                # Для других клиентских или серверных ошибок (кроме 404 и 5xx) 
                # ранее мы считали их True, но с глобальным отключением SSL это может быть не нужно.
                # Безопаснее считать их False, если это не явный успех (2xx, 3xx).
                logger.warning(f"URL {url} returned non-success/non-fatal status {response.status}. Marking as not live for safety.")
                return False # <--- Изменено на False для большей строгости
        except asyncio.TimeoutError:
            logger.warning(f"HEAD request to {url} timed out after {timeout}s. Marking as not live.")
            return False
        except aiohttp.ClientError as e_client: 
            # Поскольку SSL ошибки теперь должны игнорироваться на уровне сессии, 
            # эта ошибка будет поймана только если SSL отключение не сработало или это другая ClientError.
            logger.warning(f"Aiohttp client error during HEAD request to {url}: {type(e_client).__name__} - {e_client}. Marking as not live.")
            return False
        except Exception as e_head: 
            logger.warning(f"Unexpected error during HEAD request to {url}: {type(e_head).__name__} - {e_head}. Marking as potentially not live.")
            return False

    except Exception as e_main:
        logger.error(f"Error in check_url_liveness for {url}: {e_main}", exc_info=True)
        return False

async def check_domain_availability(domain: str, session: aiohttp.ClientSession, timeout: float = 2.0) -> bool:
    """
    Проверяет доступность домена и возвращает валидный HTTP ответ.
    """
    try:
        logger.debug(f"Checking DNS for domain: {domain}")
        try:
            # Используем asyncio.get_event_loop().getaddrinfo для асинхронного разрешения DNS
            # Вместо синхронного socket.gethostbyname, который может блокировать event loop
            await asyncio.get_event_loop().getaddrinfo(domain, None)
            logger.debug(f"DNS resolved for {domain}")
        except socket.gaierror:
            logger.debug(f"DNS resolution failed for {domain}")
            return False

        protocols_to_check = ["https", "http"]
        for protocol in protocols_to_check:
            url_to_check = f"{protocol}://{domain}"
            try:
                logger.debug(f"Attempting HEAD request to {url_to_check}")
                async with session.head(url_to_check, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=True) as response:
                    logger.debug(f"HEAD request to {url_to_check} status: {response.status}")
                    if 200 <= response.status < 400: # Успешный статус или редирект
                        return True
            except asyncio.TimeoutError:
                logger.debug(f"HEAD request to {url_to_check} timed out after {timeout}s.")
            except aiohttp.ClientError as e:
                # Логируем конкретные ошибки клиента, если они не связаны с недоступностью сервера
                # Например, ClientSSLError, ClientConnectorError (кроме ConnectionRefused)
                if not isinstance(e, (aiohttp.ClientConnectionError, aiohttp.ServerDisconnectedError)):
                     logger.warning(f"Aiohttp client error for {url_to_check}: {type(e).__name__} - {e}")
                else:
                    logger.debug(f"Aiohttp connection error for {url_to_check}: {type(e).__name__}")
            except Exception as e_head: # Другие общие исключения
                logger.warning(f"Unexpected error during HEAD request to {url_to_check}: {type(e_head).__name__} - {e_head}")
        return False
    except Exception as e_main:
        logger.error(f"Error in check_domain_availability for {domain}: {e_main}", exc_info=True)
        return False

async def find_potential_domain(company_name: str, session: aiohttp.ClientSession, tlds: list = None) -> str | None:
    """
    Пытается найти домен компании, проверяя заданные или популярные TLD.
    """
    if tlds is None:
        tlds = [
            "com", "ru", "ua", "cz", "ch", "org", "io", "net", "co", "ai", "app", "dev", "tech", "digital",
            "cloud", "online", "site", "website", "info", "biz", "me", "tv", "studio",
            "agency", "group", "team", "solutions", "services", "systems", "technology"
        ]
    
    clean_name = normalize_name_for_domain_comparison(company_name)
    if not clean_name:
        logger.debug(f"Could not generate a clean name for domain check from '{company_name}'")
        return None

    logger.debug(f"Normalized name for domain check: '{clean_name}' (from '{company_name}')")
    
    for tld in tlds:
        domain = f"{clean_name}.{tld}"
        logger.debug(f"Checking domain: {domain} for company '{company_name}'")
        if await check_domain_availability(domain, session):
            logger.info(f"Domain {domain} is available for company '{company_name}'. Returning https://{domain}")
            return f"https://{domain}"
    logger.info(f"No available domain found for '{company_name}' after checking TLDs.")
    return None

class DomainCheckFinder(Finder):
    """
    Финдер, который пытается найти домен компании путем перебора популярных TLD
    и проверки их доступности.
    """
    def __init__(self, custom_tlds: list = None, verbose: bool = False):
        self.custom_tlds = custom_tlds # Пользовательский список TLD, если нужен
        self.verbose = verbose # verbose пока не используется напрямую в этом классе, но может быть в будущем
        logger.debug("DomainCheckFinder initialized.")

    async def find(self, company_name: str, **context) -> dict:
        session = context.get('session')
        if not session:
            logger.error(f"{self.__class__.__name__}: aiohttp.ClientSession not found in context['session']")
            return {
                "source": "domain_check_finder", 
                "result": None, 
                "error": f"{self.__class__.__name__} requires aiohttp.ClientSession in context['session']",
                "source_class": self.__class__.__name__
            }
        
        logger.info(f"DomainCheckFinder: Starting domain check for '{company_name}'")
        # Передаем self.custom_tlds в find_potential_domain
        # Если self.custom_tlds is None, find_potential_domain использует свой список по умолчанию
        domain_url = await find_potential_domain(company_name, session, tlds=self.custom_tlds)
        
        if domain_url:
            logger.info(f"DomainCheckFinder: Found domain '{domain_url}' for '{company_name}'")
            return {
                "source": "domain_check_finder", 
                "result": domain_url, 
                "error": None,
                "source_class": self.__class__.__name__
            }
        else:
            logger.info(f"DomainCheckFinder: No domain found for '{company_name}'")
            return {
                "source": "domain_check_finder", 
                "result": None, 
                "error": f"No domain found for {company_name} via TLD check.",
                "source_class": self.__class__.__name__
            } 