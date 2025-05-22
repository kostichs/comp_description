# План двухэтапной интеграции HubSpot в пайплайн обработки компаний

## Общая концепция

Реализовать двухэтапный процесс обработки компаний:
1. Первый этап: Быстрый поиск URL компании с помощью LLMDeepSearchFinder в режиме "только URL"
2. Проверка найденного URL в HubSpot
3. Второй этап: Полный сбор данных только если компания отсутствует в HubSpot или имеет устаревшее описание

## Необходимые изменения

### 1. Модификация LLMDeepSearchFinder для поддержки режима "только URL"

#### 1.1. Обновление класса LLMDeepSearchFinder

- [ ] Обновить класс `LLMDeepSearchFinder` в файле `finders/llm_deep_search_finder/finder.py`:
  - [ ] Добавить параметр `url_only_mode` в метод `find()`:
    ```python
    async def find(self, company_name, **context):
        url_only_mode = context.get('url_only_mode', False)
        # ... остальной код
    ```
  - [ ] Добавить загрузку специального промпта для режима "только URL" из конфигурации:
    ```python
    # В методе __init__ или find
    if url_only_mode and "llm_url_search_only_prompt" in self.config:
        prompt_template = self.config["llm_url_search_only_prompt"]
    else:
        prompt_template = self.config["prompt_template"]  # Стандартный промпт
    ```

#### 1.2. Создание специальных промптов

- [ ] Создать специальный промпт для режима "только URL" в `llm_deep_search_config.yaml`:
  ```yaml
  llm_url_search_only_prompt: |
    Я ищу официальный веб-сайт компании {company_name}.
    
    Найди только официальный сайт компании, не рассматривай социальные сети, агрегаторы, каталоги и т.п.
    
    Верни JSON-ответ строго в следующем формате:
    ```json
    {
      "website_url": "https://example.com"
    }
    ```
    
    Если URL не найден, верни:
    ```json
    {
      "website_url": null
    }
    ```
  ```

- [ ] Настроить модель для ограниченного поиска URL:
  ```yaml
  url_search_only_config:
    model: "gpt-3.5-turbo"  # Можно использовать более быструю модель для простых запросов
    temperature: 0.0
    max_tokens: 150
    response_format:
      type: "json_object"
  ```

#### 1.3. Оптимизация поисковых запросов

- [ ] Сократить количество поисковых запросов в режиме "только URL":
  ```python
  if url_only_mode:
      max_search_results = self.config.get("url_only_max_search_results", 3)  # Меньше результатов
      search_query = f"официальный сайт компании {company_name}"
  else:
      max_search_results = self.config.get("max_search_results", 8)  # Стандартное количество
      search_query = self._generate_search_query(company_name)
  ```

- [ ] Оптимизировать поисковые запросы для быстрого нахождения URL:
  - [ ] Создать специальные шаблоны запросов для поиска URL:
  ```python
    def _generate_url_search_query(self, company_name):
        """Генерирует оптимизированный запрос для поиска URL."""
        templates = [
            f"официальный сайт компании {company_name}",
            f"{company_name} official website",
            f"{company_name} corporate website"
        ]
        return random.choice(templates)
    ```
  
  - [ ] Добавить фильтрацию результатов для приоритизации URL:
  ```python
    def _filter_for_url_search(self, search_results):
        """Фильтрует результаты поиска для режима URL."""
        filtered = []
        for result in search_results:
            url = result.get("link")
            title = result.get("title", "").lower()
            if (
                url and 
                not any(domain in url for domain in ["linkedin.com", "facebook.com", "twitter.com"]) and
                ("official" in title or "главная" in title or company_name.lower() in title)
            ):
                filtered.append(result)
        return filtered[:3]  # Возвращаем только топ-3 результата
    ```

#### 1.4. Возврат частичных результатов

