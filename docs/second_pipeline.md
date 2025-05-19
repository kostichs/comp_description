
# Анализ и план реализации двух типов входных данных

## Текущее состояние
В текущей реализации:
1. Фронтенд позволяет загружать CSV/XLSX файлы с одной колонкой (названия компаний)
2. Бэкенд обрабатывает эти данные через пайплайн, используя все финдеры
3. Пайплайн последовательно использует LLMDeepSearchFinder, HomepageFinder и другие

## План реализации

### 1. Модификация обработки входных файлов

1. **Изменение функции загрузки файлов в бэкенде:**
   ```python
   # Изменить функцию load_and_prepare_company_names
   # src/data_io.py
   def load_and_prepare_company_names(file_path, company_col_index=0, url_col_index=None):
       # Загрузка данных из файла (CSV или XLSX)
       # Определение наличия второй колонки
       # Возврат списка кортежей (название_компании, url) или списка названий компаний
       # url может быть None, если второй колонки нет
       
       # Определяем тип файла
       file_extension = Path(file_path).suffix.lower()
       
       # Инициализируем список для результатов
       companies_data = []
       
       if file_extension == '.csv':
           with open(file_path, 'r', encoding='utf-8') as f:
               csv_reader = csv.reader(f)
               headers = next(csv_reader, None)  # Пропускаем заголовок
               
               # Проверяем количество колонок
               has_url_column = len(headers) > 1 if headers else False
               
               for row in csv_reader:
                   if not row or not row[company_col_index].strip():
                       continue
                       
                   company_name = row[company_col_index].strip()
                   homepage_url = row[url_col_index].strip() if has_url_column and url_col_index < len(row) and row[url_col_index].strip() else None
                   
                   companies_data.append((company_name, homepage_url))
       
       elif file_extension in ['.xlsx', '.xls']:
           # Аналогичная логика для Excel файлов
           
       return companies_data
   ```

2. **Добавление метаданных о типе файла:**
   ```python
   # В file_handler.py или data_io.py
   def save_session_metadata(session_id, file_name, total_companies, has_homepage_urls=False):
       metadata = {
           "session_id": session_id,
           "file_name": file_name,
           "total_companies": total_companies,
           "creation_time": time.time(),
           "has_homepage_urls": has_homepage_urls,  # Новое поле
       }
       # Сохранение метаданных
   ```

### 2. Модификация пайплайна

1. **Изменение функции process_single_company_async:**
   ```python
   # В pipeline_adapter.py
   async def _process_single_company_async(
       company_name: str,
       openai_client: AsyncOpenAI,
       aiohttp_session: aiohttp.ClientSession,
       sb_client: ScrapingBeeClient,
       serper_api_key: str,
       finder_instances: Dict[str, Finder],
       description_generator: DescriptionGenerator,
       llm_config: Dict[str, Any],
       raw_markdown_output_path: Path,
       output_csv_path: Optional[str],
       output_json_path: Optional[str],
       csv_fields: List[str],
       company_index: int,
       total_companies: int,
       context_text: Optional[str] = None,
       run_llm_deep_search_pipeline: bool = True,
       run_standard_homepage_finders: bool = True,
       run_domain_check_finder: bool = True,
       predefined_homepage_url: Optional[str] = None,  # Новый параметр
       llm_deep_search_config_override: Optional[Dict[str, Any]] = None,
       broadcast_update: Optional[Callable] = None
   ) -> Dict[str, Any]:
       # ...
       
       # Переменные для итогового homepage и его источника
       final_homepage_url: Optional[str] = predefined_homepage_url  # Используем предопределенный URL, если он есть
       final_homepage_source: Optional[str] = "predefined" if predefined_homepage_url else None
       # ...
       
       # Добавляем проверку наличия URL перед запуском LLMDeepSearchFinder для поиска homepage
       run_homepage_search_in_llm = run_llm_deep_search_pipeline and not final_homepage_url
       
       # --- Этап 1: LLM Deep Search (если включен) ---
       if broadcast_update: await broadcast_update({"type": "progress", "company": company_name, "current": company_index + 1, "total": total_companies, "status": "processing_llm_deep_search"})
       llm_deep_search_finder = finder_instances.get('LLMDeepSearchFinder')
       if run_llm_deep_search_pipeline and llm_deep_search_finder:
           # ...
           # Модифицируем context, чтобы указать, нужно ли искать homepage
           context['search_for_homepage'] = run_homepage_search_in_llm
           # ...
       
       # --- Этап 2: HomepageFinder (Wikidata, Google->Wiki) ---
       # Запускаем только если нет предопределенного URL и первый этап не нашел URL
       # ...
   ```

