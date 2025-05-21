# Структура разбиения pipeline_adapter.py

## 1. Основные модули

### `src/pipeline/`
Основная директория для всех файлов конвейера

### `src/pipeline/__init__.py`
Экспортирует основные публичные функции:
- `run_pipeline`
- `run_pipeline_for_file`

### `src/pipeline/adapter.py`
Содержит основной класс `PipelineAdapter`, который заменит большую часть pipeline_adapter.py и более удобно управляет состоянием

### `src/pipeline/core.py`
Содержит основные функции процесса:
- `process_companies`
- `_process_single_company_async`

### `src/pipeline/utils/`
Директория для вспомогательных функций

### `src/pipeline/utils/markdown.py`
Содержит функции для форматирования и сохранения отчетов:
- `_generate_and_save_raw_markdown_report_async`

### `src/pipeline/utils/logging.py`
Содержит функции настройки логирования:
- `setup_session_logging`

## 2. Интеграции с внешними сервисами

### `src/integrations/`
Корневая директория для разных внешних интеграций

### `src/integrations/hubspot/`
Директория для всех компонентов интеграции с HubSpot

### `src/integrations/hubspot/client.py`
Содержит класс `HubSpotClient`

### `src/integrations/hubspot/adapter.py`
Содержит расширение основного пайплайна:
- Класс `HubSpotPipelineAdapter` (наследует `PipelineAdapter`)

### `src/integrations/hubspot/service.py`
Содержит логику интеграции:
- Класс `HubSpotIntegrationService`

## 3. Архитектура и взаимодействие

1. `src/pipeline/adapter.py` содержит основной функционал пайплайна
2. `src/integrations/hubspot/adapter.py` наследует и расширяет класс `PipelineAdapter`
3. Точка входа `run_pipeline` в `src/pipeline/__init__.py` выбирает правильную реализацию в зависимости от конфигурации

## 4. Алгоритм миграции

1. Создать необходимую структуру директорий
2. Перенести базовый функционал в `src/pipeline/core.py` и `src/pipeline/utils/*.py`
3. Создать класс `PipelineAdapter` в `src/pipeline/adapter.py`
4. Перенести интеграцию HubSpot в `src/integrations/hubspot/`
5. Создать новую точку входа в `src/pipeline/__init__.py`
6. Обновить импорты в существующем коде 