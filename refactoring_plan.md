# План рефакторинга сервиса поиска информации о компаниях

## Цель
Создать модульную, расширяемую архитектуру для поиска информации о компаниях из различных источников, с возможностью использования найденных данных для генерации описаний.

## Архитектура

- [x] 1. Создать базовую абстракцию `Finder`
- [x] 2. Разработать конкретные реализации финдеров
- [x] 3. Создать оркестратор для управления процессом поиска
- [x] 4. Разработать механизм для обработки и сохранения результатов
- [x] 5. Имплементировать экстрактор данных для генерации описаний
- [x] 6. Обновить основной скрипт

## Пошаговая реализация

### 1. Базовая абстракция Finder

- [x] Создать файл `finders/base.py`:
```python
from abc import ABC, abstractmethod

class Finder(ABC):
    @abstractmethod
    async def find(self, company_name: str, **context) -> dict:
        """
        Находит информацию о компании и возвращает результат.
        
        Args:
            company_name: Название компании для поиска
            context: Дополнительный контекст (сессия, API-ключи и т.д.)
            
        Returns:
            dict: Словарь с информацией в формате 
                 {'source': 'название_источника', 'result': результат_или_None}
        """
        pass
```

### 2. Реализации конкретных финдеров

- [x] Создать файл `finders/wikidata_finder.py`:
```python
from .base import Finder
import requests

class WikidataFinder(Finder):
    async def find(self, company_name: str, **context) -> dict:
        url = self._get_wikidata_url(company_name)
        return {"source": "wikidata", "result": url}
        
    def _get_wikidata_url(self, company_name: str) -> str:
        # Перенести логику из get_wikidata_url
        # ...
```

- [x] Создать файл `finders/domain_finder.py`:
```python
from .base import Finder
import aiohttp

class DomainFinder(Finder):
    async def find(self, company_name: str, **context) -> dict:
        session = context.get('session')
        url = await self._find_domain_by_tld(company_name, session)
        return {"source": "domains", "result": url}
        
    async def _find_domain_by_tld(self, company_name: str, session: aiohttp.ClientSession) -> str:
        # Перенести логику из find_domain_by_tld
        # ...
```

- [x] Создать файл `finders/google_finder.py`:
```python
from .base import Finder
import aiohttp
import json

class GoogleFinder(Finder):
    def __init__(self, serper_api_key: str):
        self.api_key = serper_api_key
        
    async def find(self, company_name: str, **context) -> dict:
        session = context.get('session')
        result = await self._search_google(company_name, session)
        return {"source": "google", "result": result}
        
    async def _search_google(self, company_name: str, session: aiohttp.ClientSession) -> str:
        # Перенести логику поиска через Google Serper API
        # ...
```

- [x] Создать файл `finders/wikipedia_finder.py`:
```python
from .base import Finder
import aiohttp

class WikipediaFinder(Finder):
    async def find(self, company_name: str, **context) -> dict:
        wiki_url = context.get('wiki_url')
        if not wiki_url:
            return {"source": "wikipedia", "result": None}
            
        result = self._parse_wikipedia_website(wiki_url)
        return {"source": "wikipedia", "result": result}
        
    def _parse_wikipedia_website(self, wiki_url: str) -> str:
        # Перенести логику из parse_wikipedia_website
        # ...
```

- [x] Создать файл `finders/linkedin_finder.py`:
```python
from .base import Finder
import aiohttp

class LinkedInFinder(Finder):
    async def find(self, company_name: str, **context) -> dict:
        session = context.get('session')
        result = await self._search_linkedin(company_name, session)
        return {"source": "linkedin", "result": result}
        
    async def _search_linkedin(self, company_name: str, session: aiohttp.ClientSession) -> str:
        # Реализовать поиск компании в LinkedIn
        # ...
```

- [x] Создать файл `finders/llm_search_finder.py`:
```python
from .base import Finder
from openai import AsyncOpenAI

class LLMSearchFinder(Finder):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = AsyncOpenAI(api_key=api_key)
        
    async def find(self, company_name: str, **context) -> dict:
        result = await self._ask_llm_search_model(company_name)
        return {"source": "llm_search", "result": result}
        
    async def _ask_llm_search_model(self, company_name: str) -> dict:
        # Реализовать поиск с помощью LLM
        # ...
```

