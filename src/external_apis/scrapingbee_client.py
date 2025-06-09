import asyncio
import logging
from typing import Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

class CustomScrapingBeeClient:
    BASE_URL = "https://app.scrapingbee.com/api/v1/"

    def __init__(self, api_key: str, timeout_seconds: int = 60):
        if not api_key:
            raise ValueError("ScrapingBee API key is required.")
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def fetch_website_data_via_sb_async(
        self,
        url: str,
        render_js: bool = True,
        premium_proxy: bool = False,
        country_code: Optional[str] = None,
        return_text: bool = False, # Если True, вернет только HTML контент
        timeout_source: bool = False # Если True, вернет таймаут как ошибку
    ) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """
        Асинхронно получает данные с веб-сайта с использованием ScrapingBee.

        Args:
            url: URL для скрапинга.
            render_js: Включить ли рендеринг JavaScript (по умолчанию True).
            premium_proxy: Использовать ли премиум прокси (по умолчанию False).
            country_code: Код страны для прокси (например, 'us').
            return_text: Если True, первый элемент кортежа будет HTML, иначе None.
            timeout_source: Если True, вернет ошибку таймаута.

        Returns:
            Кортеж (html_content, status_code, final_url_or_error_message):
            - html_content: HTML-содержимое страницы или None, если return_text=False или ошибка.
            - status_code: HTTP статус код ответа или None при ошибке.
            - final_url_or_error_message: Финальный URL после редиректов, или сообщение об ошибке.
        """
        session = await self._get_session()
        
        # Несколько попыток с разными параметрами для обхода блокировок
        attempts = [
            {
                "render_js": render_js,
                "premium_proxy": premium_proxy,
                "forward_headers": True,
                "block_resources": False,
                "country_code": country_code
            },
            {
                "render_js": False,  # Без JS для экономии
                "premium_proxy": True,  # Премиум прокси
                "forward_headers": True,
                "block_resources": True,  # Блокируем картинки/CSS
                "country_code": "us"
            },
            {
                "render_js": True,
                "premium_proxy": True,
                "forward_headers": False,  # Без пересылки заголовков
                "block_resources": True,
                "country_code": "gb"
            }
        ]
        
        last_error = None
        
        for attempt_num, attempt_params in enumerate(attempts, 1):
            params = {
                "api_key": self.api_key,
                "url": url,
                "render_js": str(attempt_params["render_js"]).lower(),
                "premium_proxy": str(attempt_params["premium_proxy"]).lower(),
                "forward_headers": str(attempt_params["forward_headers"]).lower(),
            }
            
            if attempt_params.get("block_resources"):
                params["block_resources"] = "true"
            if attempt_params.get("country_code"):
                params["country_code"] = attempt_params["country_code"]
            if timeout_source:
                params["timeout_source"] = "true"

            try:
                logger.info(f"[ScrapingBee] Попытка {attempt_num}/3 для {url} с параметрами: {attempt_params}")
                async with session.get(self.BASE_URL, params=params) as response:
                    response_text = await response.text()

                    # Проверка на лимит одновременных запросов
                    if response.status == 403 and "Looks like you\'ve hit the concurrency limit" in response_text:
                        logger.warning(f"[ScrapingBee] Достигнут лимит одновременных запросов для URL: {url}")
                        # Адекватная задержка для лимита одновременных запросов (ScrapingBee требует времени)
                        if attempt_num < len(attempts):
                            await asyncio.sleep(1.5)  # Компромисс: короче чем 2с, но достаточно для ScrapingBee
                            continue
                        return None, response.status, "ScrapingBee concurrency limit reached"
                    
                    # Проверка на невалидный URL
                    if response.status == 422 and "Url is not valid" in response_text:
                        logger.warning(f"[ScrapingBee] URL '{url}' не валиден для ScrapingBee. Ответ: {response_text[:200]}")
                        return None, response.status, f"ScrapingBee: Invalid URL - {response_text[:100]}"

                    # Проверка на таймаут
                    if response.headers.get("X-ScrapingBee-Error") == "TIMEOUT" or "render timed out" in response_text.lower():
                        logger.warning(f"[ScrapingBee] Таймаут при обработке URL: {url}")
                        if attempt_num < len(attempts):
                            continue  # Пробуем следующую конфигурацию
                        return None, 408, "ScrapingBee render timed out"

                    final_url = response.headers.get("X-ScrapingBee-Final-Url", url)

                    if response.ok:  # Статусы 2xx
                        logger.info(f"[ScrapingBee] Успешный запрос к {url}, статус {response.status}, финальный URL: {final_url}")
                        html_content = response_text if return_text else None
                        return html_content, response.status, final_url
                    elif response.status in [403, 429]:  # Блокировка ботов
                        logger.info(f"[ScrapingBee] Сайт {url} блокирует ботов (статус {response.status}), но сайт вероятно живой")
                        # Возвращаем как успешный результат, так как это означает что сайт работает
                        return None, response.status, final_url
                    elif response.status == 500:
                        logger.warning(f"[ScrapingBee] Внутренняя ошибка сервера для {url}: {response_text[:200]}")
                        if attempt_num < len(attempts):
                            continue  # Пробуем следующую конфигурацию
                        last_error = f"ScrapingBee Error: Status {response.status} - {response_text[:100]}"
                    else:
                        logger.warning(f"[ScrapingBee] Ошибка при запросе к {url}: статус {response.status}, ответ: {response_text[:200]}")
                        if attempt_num < len(attempts):
                            continue  # Пробуем следующую конфигурацию
                        last_error = f"ScrapingBee Error: Status {response.status} - {response_text[:100]}"

            except aiohttp.ClientConnectorError as e:
                logger.error(f"[ScrapingBee] Ошибка соединения для {url}: {e}")
                last_error = f"ScrapingBee Connection Error: {str(e)}"
                if attempt_num < len(attempts):
                    await asyncio.sleep(0.2)  # Сокращена с 1 до 0.2 секунд
                    continue
            except asyncio.TimeoutError:
                logger.error(f"[ScrapingBee] Таймаут запроса к {url}")
                last_error = f"ScrapingBee Request Timeout"
                if attempt_num < len(attempts):
                    continue
            except Exception as e:
                logger.error(f"[ScrapingBee] Неожиданная ошибка для {url}: {e}", exc_info=True)
                last_error = f"ScrapingBee Unexpected Error: {str(e)}"
                if attempt_num < len(attempts):
                    continue
        
        # Если все попытки не удались
        return None, None, last_error or "All ScrapingBee attempts failed"

    async def close_async(self):
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("ScrapingBee aiohttp session closed.")
        self._session = None 