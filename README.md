# Модульный сервис поиска информации о компаниях

Модульный сервис для поиска информации о компаниях из различных источников и генерации описаний на основе найденных данных.

## Возможности

- Поиск информации о компаниях через различные источники:
  - Wikidata
  - Проверка доменов
  - Google (через Serper API)
  - Wikipedia
  - LinkedIn
  - LLM (OpenAI API)
- Обработка списка компаний пакетами для оптимизации
- Генерация описаний компаний на основе найденных данных
- Сохранение результатов в форматах JSON и Excel
- Подробная статистика по результатам поиска

## Установка

1. Клонируйте репозиторий:

```
git clone https://github.com/username/company-search.git
cd company-search
```

2. Создайте и активируйте виртуальное окружение:

```
python -m venv venv
# Для Windows
venv\Scripts\activate
# Для Linux/Mac
source venv/bin/activate
```

3. Установите зависимости:

```
pip install -r requirements.txt
```

4. Создайте файл `.env` с необходимыми API ключами:

```
SERPER_API_KEY=ваш_ключ_serper
OPENAI_API_KEY=ваш_ключ_openai
```

## Использование

1. Поместите список компаний в файл `input/companies.xlsx` (первый столбец должен содержать названия компаний).

2. Запустите скрипт:

```
python company_search.py
```

3. Результаты будут сохранены в директории `output/`:
   - `results.json` - полные результаты в формате JSON
   - `results.xlsx` - результаты в формате Excel

## Структура проекта

```
company-search/
├── finders/               # Модули для поиска информации
│   ├── __init__.py        # Экспорт всех финдеров
│   ├── base.py            # Базовый абстрактный класс Finder
│   ├── wikidata_finder.py # Финдер через Wikidata
│   ├── domain_finder.py   # Финдер через проверку доменов
│   ├── google_finder.py   # Финдер через Google Serper API
│   ├── wikipedia_finder.py # Финдер через парсинг Wikipedia
│   ├── linkedin_finder.py # Финдер через LinkedIn
│   └── llm_search_finder.py # Финдер через LLM
├── orchestrator.py        # Оркестратор для управления финдерами
├── result_processor.py    # Обработка и сохранение результатов
├── description_generator.py # Генерация описаний компаний
├── utils.py               # Вспомогательные функции
├── company_search.py      # Основной скрипт
├── .env                   # Файл с переменными окружения (API ключи)
├── requirements.txt       # Зависимости проекта
├── input/                 # Директория для входных файлов
│   └── companies.xlsx     # Список компаний
└── output/                # Директория для выходных файлов
    ├── results.json       # Результаты в формате JSON
    └── results.xlsx       # Результаты в формате Excel
```

## Добавление новых источников данных

Для добавления нового источника данных необходимо:

1. Создать новый класс, наследующийся от `Finder` в директории `finders/`:

```python
from .base import Finder

class NewSourceFinder(Finder):
    async def find(self, company_name: str, **context) -> dict:
        # Реализация поиска
        return {"source": "new_source", "result": result_or_none}
```

2. Добавить новый финдер в `finders/__init__.py`:

```python
from .new_source_finder import NewSourceFinder

__all__ = [
    # ...
    'NewSourceFinder'
]
```

3. Добавить новый финдер в список финдеров в `company_search.py`:

```python
finders = [
    # ...
    NewSourceFinder()
]
```

## Лицензия

MIT
