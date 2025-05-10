# План Реализации: Параллельные Пайплайны Обработки Компаний

**Цель:** Реализовать возможность выбора между стандартным пайплайном обработки и новым пайплайном "LLM Deep Search" (с возможностью их комбинации) через UI, для получения более детализированной информации о компаниях.

---

## Фаза 1: Подготовка и Разработка Функционала "LLM Deep Search"

### 1.1. Определение Специфичных Запросов для LLM Deep Search
    - [ ] Составить список конкретных вопросов для LLM, направленных на извлечение глубокой финансовой и бизнес-информации (например, ARR, количество сотрудников, детали финансирования, ключевые продукты/конкуренты).
    - [ ] Решить, будет ли этот список статичным или конфигурируемым (например, через `llm_config.yaml`). (Для начала можно сделать статичным).

### 1.2. Разработка Новой Функции для LLM Deep Search
    - [ ] Создать новый файл: `src/llm_deep_search.py` (или решить, будет ли это частью `src/external_apis/openai_client.py`).
    - [ ] Реализовать асинхронную функцию `query_llm_for_deep_info` в этом файле:
        - **Сигнатура:**
          ```python
          async def query_llm_for_deep_info(
              openai_client: AsyncOpenAI, # или специфичный клиент для GPT Search
              company_name: str,
              text_sources_for_deep_search: str, # Комбинированный текст из доступных источников
              specific_queries: List[str] 
          ) -> Dict[str, Any]: # Возвращает словарь {query: answer}
          ```
        - **Логика:**
            - Итерация по `specific_queries`.
            - Для каждого запроса: формирование специфичного промпта, включающего `company_name`, `text_sources_for_deep_search`, и сам `query`.
            - Вызов OpenAI API (или GPT Search API) с этим промптом.
            - Обработка ответа, извлечение ответа LLM.
            - Сохранение пары (запрос: ответ) в результирующий словарь.
        - **Обработка Ошибок:**
            - Реализовать базовую обработку ошибок для вызовов API (например, `try...except` для `openai.APIError`, `TimeoutError`).
            - Логирование ошибок и успешных запросов.
            - *(Позже, после базовой реализации, можно будет добавить `tenacity` для retry, если потребуется)*.
        - **Возвращаемое значение:** Словарь с результатами или словарь с ключом "error" в случае общей неудачи.
    - [ ] Провести юнит-тестирование функции `query_llm_for_deep_info` в изоляции.

---

## Фаза 2: Интеграция в Существующий Пайплайн

### 2.1. Модификация UI (`frontend/`)
    - [ ] **`frontend/index.html`**:
        - Добавить два чекбокса:
            - "Standard Pipeline" (по умолчанию включен).
            - "LLM Deep Search Pipeline" (по умолчанию выключен).
        - Присвоить им `id` и `name` (например, `standard_pipeline` и `llm_deep_search_pipeline`).
    - [ ] **`frontend/app.js`**:
        - При формировании `FormData` для запроса `POST /api/sessions` (создание новой сессии):
            - Считать состояния чекбоксов.
            - Добавить их значения в `FormData` (например, `formData.append('run_standard_pipeline', document.getElementById('standardPipeline').checked);`).

### 2.2. Модификация Бэкенда (`backend/main.py`)

    - [ ] **Эндпоинт `POST /api/sessions` (Создание сессии):**
        - Принять новые параметры из формы: `run_standard_pipeline: bool = Form(True)`, `run_llm_deep_search_pipeline: bool = Form(False)`.
        - Сохранить эти флаги в метаданные создаваемой сессии (в `sessions_metadata.json`).
    - [ ] **Функция `execute_pipeline_for_session_async` (или аналогичная, запускающая пайплайн для сессии):**
        - Прочитать сохраненные флаги `run_standard_pipeline` и `run_llm_deep_search_pipeline` из метаданных сессии.
        - Передать эти флаги как параметры в функцию `run_pipeline_for_file` из `src/pipeline.py`.
        - **Обновление `expected_csv_fieldnames`:**
            - Определить, какие новые колонки появятся в CSV от "LLM Deep Search" (например, `deep_search_arr`, `deep_search_employees`, или более общие `deep_search_query1_answer`, `deep_search_query2_answer` и т.д., соответствующие `specific_queries`).
            - Добавить эти новые имена колонок в `base_ordered_fields` (или в `additional_llm_fields`, если это подходит по логике) при формировании `expected_csv_fieldnames` внутри этой функции. Этот список затем передается в `run_pipeline_for_file`.

