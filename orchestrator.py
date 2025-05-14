import asyncio
import aiohttp
from typing import List, Dict, Any
from finders import Finder

class PipelineOrchestrator:
    def __init__(self, finders: List[Finder]):
        """
        Инициализирует оркестратор с набором финдеров.
        
        Args:
            finders: Список финдеров для поиска информации
        """
        self.finders = finders
        
    async def process(self, company_name: str, session: aiohttp.ClientSession, **additional_context) -> Dict[str, Any]:
        """
        Обрабатывает компанию, запуская каждый finder последовательно.
        
        Args:
            company_name: Название компании
            session: aiohttp.ClientSession для HTTP-запросов
            additional_context: Дополнительный контекст для финдеров
            
        Returns:
            dict: Результат поиска с информацией об источнике
        """
        # Инициализация контекста
        context = {"session": session, **additional_context}
        
        # Запускаем все финдеры и собираем результаты
        results = []
        for finder in self.finders:
            try:
                # Запускаем финдер
                result = await finder.find(company_name, **context)
                results.append(result)
                
                # Если источник нашел результат, обновляем контекст
                # для передачи в следующие финдеры
                if result["result"]:
                    context.update(result)
            except Exception as e:
                # Логируем ошибку и продолжаем с следующим финдером
                print(f"Ошибка в {finder.__class__.__name__} для {company_name}: {e}")
                results.append({"source": finder.__class__.__name__, "result": None, "error": str(e)})
                
        # Формируем итоговый результат
        return {
            "company": company_name,
            "results": results,
            "successful": any(r.get("result") is not None for r in results)
        }
        
    async def process_batch(self, company_names: List[str], session: aiohttp.ClientSession, **additional_context) -> List[Dict[str, Any]]:
        """
        Обрабатывает пакет компаний параллельно.
        
        Args:
            company_names: Список названий компаний
            session: aiohttp.ClientSession для HTTP-запросов
            additional_context: Дополнительный контекст для финдеров
            
        Returns:
            list: Список результатов поиска для каждой компании
        """
        # Создаем задачи для каждой компании
        tasks = [self.process(name, session, **additional_context) for name in company_names]
        
        # Запускаем все задачи параллельно и ждем результатов
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем возможные исключения
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Если произошла ошибка, создаем запись с информацией об ошибке
                processed_results.append({
                    "company": company_names[i],
                    "results": [],
                    "successful": False,
                    "error": str(result)
                })
            else:
                processed_results.append(result)
                
        return processed_results 