- [ ] Модифицировать обработку результатов LLM для возврата частичных данных:
  ```python
  if url_only_mode:
      try:
          # Обработка ответа LLM
          llm_response = await self._get_llm_response(
              prompt, 
              self.config.get("url_search_only_config", self.config)
          )
          
          result_json = json.loads(llm_response)
          
          # Валидация результата
          if isinstance(result_json, dict) and "website_url" in result_json:
              website_url = result_json["website_url"]
              if website_url:
                  # Проверка и нормализация URL
                  if not website_url.startswith(('http://', 'https://')):
                      website_url = 'https://' + website_url
                  
                  logger.info(f"URL-only mode: Found URL {website_url} for company {company_name}")
                  return {"source": "llm_deep_search", "result": {"website_url": website_url}}
          
          logger.warning(f"URL-only mode: No URL found for company {company_name}")
          return {"source": "llm_deep_search", "result": {"website_url": None}}
          
      except Exception as e:
          logger.error(f"URL-only mode: Error processing LLM response: {e}")
          return {"source": "llm_deep_search", "result": {"website_url": None}}
  ```

#### 1.5. Интеграция с механизмом кэширования

- [ ] Добавить отдельное кэширование для режима "только URL":
  ```python
  def _get_cache_key(self, company_name, url_only=False):
      """Генерирует ключ кэша с учетом режима работы."""
      if url_only:
          return f"url_only_{company_name.lower().strip()}"
      return f"full_{company_name.lower().strip()}"
  
  async def find(self, company_name, **context):
      url_only_mode = context.get('url_only_mode', False)
      
      # Проверка кэша с учетом режима
      cache_key = self._get_cache_key(company_name, url_only_mode)
      cached_result = self._check_cache(cache_key)
      
      if cached_result:
          logger.info(f"Using cached result for {company_name} (url_only_mode={url_only_mode})")
          return cached_result
      
      # ... основная логика поиска ...
      
      # Сохранение в кэш
      self._save_to_cache(cache_key, result)
      return result
  ```

#### 1.6. Метрики и логирование

- [ ] Добавить метрики для отслеживания производительности режима "только URL":
  ```python
  if url_only_mode:
      start_time = time.time()
      # ... логика поиска URL ...
      elapsed_time = time.time() - start_time
      logger.info(f"URL-only search took {elapsed_time:.2f} seconds for company {company_name}")
      
      # Обновить счетчики
      self.metrics["url_only_searches"] = self.metrics.get("url_only_searches", 0) + 1
      self.metrics["url_only_success"] = self.metrics.get("url_only_success", 0) + (1 if found_url else 0)
      self.metrics["url_only_avg_time"] = (
          (self.metrics.get("url_only_avg_time", 0) * (self.metrics["url_only_searches"] - 1) + elapsed_time) 
          / self.metrics["url_only_searches"]
      )
  ```

### 2. Модификация HubSpotAdapter для проверки компаний по URL

- [ ] Улучшить метод `check_company_description()` в `HubSpotAdapter`
  - [ ] Добавить логирование процесса проверки
  - [ ] Улучшить извлечение и нормализацию доменов из URL
  - [ ] Добавить настройку для определения "свежести" описания (по умолчанию 6 месяцев)
  - [ ] Возвращать структурированные данные компании при наличии

### 3. Модификация HubSpotPipelineAdapter для двухэтапной обработки

- [ ] Переопределить метод `run_pipeline_for_file()` в `HubSpotPipelineAdapter`
  - [ ] Добавить логику предварительного поиска URL через LLMDeepSearchFinder
  - [ ] Интегрировать проверку в HubSpot после нахождения URL
  - [ ] Реализовать условную обработку на основе результатов проверки HubSpot
  - [ ] Добавить счетчики для статистики (сколько компаний найдено в HubSpot)

### 4. Добавление конфигурации и параметров

- [ ] Обновить `llm_config.yaml` для поддержки новых параметров
  - [ ] Добавить параметр `hubspot_two_phase_search: true/false`
  - [ ] Добавить параметр `hubspot_description_freshness_days: 180` (по умолчанию 6 месяцев)
  - [ ] Добавить параметр `llm_url_search_only_prompt` для определения специального промпта

### 5. Обновление фабричного метода и функций создания адаптеров

- [ ] Обновить функцию `get_pipeline_adapter()` в `src/pipeline/__init__.py`
  - [ ] Добавить передачу параметров двухэтапной обработки
  - [ ] Обеспечить обратную совместимость с существующими вызовами

### 6. Доработка логирования и метрик

- [ ] Добавить новые поля для логирования и метрик
  - [ ] Логирование времени первого этапа (поиск URL)
  - [ ] Логирование результатов проверки в HubSpot
  - [ ] Логирование пропущенных компаний (найденных в HubSpot)
  - [ ] Добавить сводные метрики по итогам обработки