### 2.3. Модификация Основного Пайплайна (`src/pipeline.py`)

    - [ ] **Функция `run_pipeline_for_file`:**
        - Добавить новые булевы параметры в сигнатуру: `run_standard_pipeline: bool`, `run_llm_deep_search: bool`.
        - Передавать эти параметры дальше в каждую задачу `process_company`.
    - [ ] **Функция `process_company`:**
        - Добавить новые булевы параметры в сигнатуру: `run_standard_pipeline: bool`, `run_llm_deep_search: bool`.
        - **Инициализация `result_data`:**
            - Добавить ключи для новых полей от LLM Deep Search со значениями по умолчанию (например, "N/A" или "Not run").
        - **Условное выполнение блоков:**
            - **Стандартный пайплайн:**
                ```python
                if run_standard_pipeline:
                    # ... (существующая логика: Serper, Scrape, Wikipedia, стандартное описание LLM)
                    # ... (запись в result_data["homepage"], result_data["linkedin"], result_data["description"])
                else:
                    # Заполнить стандартные поля заглушками, если этот пайплайн не выбран
                    result_data["homepage"] = "Standard pipeline not run" 
                    result_data["linkedin"] = "Standard pipeline not run"
                    result_data["description"] = "Standard pipeline not run"
                ```
            - **LLM Deep Search пайплайн:**
                ```python
                if run_llm_deep_search:
                    # 1. Сбор/подготовка `text_sources_for_deep_search`
                    #    (можно использовать/адаптировать существующий `final_text_source_for_llm` или его компоненты)
                    #    Убедиться, что общие шаги (поиск URL, скрейпинг) выполняются, если нужен их результат.
                    # 2. Определение `specific_queries` (список вопросов).
                    # 3. Вызов `await query_llm_for_deep_info(...)` из `src/llm_deep_search.py`.
                    # 4. Заполнение соответствующих полей в `result_data` (например, `result_data["deep_search_arr"] = ...`).
                else:
                    # Заполнить поля deep_search заглушками
                    result_data["deep_search_arr"] = "Deep search not run" 
                    # ... и т.д. для других полей deep_search
                ```
        - **Агрегация результатов (если оба пайплайна выполнены):**
            - Продумать, нужно ли как-то комбинировать `result_data["description"]` с результатами `deep_search_results`.
            - *Вариант А:* Оставить их раздельными (стандартное описание в своей колонке, результаты deep search - в своих новых колонках). Это проще.
            - *Вариант Б:* Дополнить стандартное описание инсайтами из deep search. (Более сложная логика).
            - **Для начала реализуем Вариант А.**

---

## Фаза 3: Тестирование и Итерации

### 3.1. Тестирование каждого пайплайна по отдельности
    - [ ] Проверить работу "Standard Pipeline" (чекбокс включен, LLM Deep Search выключен).
    - [ ] Проверить работу "LLM Deep Search Pipeline" (чекбокс включен, Standard выключен). Убедиться, что собираются необходимые данные для LLM Deep Search и результаты корректно записываются в новые колонки.
    - [ ] Проанализировать логи и выходные CSV для каждого случая.

### 3.2. Тестирование комбинированной работы
    - [ ] Проверить работу, когда оба чекбокса включены.
    - [ ] Убедиться, что результаты обоих пайплайнов корректно агрегируются/записываются.
    - [ ] Оценить общее время выполнения.

### 3.3. Оптимизация и Доработка (при необходимости)
    - [ ] Оптимизировать промпты для `query_llm_for_deep_info`.
    - [ ] Рассмотреть добавление `tenacity` для `query_llm_for_deep_info`, если наблюдаются ошибки API.
    - [ ] Проанализировать производительность и стоимость.

---

## Фаза 4: Обновление Документации

### 4.1. `doc/ARCHITECTURE.md`
    - [ ] Описать новые функции в `src/llm_deep_search.py`.
    - [ ] Обновить описание `process_company` с учетом условного выполнения пайплайнов и новых полей в `result_data`.
    - [ ] Обновить описание эндпоинта `POST /api/sessions` для отражения новых параметров (`run_standard_pipeline`, `run_llm_deep_search_pipeline`).
    - [ ] Обновить описание структуры CSV, включив новые колонки.

### 4.2. `README.md`
    - [ ] Добавить информацию о новой возможности "LLM Deep Search".
    - [ ] Описать, как выбирать пайплайны через UI.
    - [ ] Обновить описание выходного формата CSV.

---