2. **Модификация основного метода run_pipeline_for_file:**
   ```python
   # В pipeline_adapter.py
   async def run_pipeline_for_file(
       input_file_path: str | Path,
       output_csv_path: str | Path,
       pipeline_log_path: str,
       session_dir_path: Path,
       llm_config: Dict[str, Any],
       context_text: str | None,
       company_col_index: int,
       url_col_index: int = 1,  # Добавляем новый параметр
       aiohttp_session: aiohttp.ClientSession,
       sb_client: ScrapingBeeClient,
       openai_client: AsyncOpenAI,
       serper_api_key: str,
       expected_csv_fieldnames: list[str],
       broadcast_update: callable = None,
       main_batch_size: int = DEFAULT_BATCH_SIZE, 
       run_standard_pipeline: bool = True,
       run_llm_deep_search_pipeline: bool = True,
   ) -> tuple[int, int, list[dict]]:
       # ...
       
       # Загружаем компании и проверяем, есть ли предопределенные URL
       companies_data = load_and_prepare_company_names(input_file_path, company_col_index, url_col_index)
       
       # Определяем, есть ли URLs во входных данных
       has_predefined_urls = any(data[1] for data in companies_data)
       
       # Сохраняем эту информацию в метаданных
       save_session_metadata(session_id, input_file_path.name, len(companies_data), has_predefined_urls)
       
       # Если есть предопределенные URLs, отключаем стандартный пайплайн поиска homepage
       if has_predefined_urls:
           run_standard_pipeline = False  # Отключаем стандартный пайплайн для homepage
       
       # Модифицируем передачу данных в process_companies
       company_names = [data[0] for data in companies_data]
       homepage_urls = [data[1] for data in companies_data] if has_predefined_urls else [None] * len(companies_data)
       
       results = await process_companies(
           company_names=company_names,
           homepage_urls=homepage_urls,  # Передаем предопределенные URLs
           openai_client=openai_client,
           aiohttp_session=aiohttp_session,
           sb_client=sb_client,
           serper_api_key=serper_api_key,
           llm_config=llm_config,
           raw_markdown_output_path=raw_markdown_output_path,
           batch_size=main_batch_size,
           context_text=context_text,
           run_llm_deep_search_pipeline_cfg=run_llm_deep_search_pipeline,
           run_standard_pipeline_cfg=run_standard_pipeline,
           # ...
       )
       # ...
   ```

3. **Модификация process_companies:**
   ```python
   # В pipeline_adapter.py
   async def process_companies(
       company_names: List[str],
       openai_client: AsyncOpenAI,
       aiohttp_session: aiohttp.ClientSession,
       sb_client: ScrapingBeeClient,
       serper_api_key: str,
       llm_config: Dict[str, Any],
       raw_markdown_output_path: Path,
       batch_size: int, 
       homepage_urls: Optional[List[str]] = None,  # Новый параметр
       context_text: Optional[str] = None,
       run_llm_deep_search_pipeline_cfg: bool = True,
       run_standard_pipeline_cfg: bool = True,
       run_domain_check_finder_cfg: bool = True,
       broadcast_update: Optional[Callable] = None,
       output_csv_path: Optional[str] = None,
       output_json_path: Optional[str] = None,
       llm_deep_search_config_override: Optional[Dict[str, Any]] = None
   ) -> List[Dict[str, Any]]:
       # ...
       
       # Если homepage_urls не определены, создаем список None
       if homepage_urls is None:
           homepage_urls = [None] * len(company_names)
       
       # Остальной код...
       
       for batch_idx in range(0, len(company_names), batch_size):
           batch = company_names[batch_idx:batch_idx + batch_size]
           batch_urls = homepage_urls[batch_idx:batch_idx + batch_size]
           
           tasks = []
           for i, (company, homepage_url) in enumerate(zip(batch, batch_urls)):
               idx = batch_idx + i
               # Передаем homepage_url в _process_single_company_async
               task = asyncio.create_task(_process_single_company_async(
                   company_name=company,
                   # ...
                   predefined_homepage_url=homepage_url,  # Передаем URL, если он есть
                   # ...
               ))
               tasks.append(task)
           # ...
   ```

### 3. Модификация фронтенда