### 7. Оптимизация производительности

- [ ] Оптимизировать поиск URL в LLMDeepSearchFinder
  - [ ] Сократить количество запросов в режиме "только URL"
  - [ ] Использовать более короткие промпты для первого этапа
  - [ ] Настроить таймауты и повторные попытки для критических операций

### 8. Тестирование

- [ ] Создать тесты для новой функциональности
  - [ ] Тест режима "только URL" для LLMDeepSearchFinder
  - [ ] Тест двухэтапной обработки в HubSpotPipelineAdapter
  - [ ] Тест проверки компаний в HubSpot
  - [ ] Интеграционный тест полного пайплайна

## Детали реализации

### Модификация LLMDeepSearchFinder

  ```python
class LLMDeepSearchFinder:
    async def find(self, company_name, **context):
        url_only_mode = context.get('url_only_mode', False)
        
        if url_only_mode:
            # Упрощенный промпт для быстрого поиска URL
            prompt = f"Найдите официальный сайт компании {company_name}. Верните только URL."
            # Ограниченное количество запросов и поисковых результатов
            # Оптимизированная обработка результатов
            # ...
            return {"source": "llm_deep_search", "result": {"website_url": found_url}}
        else:
            # Стандартная полная обработка
      # ...
  ```

### Модификация HubSpotPipelineAdapter

```python
class HubSpotPipelineAdapter(PipelineAdapter):
    async def run_pipeline_for_file(self, ...):
        # Инициализация компонентов
        llm_deep_search_finder = self._init_llm_deep_search_finder()
        hubspot_client = self.hubspot_client
        
        # Проверка, включена ли двухэтапная обработка
        two_phase_enabled = self.llm_config.get("hubspot_two_phase_search", False)
        
        if not two_phase_enabled:
            # Стандартная обработка, если двухэтапный режим отключен
            return await super().run_pipeline_for_file(...)
        
        results = []
        
        for company in companies:
            # Если URL не предоставлен, найти его через LLMDeepSearchFinder
            if not company.get('url'):
                # Первый этап - поиск URL
                url_result = await llm_deep_search_finder.find(
                    company['name'], 
                    url_only_mode=True,
                    session=aiohttp_session,
                    openai_client=openai_client,
                    serper_api_key=serper_api_key
                )
                
                structured_data = url_result.get('result', {})
                found_url = structured_data.get('website_url')
                
                # Если URL найден, проверить в HubSpot
                if found_url:
                    should_process, hubspot_data = await hubspot_client.check_company_description(
                        company['name'], found_url)
                    
                    if not should_process and hubspot_data:
                        # Использовать данные из HubSpot, пропустить полную обработку
                        results.append({
                            "Company_Name": company['name'],
                            "Official_Website": found_url,
                            "Description": hubspot_data.get('description', ''),
                            "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "From_HubSpot": True
                        })
                        continue
            
            # Если HubSpot не предоставил данные или URL не найден,
            # выполнить полную обработку
            full_result = await self._process_single_company_async(...)
            results.append(full_result)
```

## Преимущества подхода

1. **Экономия ресурсов**: Полный сбор данных выполняется только для компаний, не найденных в HubSpot
2. **Оптимизация скорости**: Первый этап (поиск URL) выполняется быстрее, чем полный сбор данных
3. **Гибкость**: Возможность настройки параметров интеграции через конфигурационный файл
4. **Согласованность данных**: Использование данных из HubSpot обеспечивает согласованность между системами
5. **Масштабируемость**: Подход легко масштабируется для обработки больших объемов данных

## Потенциальные риски и ограничения

1. **Ложные срабатывания**: Если URL найден неправильно, проверка в HubSpot может дать некорректные результаты
2. **Задержки API**: При высокой нагрузке могут возникать задержки в ответах API HubSpot
3. **Ограничения скорости**: Необходимо учитывать лимиты запросов к API HubSpot
4. **Сложность отладки**: Двухэтапный процесс может быть сложнее для отладки и мониторинга

## Следующие шаги после реализации

1. Мониторинг производительности и эффективности
2. Сбор метрик по количеству компаний, найденных в HubSpot
3. Оптимизация промптов и параметров поиска
4. Расширение интеграции с другими системами (при необходимости) 