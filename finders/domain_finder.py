from .base import Finder
import aiohttp
import re
import socket

class DomainFinder(Finder):
    async def find(self, company_name: str, **context) -> dict:
        """
        Проверяет наличие доступного домена для компании, проходя по разным TLD.
        
        Args:
            company_name: Название компании
            context: Словарь с контекстом, должен содержать 'session' с aiohttp.ClientSession
            
        Returns:
            dict: Результат поиска {"source": "domains", "result": url или None}
        """
        session = context.get('session')
        if not session:
            raise ValueError("DomainFinder требует aiohttp.ClientSession в context['session']")
            
        url = await self._find_domain_by_tld(company_name, session)
        return {"source": "domains", "result": url}
        
    async def _find_domain_by_tld(self, company_name: str, session: aiohttp.ClientSession) -> str | None:
        """
        Пытается найти домен компании, проверяя популярные TLD.
        
        Args:
            company_name: Название компании
            session: aiohttp.ClientSession для HTTP-запросов
            
        Returns:
            str | None: URL компании или None, если не найден
        """
        # Популярные TLD в порядке приоритета
        common_tlds = [
            "com", "ru", "ua", "cz", "ch", "org", "io", "net", "co", "ai", "app", "dev", "tech", "digital",
            "cloud", "online", "site", "website", "info", "biz", "me", "tv", "studio",
            "agency", "group", "team", "solutions", "services", "systems", "technology"
        ]
        
        # Очищаем название компании
        clean_name = self._normalize_name_for_domain_comparison(company_name)
        
        # Пробуем каждый TLD
        for tld in common_tlds:
            domain = f"{clean_name}.{tld}"
            if await self._check_domain_availability(domain, session):
                return f"https://{domain}"
        
        return None
        
    def _normalize_name_for_domain_comparison(self, name: str) -> str:
        """
        Очищает название компании для сравнения с доменом.
        
        Args:
            name: Название компании
            
        Returns:
            str: Очищенное название
        """
        # Удаляем всё в скобках
        name = re.sub(r'\s*\([^)]*\)', '', name)
        name = name.lower()
        common_suffixes = [
            ', inc.', ' inc.', ', llc', ' llc', ', ltd.', ' ltd.', ' ltd', ', gmbh', ' gmbh',
            ', s.a.', ' s.a.', ' plc', ' se', ' ag', ' oyj', ' ab', ' as', ' nv', ' bv', ' co.', ' co'
            ' corporation', ' company', ' group', ' holding', ' solutions', ' services',
            ' technologies', ' systems', ' international'
        ]
        for suffix in common_suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        name = re.sub(r'[^\w-]', '', name)
        return name.strip('-')
        
    async def _check_domain_availability(self, domain: str, session: aiohttp.ClientSession, timeout: float = 2.0) -> bool:
        """
        Проверяет доступность домена и возвращает валидный HTTP ответ.
        
        Args:
            domain: Домен для проверки
            session: aiohttp.ClientSession для HTTP-запросов
            timeout: Таймаут запроса в секундах
            
        Returns:
            bool: True, если домен доступен
        """
        try:
            # Сначала пробуем разрешить DNS
            try:
                socket.gethostbyname(domain)
            except socket.gaierror:
                return False

            # Пробуем HTTPS сначала
            try:
                async with session.head(f"https://{domain}", timeout=timeout, allow_redirects=True) as response:
                    if 200 <= response.status < 400:
                        return True
            except:
                pass

            # Если HTTPS не сработал, пробуем HTTP
            try:
                async with session.head(f"http://{domain}", timeout=timeout, allow_redirects=True) as response:
                    if 200 <= response.status < 400:
                        return True
            except:
                pass

            return False
        except Exception:
            return False 