1. **Изменения в HTML и CSS:**
   
   ```html
   <!-- В index.html -->
   <div class="dropZone-instructions">
       <p>Поддерживаемые форматы: CSV, XLSX.</p>
       <p>Обнаружены следующие варианты данных:</p>
       <ul>
           <li>Один столбец: название компании в первом столбце (первая строка - заголовок)</li>
           <li>Два столбца: название компании в первом столбце и URL домашней страницы во втором (первая строка - заголовок)</li>
       </ul>
   </div>
   ```

2. **Изменения в JavaScript (app.js):**
   
   ```javascript
   // В uploadForm.addEventListener('submit', async (e) => {...})
   
   // После успешной загрузки файла 
   const response = await fetch('/api/sessions', {
       method: 'POST',
       body: formData
   });
   
   const sessionData = await response.json();
   currentSessionId = sessionData.session_id;
   
   // Отображаем информацию о типе файла
   if (sessionData.has_homepage_urls) {
       if (progressStatus) {
           progressStatus.textContent = 'Обработка файла с предопределенными URL домашних страниц...';
       }
   } else {
       if (progressStatus) {
           progressStatus.textContent = 'Обработка файла только с названиями компаний...';
       }
   }
   
   await startProcessingImmediately(currentSessionId);
   ```

### 4. Модификация серверной части (API эндпоинты)

1. **Модификация обработчика загрузки файла:**
   ```python
   # В файле с API (routes.py, main.py, etc.)
   @router.post("/api/sessions")
   async def create_session(
       file: UploadFile,
       context_text: Optional[str] = Form(None),
       run_standard_pipeline: bool = Form(True),
       run_llm_deep_search_pipeline: bool = Form(True)
   ):
       # Сохраняем файл
       file_path = save_uploaded_file(file)
       
       # Проверяем количество колонок
       has_homepage_urls = check_if_file_has_homepage_urls(file_path)
       
       # Создаем сессию
       session_id = create_session_id()
       
       # Сохраняем метаданные
       save_session_metadata(session_id, file.filename, 0, has_homepage_urls)
       
       return {"session_id": session_id, "has_homepage_urls": has_homepage_urls}
   ```

2. **Добавление функции проверки наличия колонки с URL:**
   ```python
   # В data_io.py или соответствующем файле
   def check_if_file_has_homepage_urls(file_path):
       """Проверяет, есть ли в файле колонка с URL домашних страниц"""
       file_extension = Path(file_path).suffix.lower()
       
       if file_extension == '.csv':
           with open(file_path, 'r', encoding='utf-8') as f:
               csv_reader = csv.reader(f)
               headers = next(csv_reader, None)
               if headers and len(headers) > 1:
                   # Проверяем, содержит ли вторая колонка URL
                   for row in csv_reader:
                       if len(row) > 1 and row[1].strip():
                           return is_valid_url(row[1].strip())
                       break
       
       elif file_extension in ['.xlsx', '.xls']:
           # Аналогичная логика для Excel
           
       return False
   ```

3. **Валидация URL:**
   ```python
   # Вспомогательная функция для проверки URL
   def is_valid_url(url):
       """Проверяет, является ли строка действительным URL"""
       try:
           result = urlparse(url)
           return all([result.scheme, result.netloc])
       except:
           return False
   ```

### 5. Модификация LLMDeepSearchFinder

1. **Опциональное отключение поиска homepage URL:**
   ```python
   # В LLMDeepSearchFinder.find() метод
   async def find(self, company_name: str, **context) -> Dict[str, Any]:
       # ...
       search_for_homepage = context.get('search_for_homepage', True)
       
       if search_for_homepage:
           # Выполняем поиск homepage URL
           # ...
       else:
           # Пропускаем поиск homepage URL
           # ...
       
       # ...
   ```

### 6. Тестирование

1. **Тестовые файлы:**
   - Создать тестовый CSV с одной колонкой
   - Создать тестовый CSV с двумя колонками
   - Проверить корректность обработки обоих файлов

2. **Элементы для тестирования:**
   - Правильное определение типа файла
   - Корректная загрузка данных
   - Отключение поиска homepage для файлов с предопределенными URL
   - Корректная работа пайплайна в обоих режимах
   - Правильное отображение информации о типе файла в UI

## Заключение

Этот план позволит реализовать два режима работы вашего приложения в зависимости от типа входных данных:
1. Обычный режим для файлов только с названиями компаний
2. Режим с предопределенными URL для файлов с двумя колонками

Реализация достаточно прямолинейна и заключается в:
1. Определении типа входного файла
2. Адаптации пайплайна в зависимости от наличия предопределенных URL
3. Модификации UI для отображения соответствующей информации