- [x] Создать файл `finders/__init__.py` для экспорта всех финдеров:
```python
from .base import Finder
from .wikidata_finder import WikidataFinder
from .domain_finder import DomainFinder
from .google_finder import GoogleFinder
from .wikipedia_finder import WikipediaFinder
from .linkedin_finder import LinkedInFinder
from .llm_search_finder import LLMSearchFinder

__all__ = [
    'Finder',
    'WikidataFinder',
    'DomainFinder',
    'GoogleFinder',
    'WikipediaFinder',
    'LinkedInFinder',
    'LLMSearchFinder'
]
```

### 3. Создание оркестратора

- [x] Создать файл `orchestrator.py`:
```python
import asyncio
import aiohttp
from typing import List, Dict, Any
from finders import Finder

class PipelineOrchestrator:
    def __init__(self, finders: List[Finder]):
        self.finders = finders
        
    async def process(self, company_name: str, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """
        Обрабатывает компанию, запуская каждый finder последовательно до первого успешного результата.
        
        Args:
            company_name: Название компании
            session: aiohttp.ClientSession для HTTP-запросов
            
        Returns:
            dict: Результат поиска с информацией об источнике
        """
        context = {"session": session}
        
        results = []
        for finder in self.finders:
            try:
                result = await finder.find(company_name, **context)
                results.append(result)
                # Если источник нашел результат, обновляем контекст
                if result["result"]:
                    context.update(result)
            except Exception as e:
                print(f"Ошибка в {finder.__class__.__name__}: {e}")
                
        return {
            "company": company_name,
            "results": results,
            "successful": any(r["result"] for r in results)
        }
```

### 4. Механизм для обработки и сохранения результатов

- [x] Создать файл `result_processor.py`:
```python
import json
import pandas as pd
from typing import List, Dict, Any

class ResultProcessor:
    @staticmethod
    def save_to_json(results: List[Dict[str, Any]], output_file: str) -> None:
        """Сохраняет результаты в JSON-файл."""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
    @staticmethod
    def save_to_excel(results: List[Dict[str, Any]], output_file: str) -> None:
        """Сохраняет результаты в Excel-файл."""
        df = pd.DataFrame([
            {
                'Company': r['company'],
                'Success': r['successful'],
                'Sources': ', '.join([res['source'] for res in r['results'] if res['result']]),
                'Results': ', '.join([str(res['result']) for res in r['results'] if res['result']])
            }
            for r in results
        ])
        df.to_excel(output_file, index=False)
            
    @staticmethod
    def print_stats(results: List[Dict[str, Any]]) -> None:
        """Выводит статистику по результатам поиска."""
        total = len(results)
        successful = sum(1 for r in results if r['successful'])
        
        # Подсчет успешных результатов по источникам
        sources = {}
        for r in results:
            for res in r['results']:
                if res['result']:
                    source = res['source']
                    sources[source] = sources.get(source, 0) + 1
        
        print("\n=== Статистика поиска ===")
        print(f"Всего компаний: {total}")
        print(f"Успешно найдено: {successful} ({successful/total*100:.1f}%)")
        print("\nПо источникам:")
        for source, count in sources.items():
            print(f"- {source}: {count} ({count/total*100:.1f}%)")
```

### 5. Экстрактор данных для генерации описаний

- [x] Создать файл `description_generator.py`:
```python
from openai import AsyncOpenAI
from typing import List, Dict, Any

class DescriptionGenerator:
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)
        
    async def generate_description(self, company_name: str, findings: List[Dict[str, Any]]) -> str:
        """
        Генерирует описание компании на основе найденных данных.
        
        Args:
            company_name: Название компании
            findings: Список результатов от различных финдеров
            
        Returns:
            str: Сгенерированное описание компании
        """
        # Подготовка данных для LLM
        data_points = []
        for finding in findings:
            if finding["result"]:
                data_points.append(f"Source: {finding['source']}, Data: {finding['result']}")
                
        if not data_points:
            return f"Недостаточно данных для генерации описания компании {company_name}."
            
        # Формирование промпта для LLM
        prompt = f"""
        Сгенерируй краткое описание компании {company_name} на основе следующих данных:
        
        {chr(10).join(data_points)}
        
        Описание должно быть информативным, лаконичным и профессиональным.
        """
        
        # Вызов LLM для генерации описания
        response = await self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты - эксперт по созданию деловых профилей компаний."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300
        )
        
        return response.choices[0].message.content.strip()
```

