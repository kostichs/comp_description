"""
Модуль для сохранения поисковых данных в markdown файлы
Сохраняет все данные Serper и ScrapingBee для каждой компании в отдельный markdown файл
"""

import os
import json
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from src.utils.config import OUTPUT_DIR
from src.utils.logging import log_info, log_error, log_debug


class SearchDataSaver:
    """Класс для сохранения поисковых данных в markdown файлы"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.search_data_dir = os.path.join(OUTPUT_DIR, session_id, "search_data")
        os.makedirs(self.search_data_dir, exist_ok=True)
        
        # Словарь для накопления данных по компаниям
        self.company_search_data = {}
    
    def add_serper_data(self, company_name: str, query: str, serper_results: Dict[str, Any]):
        """
        Добавляет результаты Serper поиска для компании
        
        Args:
            company_name: Название компании
            query: Поисковый запрос
            serper_results: Результаты поиска от Serper API
        """
        if not company_name or not serper_results:
            return
        
        # Инициализируем данные компании если их нет
        if company_name not in self.company_search_data:
            self.company_search_data[company_name] = {
                "company_name": company_name,
                "serper_searches": [],
                "scraped_pages": [],
                "timestamp": datetime.now().isoformat()
            }
        
        # Добавляем данные Serper поиска
        serper_entry = {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "results_count": len(serper_results.get("organic", [])),
            "organic_results": serper_results.get("organic", []),
            "knowledge_graph": serper_results.get("knowledgeGraph", {}),
            "answer_box": serper_results.get("answerBox", {}),
            "people_also_ask": serper_results.get("peopleAlsoAsk", []),
            "related_searches": serper_results.get("relatedSearches", [])
        }
        
        self.company_search_data[company_name]["serper_searches"].append(serper_entry)
        log_debug(f"📊 Added Serper data for {company_name}: query='{query}', results={serper_entry['results_count']}")
    
    def add_scrapingbee_data(self, company_name: str, url: str, scraped_content: str, 
                           serper_query: str = "", status_code: int = 200, error: str = None):
        """
        Добавляет результаты ScrapingBee скрапинга для компании
        
        Args:
            company_name: Название компании
            url: URL страницы
            scraped_content: Скрапленный контент
            serper_query: Исходный поисковый запрос
            status_code: HTTP статус код
            error: Ошибка если есть
        """
        if not company_name:
            return
        
        # Инициализируем данные компании если их нет
        if company_name not in self.company_search_data:
            self.company_search_data[company_name] = {
                "company_name": company_name,
                "serper_searches": [],
                "scraped_pages": [],
                "timestamp": datetime.now().isoformat()
            }
        
        # Добавляем данные скрапинга
        scraped_entry = {
            "url": url,
            "serper_query": serper_query,
            "timestamp": datetime.now().isoformat(),
            "status_code": status_code,
            "content_length": len(scraped_content) if scraped_content else 0,
            "content": scraped_content[:10000] if scraped_content else "",  # Первые 10K символов
            "content_preview": scraped_content[:500] if scraped_content else "",  # Превью 500 символов
            "error": error
        }
        
        self.company_search_data[company_name]["scraped_pages"].append(scraped_entry)
        log_debug(f"🐝 Added ScrapingBee data for {company_name}: url='{url}', content_length={scraped_entry['content_length']}")
    
    def save_company_markdown(self, company_name: str) -> Optional[str]:
        """
        Сохраняет все поисковые данные компании в markdown файл
        
        Args:
            company_name: Название компании
            
        Returns:
            str: Путь к сохраненному файлу или None если ошибка
        """
        if company_name not in self.company_search_data:
            log_debug(f"No search data found for company: {company_name}")
            return None
        
        try:
            # Создаем безопасное имя файла
            safe_company_name = re.sub(r'[^a-zA-Z0-9_-]', '_', company_name)
            filename = f"{safe_company_name}_search_data.md"
            filepath = os.path.join(self.search_data_dir, filename)
            
            # Генерируем markdown контент
            markdown_content = self._generate_markdown_content(self.company_search_data[company_name])
            
            # Сохраняем файл
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            log_info(f"💾 Saved search data for {company_name} to {filepath}")
            return filepath
            
        except Exception as e:
            log_error(f"❌ Error saving search data for {company_name}: {e}")
            return None
    
    def save_all_companies_markdown(self) -> List[str]:
        """
        Сохраняет поисковые данные всех компаний в markdown файлы
        
        Returns:
            List[str]: Список путей к сохраненным файлам
        """
        saved_files = []
        
        for company_name in self.company_search_data.keys():
            filepath = self.save_company_markdown(company_name)
            if filepath:
                saved_files.append(filepath)
        
        log_info(f"💾 Saved search data for {len(saved_files)} companies to markdown files")
        return saved_files
    
    def _generate_markdown_content(self, company_data: Dict[str, Any]) -> str:
        """
        Генерирует markdown контент для компании
        
        Args:
            company_data: Данные компании
            
        Returns:
            str: Markdown контент
        """
        company_name = company_data["company_name"]
        timestamp = company_data["timestamp"]
        serper_searches = company_data.get("serper_searches", [])
        scraped_pages = company_data.get("scraped_pages", [])
        
        # Начинаем с заголовка
        content = [f"# Search Data Report for {company_name}"]
        content.append(f"**Generated:** {timestamp}")
        content.append(f"**Session ID:** {self.session_id}")
        content.append("")
        
        # Добавляем сводку
        content.append("## Summary")
        content.append(f"* **Total Serper Searches:** {len(serper_searches)}")
        content.append(f"* **Total Scraped Pages:** {len(scraped_pages)}")
        content.append("")
        
        # Добавляем данные Serper поисков
        if serper_searches:
            content.append("## Serper Search Results")
            content.append("")
            
            for i, search in enumerate(serper_searches, 1):
                content.append(f"### Search {i}: {search['query']}")
                content.append(f"**Timestamp:** {search['timestamp']}")
                content.append(f"**Results Found:** {search['results_count']}")
                content.append("")
                
                # Organic results
                if search.get("organic_results"):
                    content.append("#### Organic Search Results")
                    for j, result in enumerate(search["organic_results"][:10], 1):  # Первые 10 результатов
                        title = result.get("title", "No title")
                        link = result.get("link", "No link")
                        snippet = result.get("snippet", "No snippet")
                        
                        content.append(f"**{j}. {title}**")
                        content.append(f"* **URL:** {link}")
                        content.append(f"* **Snippet:** {snippet}")
                        content.append("")
                
                # Knowledge Graph
                if search.get("knowledge_graph"):
                    kg = search["knowledge_graph"]
                    content.append("#### Knowledge Graph")
                    if kg.get("title"):
                        content.append(f"* **Title:** {kg['title']}")
                    if kg.get("type"):
                        content.append(f"* **Type:** {kg['type']}")
                    if kg.get("description"):
                        content.append(f"* **Description:** {kg['description']}")
                    if kg.get("website"):
                        content.append(f"* **Website:** {kg['website']}")
                    content.append("")
                
                # Answer Box
                if search.get("answer_box"):
                    ab = search["answer_box"]
                    content.append("#### Answer Box")
                    if ab.get("answer"):
                        content.append(f"* **Answer:** {ab['answer']}")
                    if ab.get("title"):
                        content.append(f"* **Title:** {ab['title']}")
                    if ab.get("link"):
                        content.append(f"* **Source:** {ab['link']}")
                    content.append("")
                
                # People Also Ask
                if search.get("people_also_ask"):
                    content.append("#### People Also Ask")
                    for paa in search["people_also_ask"][:5]:  # Первые 5 вопросов
                        if paa.get("question"):
                            content.append(f"* {paa['question']}")
                    content.append("")
                
                # Related Searches
                if search.get("related_searches"):
                    content.append("#### Related Searches")
                    for rs in search["related_searches"][:5]:  # Первые 5 связанных поисков
                        if rs.get("query"):
                            content.append(f"* {rs['query']}")
                    content.append("")
                
                content.append("---")
                content.append("")
        
        # Добавляем данные скрапинга
        if scraped_pages:
            content.append("## Scraped Pages Content")
            content.append("")
            
            for i, page in enumerate(scraped_pages, 1):
                content.append(f"### Scraped Page {i}")
                content.append(f"**URL:** {page['url']}")
                content.append(f"**Timestamp:** {page['timestamp']}")
                content.append(f"**Status Code:** {page['status_code']}")
                content.append(f"**Content Length:** {page['content_length']} characters")
                
                if page.get("serper_query"):
                    content.append(f"**Related Search Query:** {page['serper_query']}")
                
                if page.get("error"):
                    content.append(f"**Error:** {page['error']}")
                
                content.append("")
                
                # Добавляем превью контента
                if page.get("content_preview"):
                    content.append("#### Content Preview (first 500 characters)")
                    content.append("```")
                    content.append(page["content_preview"])
                    content.append("```")
                    content.append("")
                
                # Добавляем полный контент (первые 10K символов)
                if page.get("content") and len(page["content"]) > 500:
                    content.append("#### Full Content (first 10,000 characters)")
                    content.append("```")
                    content.append(page["content"])
                    content.append("```")
                    content.append("")
                
                content.append("---")
                content.append("")
        
        # Добавляем footer
        content.append("---")
        content.append(f"*Report generated by Criteria Processor - Session {self.session_id}*")
        content.append(f"*Generated at: {datetime.now().isoformat()}*")
        
        return "\n".join(content)


# Глобальный экземпляр для текущей сессии
_current_saver: Optional[SearchDataSaver] = None


def initialize_search_data_saver(session_id: str) -> SearchDataSaver:
    """
    Инициализирует глобальный экземпляр SearchDataSaver для сессии
    
    Args:
        session_id: ID сессии
        
    Returns:
        SearchDataSaver: Экземпляр сохранителя
    """
    global _current_saver
    _current_saver = SearchDataSaver(session_id)
    log_info(f"🔧 Initialized SearchDataSaver for session: {session_id}")
    return _current_saver


def get_current_search_data_saver() -> Optional[SearchDataSaver]:
    """
    Возвращает текущий экземпляр SearchDataSaver
    
    Returns:
        SearchDataSaver или None если не инициализирован
    """
    return _current_saver


def save_serper_search_data(company_name: str, query: str, serper_results: Dict[str, Any]):
    """
    Сохраняет данные Serper поиска через глобальный сохранитель
    
    Args:
        company_name: Название компании
        query: Поисковый запрос
        serper_results: Результаты поиска
    """
    if _current_saver:
        _current_saver.add_serper_data(company_name, query, serper_results)


def save_scrapingbee_data(company_name: str, url: str, scraped_content: str, 
                         serper_query: str = "", status_code: int = 200, error: str = None):
    """
    Сохраняет данные ScrapingBee через глобальный сохранитель
    
    Args:
        company_name: Название компании
        url: URL страницы
        scraped_content: Скрапленный контент
        serper_query: Исходный поисковый запрос
        status_code: HTTP статус код
        error: Ошибка если есть
    """
    if _current_saver:
        _current_saver.add_scrapingbee_data(company_name, url, scraped_content, serper_query, status_code, error)


def finalize_search_data_saving() -> List[str]:
    """
    Завершает сохранение данных - сохраняет все markdown файлы
    
    Returns:
        List[str]: Список путей к сохраненным файлам
    """
    if _current_saver:
        saved_files = _current_saver.save_all_companies_markdown()
        log_info(f"🎉 Finalized search data saving: {len(saved_files)} files saved")
        return saved_files
    return [] 