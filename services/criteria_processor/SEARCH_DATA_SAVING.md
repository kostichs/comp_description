# Search Data Saving System

## Описание

Система автоматического сохранения всех поисковых данных (Serper + ScrapingBee) в markdown файлы для каждой компании в папке сессии критериев.

## Функциональность

### Что сохраняется

1. **Serper Search Results**
   - Organic search results (title, URL, snippet)
   - Knowledge Graph data
   - Answer Box information
   - People Also Ask questions
   - Related Searches

2. **ScrapingBee Scraped Content**
   - Full scraped text content (first 10K characters)
   - Content preview (first 500 characters)
   - HTTP status codes
   - Error messages if any
   - Related search queries

### Структура файлов

```
services/criteria_processor/output/
├── [session_id]/
│   ├── search_data/                    # Новая папка с поисковыми данными
│   │   ├── Company_Name_search_data.md # Markdown файл для каждой компании
│   │   ├── Another_Company_search_data.md
│   │   └── ...
│   ├── analysis_results_*.json         # Основные результаты анализа
│   ├── analysis_results_*.csv
│   ├── serper_results/                 # Старые JSON файлы (сохраняются)
│   └── scrapingbee_logs/              # Старые лог файлы (сохраняются)
```

### Формат Markdown файлов

Каждый файл содержит:

1. **Header** - название компании, дата, session ID
2. **Summary** - количество поисков и скрапленных страниц
3. **Serper Search Results** - детальные результаты каждого поиска
4. **Scraped Pages Content** - содержимое всех скрапленных страниц
5. **Footer** - информация о генерации

## Техническая реализация

### Основные компоненты

1. **SearchDataSaver** (`src/data/search_data_saver.py`)
   - Класс для накопления и сохранения поисковых данных
   - Методы для добавления Serper и ScrapingBee данных
   - Генерация markdown контента

2. **Глобальные функции**
   - `initialize_search_data_saver(session_id)` - инициализация для сессии
   - `save_serper_search_data()` - сохранение данных Serper
   - `save_scrapingbee_data()` - сохранение данных ScrapingBee
   - `finalize_search_data_saving()` - финализация и сохранение файлов

### Интеграция

Система интегрирована во все основные процессоры:

- `src/core/processor.py` - обычный анализ
- `src/core/parallel_processor.py` - параллельный анализ
- `src/core/recovery.py` - восстановление сессий
- `src/external/serper.py` - Serper API
- `src/external/scrapingbee_client.py` - ScrapingBee API

### Автоматическое сохранение

1. **Инициализация** - в начале каждого анализа
2. **Накопление данных** - при каждом вызове Serper/ScrapingBee
3. **Финализация** - в конце анализа, сохранение всех markdown файлов

## Преимущества

1. **Полная трассируемость** - все поисковые данные сохраняются
2. **Человекочитаемый формат** - markdown легко читать и анализировать
3. **Структурированность** - четкая организация данных по компаниям
4. **Возможность повторного использования** - данные можно использовать для базы данных
5. **Отладка** - легко понять откуда взялись данные для анализа

## Использование

Система работает автоматически при запуске любого анализа критериев. Никаких дополнительных действий не требуется.

Для просмотра сохраненных данных:
1. Перейдите в папку сессии: `services/criteria_processor/output/[session_id]/`
2. Откройте папку `search_data/`
3. Просмотрите markdown файлы для интересующих компаний

## Совместимость

- Работает со всеми режимами анализа (обычный, оптимизированный, параллельный)
- Совместимо с существующими системами логирования
- Не влияет на производительность анализа
- Сохраняет обратную совместимость со старыми форматами логов 