### 6. Обновление основного скрипта

- [x] Создать файл `company_search.py`:
```python
import asyncio
import aiohttp
import os
from dotenv import load_dotenv
from pathlib import Path

# Импорт компонентов системы
from finders import (
    WikidataFinder, 
    DomainFinder, 
    GoogleFinder, 
    WikipediaFinder,
    LinkedInFinder,
    LLMSearchFinder
)
from orchestrator import PipelineOrchestrator
from result_processor import ResultProcessor
from description_generator import DescriptionGenerator

# Вспомогательные функции
from utils import load_company_names

async def main():
    # Загрузка переменных окружения
    load_dotenv()
    
    # API ключи
    serper_api_key = os.getenv("SERPER_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not serper_api_key or not openai_api_key:
        print("Ошибка: Не найдены необходимые API ключи в .env файле")
        exit(1)
    
    # Путь к файлу с компаниями
    input_file = "input/companies.xlsx"
    output_file = "output/results.json"
    
    # Создаем ворклоад
    async with aiohttp.ClientSession() as session:
        # Инициализация финдеров
        finders = [
            WikidataFinder(),
            DomainFinder(),
            GoogleFinder(serper_api_key),
            WikipediaFinder(),
            LinkedInFinder(),
            LLMSearchFinder(openai_api_key)
        ]
        
        # Инициализация оркестратора
        orchestrator = PipelineOrchestrator(finders)
        
        # Инициализация генератора описаний
        description_generator = DescriptionGenerator(openai_api_key)
        
        # Загрузка имен компаний
        company_names = load_company_names(input_file)
        if not company_names:
            print(f"Не удалось загрузить компании из {input_file}")
            exit(1)
            
        print(f"Загружено {len(company_names)} компаний из {input_file}")
        
        # Обработка компаний
        results = []
        for company_name in company_names:
            # Поиск информации о компании
            result = await orchestrator.process(company_name, session)
            
            # Генерация описания на основе найденных данных
            if result["successful"]:
                description = await description_generator.generate_description(
                    company_name, 
                    result["results"]
                )
                result["description"] = description
            
            results.append(result)
            print(f"Обработана компания: {company_name}")
            
        # Сохранение результатов
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        ResultProcessor.save_to_json(results, output_file)
        ResultProcessor.save_to_excel(results, output_file.replace('.json', '.xlsx'))
        
        # Вывод статистики
        ResultProcessor.print_stats(results)

if __name__ == "__main__":
    asyncio.run(main())
```

- [x] Создать файл `utils.py` для вспомогательных функций:
```python
import pandas as pd
from pathlib import Path
from typing import List, Optional

def load_company_names(file_path: str) -> Optional[List[str]]:
    """
    Загружает список названий компаний из Excel/CSV файла.
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        Optional[List[str]]: Список названий компаний или None в случае ошибки
    """
    # Перенести логику из функции load_company_names
    # ...
```

## Структура проекта

```
company-search/
├── finders/
│   ├── __init__.py
│   ├── base.py
│   ├── wikidata_finder.py
│   ├── domain_finder.py
│   ├── google_finder.py
│   ├── wikipedia_finder.py
│   ├── linkedin_finder.py
│   └── llm_search_finder.py
├── orchestrator.py
├── result_processor.py
├── description_generator.py
├── utils.py
├── company_search.py
├── .env
├── requirements.txt
├── input/
│   └── companies.xlsx
└── output/
    ├── results.json
    └── results.xlsx
```

## Дополнительные задачи

- [x] Создать requirements.txt с необходимыми зависимостями
- [x] Настроить асинхронное выполнение для повышения производительности
- [x] Добавить обработку ошибок и логирование
- [x] Написать документацию по использованию модульной системы
- [ ] Создать тесты для проверки работы каждого финдера

## Примечания

- При реализации каждого финдера следует переиспользовать существующие функции из test_serper.py
- Для интеграции с LinkedIn может потребоваться дополнительная настройка API/скрапинга
- Для оптимальной производительности можно настроить параллельное выполнение финдеров
- Стоит рассмотреть возможность кеширования результатов для ускорения повторных запросов 