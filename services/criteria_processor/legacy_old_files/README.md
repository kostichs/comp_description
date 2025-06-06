# Старые файлы (Legacy)

Эта папка содержит старые файлы которые были заменены новой модульной архитектурой.

## Миграция файлов:

### Конфигурация
- `config.py` → `src/utils/config.py` + `config/settings.py`
- `promt_generate.yaml` → `config/prompts.yaml`

### Логирование  
- `logger_config.py` → `src/utils/logging.py`

### Модели
- `models.py` → `src/external/openai_client.py`

### Данные
- `data_utils.py` (293 строки) → разбит на:
  - `src/data/encodings.py`
  - `src/data/loaders.py` 
  - `src/data/savers.py`

### Критерии
- `criteria_checkers.py` (230 строк) → разбит на:
  - `src/criteria/base.py`
  - `src/criteria/general.py`
  - `src/criteria/qualification.py`
  - `src/criteria/mandatory.py`
  - `src/criteria/nth.py`

### Форматирование
- `json_formatter.py` (222 строки) → разбит на:
  - `src/formatters/json_format.py`
  - `src/formatters/csv_format.py`

### Внешние API
- `serper_utils.py` (229 строк) → `src/external/serper.py`

### Дополнительные модули
- `sanctions_checker.py` → можно интегрировать в `src/filters/`
- `scoring_system.py` → можно интегрировать в `src/criteria/`

### Тесты
- `test_structure.py` → заменен на `test_new_architecture.py`

## Статус
Все файлы успешно мигрированы в новую архитектуру.
Можно безопасно удалить через некоторое время после тестирования новой системы. 