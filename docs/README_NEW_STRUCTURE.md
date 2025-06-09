# Новая структура проекта Company Description Generator

## Обзор
Этот проект был реструктуризирован для улучшения поддерживаемости кода, устранения проблем с форматированием в больших файлах и упрощения добавления новых интеграций и фич.

## Структура директорий

```
company-description/
│
├── src/                        # Основной код проекта
│   ├── pipeline/               # Основной модуль пайплайна
│   │   ├── __init__.py         # Экспортирует публичное API
│   │   ├── adapter.py          # Основной класс PipelineAdapter
│   │   ├── core.py             # Основные функции процесса
│   │   └── utils/              # Вспомогательные функции
│   │       ├── __init__.py     
│   │       ├── logging.py      # Настройка логирования
│   │       └── markdown.py     # Функции для отчетов
│   │
│   ├── integrations/           # Внешние интеграции
│   │   ├── __init__.py
│   │   └── hubspot/            # HubSpot интеграция
│   │       ├── __init__.py
│   │       ├── adapter.py      # HubSpotPipelineAdapter
│   │       ├── client.py       # HubSpotClient для API
│   │       └── service.py      # HubSpotIntegrationService
│   │
│   ├── config.py               # Конфигурация проекта
│   └── data_io.py              # Функции ввода/вывода данных
│
├── run_pipeline.py             # Точка входа для запуска пайплайна
├── llm_config.yaml             # Конфигурация LLM
└── .env                        # API ключи и переменные окружения
```

## Основные изменения

### 1. Модульная структура
- Большой файл `pipeline_adapter.py` разбит на несколько меньших модулей
- Код сгруппирован по функциональности (pipeline, integrations)
- Точка входа вынесена в отдельный файл `run_pipeline.py`

### 2. Объектно-ориентированный подход
- Основной код переписан в виде классов
- `PipelineAdapter` - базовый класс для работы с пайплайном
- `HubSpotPipelineAdapter` - расширение с поддержкой HubSpot

### 3. Интеграции
- Внешние интеграции выделены в отдельную директорию
- HubSpot интеграция полностью инкапсулирована

## Использование

### Запуск пайплайна
```bash
python run_pipeline.py --input companies.csv --config llm_config.yaml
```

### Опции командной строки
- `--input` / `-i`: Путь к входному CSV файлу (по умолчанию: test_companies.csv)
- `--config` / `-c`: Путь к файлу конфигурации (по умолчанию: llm_config.yaml)
- `--use-hubspot`: Включить интеграцию с HubSpot
- `--disable-hubspot`: Отключить интеграцию с HubSpot

### HubSpot интеграция
Для работы интеграции HubSpot необходимо:
1. Добавить API ключ в файл `.env`: `HUBSPOT_API_KEY=your_api_key_here`
2. Включить интеграцию в `llm_config.yaml`:
```yaml
use_hubspot_integration: true
hubspot_description_max_age_months: 6
```

## Разработка

### Добавление новых интеграций
1. Создайте новую директорию в `src/integrations/`
2. Создайте клиент для API в `client.py`
3. Реализуйте бизнес-логику в `service.py`
4. Создайте расширение пайплайна в `adapter.py`
5. Обновите фабрику в `src/pipeline/__init__.py`

### Добавление новых Finder'ов
1. Реализуйте новый Finder в `finders/`
2. Добавьте его в `PipelineAdapter` 