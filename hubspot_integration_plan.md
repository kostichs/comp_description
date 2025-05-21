# План интеграции HubSpot с pipeline обработки компаний

## Общая схема работы

1. Получаем название компании и веб-сайт из входных данных
2. Проверяем компанию в HubSpot по веб-сайту (используем URL как идентификатор)
3. Если компания найдена в HubSpot:
   - Проверяем возраст описания (поле timestamp)
   - Если описание свежее (менее 6 месяцев) — используем описание из HubSpot
   - Если описание устарело — запускаем стандартный пайплайн обработки
4. Если компания не найдена в HubSpot — запускаем стандартный пайплайн обработки

## Шаги реализации

### 1. Создание клиента для работы с HubSpot API

- [ ] Создать файл `hubspot_client.py` в корне проекта
- [ ] Реализовать класс `HubSpotClient` с методами:
  ```python
  import requests
  import datetime
  from typing import Dict, Optional, List, Tuple
  
  class HubSpotClient:
      def __init__(self, api_key: str, base_url: str = "https://api.hubapi.com"):
          self.api_key = api_key
          self.base_url = base_url
          self.headers = {
              "Authorization": f"Bearer {api_key}",
              "Content-Type": "application/json"
          }
          self._cache = {}  # Кэш для избежания повторных запросов
      
      async def search_company_by_website(self, website: str) -> Optional[Dict]:
          """Поиск компании по веб-сайту"""
          # Нормализация URL (удаление http://, https://, www., конечных слешей)
          normalized_website = self._normalize_website(website)
          
          # Проверяем кэш
          if normalized_website in self._cache:
              return self._cache[normalized_website]
          
          endpoint = f"{self.base_url}/crm/v3/objects/companies/search"
          payload = {
              "filterGroups": [{
                  "filters": [{
                      "propertyName": "website",
                      "operator": "CONTAINS_TOKEN",
                      "value": normalized_website
                  }]
              }],
              "properties": ["name", "website", "description", "description_timestamp", "linkedin_url"],
              "limit": 1
          }
          
          response = requests.post(endpoint, headers=self.headers, json=payload)
          if response.status_code == 200:
              results = response.json().get("results", [])
              if results:
                  self._cache[normalized_website] = results[0]  # Сохраняем в кэш
                  return results[0]
          
          self._cache[normalized_website] = None  # Кэшируем отрицательный результат
          return None
      
      def _normalize_website(self, website: str) -> str:
          """Нормализация веб-сайта для сравнения"""
          if not website:
              return ""
              
          website = website.lower()
          for prefix in ["https://", "http://", "www."]:
              if website.startswith(prefix):
                  website = website[len(prefix):]
          if website.endswith("/"):
              website = website[:-1]
          return website
      
      def is_description_fresh(self, timestamp_str: str, max_age_months: int = 6) -> bool:
          """Проверка свежести описания (меньше max_age_months)"""
          try:
              timestamp = datetime.datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
              now = datetime.datetime.now(datetime.timezone.utc)
              age = now - timestamp
              return age.days < max_age_months * 30  # примерно 30 дней в месяце
          except Exception:
              return False  # При ошибке считаем описание устаревшим
  ```

### 2. Модификация файла окружения (.env)

- [ ] Добавить переменную окружения для HubSpot API ключа:
  ```
  HUBSPOT_API_KEY=ваш_ключ_hubspot_api
  ```

- [ ] Обновить `src/config.py` для загрузки HubSpot API ключа:
  ```python
  def load_env_vars():
      # ...существующий код...
      
      hubspot_api_key = os.getenv("HUBSPOT_API_KEY")
      
      return scrapingbee_api_key, openai_api_key, serper_api_key, hubspot_api_key
  ```

### 3. Модификация pipeline_adapter.py

- [ ] Добавить импорт HubSpot клиента:
  ```python
  from hubspot_client import HubSpotClient
  ```

- [ ] Обновить функцию `run_pipeline_for_file` для принятия параметра HubSpot API ключа:
  ```python
  async def run_pipeline_for_file(
      # ...существующие параметры...
      hubspot_api_key: Optional[str] = None,
      use_hubspot_integration: bool = True,
      # ...
  ):
      # Инициализация HubSpot клиента, если предоставлен API ключ и интеграция включена
      hubspot_client = None
      if hubspot_api_key and use_hubspot_integration:
          hubspot_client = HubSpotClient(hubspot_api_key)
          logger.info(f"HubSpot client initialized. Integration enabled: {use_hubspot_integration}")
      
      # ...существующий код...
      
      # Передаем HubSpot клиента в process_companies
      results = await process_companies(
          # ...существующие параметры...
          hubspot_client=hubspot_client,
          # ...
      )
  ```

- [ ] Обновить функцию `process_companies` для принятия HubSpot клиента:
  ```python
  async def process_companies(
      # ...существующие параметры...
      hubspot_client: Optional[HubSpotClient] = None,
      # ...
  ):
      # ...существующий код...
      
      for i in range(0, total_companies_count, batch_size):
          # ...
          for j, company_name_in_batch in enumerate(batch_company_names):
              # ...
              task = asyncio.create_task(
                  _process_single_company_async(
                      # ...существующие параметры...
                      hubspot_client=hubspot_client,
                      # ...
                  )
              )
              # ...
  ```

### 4. Модификация функции _process_single_company_async

- [ ] Добавить параметр HubSpot клиента:
  ```python
  async def _process_single_company_async(
      # ...существующие параметры...
      hubspot_client: Optional[HubSpotClient] = None,
      # ...
  ):
  ```

- [ ] Добавить логику проверки компании в HubSpot после того, как определен `final_homepage_url`:
  ```python
  # Проверка в HubSpot по URL (если есть URL и HubSpot клиент)
  hubspot_data = None
  hubspot_used = False
  
  # Добавить лог для отладки
  if hubspot_client:
      logger.info(f"Will check HubSpot for {company_name}")
  else:
      logger.info(f"HubSpot integration not enabled or no client available for {company_name}")
      
  if hubspot_client and final_homepage_url:
      try:
          logger.info(f"Checking {company_name} website {final_homepage_url} in HubSpot")
          hubspot_data = await hubspot_client.search_company_by_website(final_homepage_url)
          
          if hubspot_data:
              logger.info(f"Found company {company_name} in HubSpot: {hubspot_data.get('properties', {}).get('name')}")
              
              # Проверка свежести описания
              hubspot_description = hubspot_data.get("properties", {}).get("description")
              hubspot_timestamp = hubspot_data.get("properties", {}).get("description_timestamp")
              hubspot_linkedin = hubspot_data.get("properties", {}).get("linkedin_url")
              
              logger.info(f"HubSpot data found: description_length={len(hubspot_description) if hubspot_description else 0}, timestamp={hubspot_timestamp}")
              
              if hubspot_description and hubspot_timestamp:
                  is_fresh = hubspot_client.is_description_fresh(hubspot_timestamp)
                  logger.info(f"HubSpot description for {company_name} is {'fresh' if is_fresh else 'outdated'}")
                  
                  if is_fresh:
                      # Используем данные из HubSpot
                      description = hubspot_description
                      # Для CSV используем дату из HubSpot, но в более читабельном формате
                      try:
                          timestamp = datetime.datetime.fromisoformat(hubspot_timestamp.replace("Z", "+00:00"))
                          formatted_timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                      except:
                          formatted_timestamp = hubspot_timestamp
                          
                      # Не используем structured_data, так как берем готовое описание
                      structured_data = None
                      
                      logger.info(f"Using HubSpot description for {company_name}")
                      hubspot_used = True
                      
                      # Добавляем отметку в результат, что данные из HubSpot
                      result = {
                          "Company_Name": company_name,
                          "Official_Website": final_homepage_url or "Not found",
                          "LinkedIn_URL": hubspot_linkedin or linkedin_url_result or "Not found",
                          "Description": description,
                          "Timestamp": formatted_timestamp,
                          "Data_Source": "HubSpot",  # Дополнительное поле, указывающее источник данных
                          "structured_data": None
                      }
                      
                      # Сохраняем результат в CSV
                      if output_csv_path:
                          file_exists = os.path.exists(output_csv_path)
                          try:
                              # Дополняем csv_fields полем Data_Source, если его там еще нет
                              extended_csv_fields = list(csv_fields)
                              if "Data_Source" not in extended_csv_fields:
                                  extended_csv_fields.append("Data_Source")
                                  
                              csv_row = {key: result.get(key) for key in extended_csv_fields if key in result}
                              save_results_csv([csv_row], output_csv_path, extended_csv_fields, append_mode=file_exists)
                              logger.info(f"Saved HubSpot data for {company_name} to {output_csv_path}")
                          except Exception as e:
                              logger.error(f"Error saving CSV for {company_name}: {e}", exc_info=True)
                      
                      if broadcast_update:
                          await broadcast_update({
                              "type": "company_completed", 
                              "company": company_name,
                              "current": company_index + 1,
                              "total": total_companies,
                              "status": "completed_from_hubspot",
                              "result": result
                          })
                      
                      return result
              
              # Если описание устарело или отсутствует, продолжаем обычный процесс
              logger.info(f"HubSpot description for {company_name} is not available or outdated, processing normally")
          else:
              logger.info(f"Company {company_name} not found in HubSpot")
      except Exception as e:
          logger.error(f"Error checking HubSpot for {company_name}: {e}", exc_info=True)
  
  # Продолжаем обычный процесс обработки, если компании нет в HubSpot 
  # или описание устарело, или произошла ошибка
  ```

- [ ] Обновить секцию финального сохранения результата, чтобы включить поле `Data_Source`:
  ```python
  # Результат обработки компании
  result = {
      "Company_Name": company_name,
      "Official_Website": final_homepage_url or "Not found",
      "LinkedIn_URL": linkedin_url_result or "Not found",
      "Description": description,
      "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
      "Data_Source": "Pipeline",  # Указываем, что данные получены через стандартный пайплайн
      "structured_data": structured_data
  }
  ```

### 5. Обновление функции backend/main.py

- [ ] Обновить функцию `execute_pipeline_for_session_async` для передачи HubSpot API ключа:
  ```python
  async def execute_pipeline_for_session_async(
      # ...существующие параметры...
  ):
      try:
          # ...
          env_vars = load_env_vars()
          scrapingbee_api_key = env_vars[0] 
          openai_api_key = env_vars[1]
          serper_api_key = env_vars[2]
          hubspot_api_key = env_vars[3] if len(env_vars) > 3 else os.getenv("HUBSPOT_API_KEY")
          # ...
      except Exception as e_env:
          # ...
      
      # ...
      
      await run_pipeline_for_file( 
          # ...существующие параметры...
          hubspot_api_key=hubspot_api_key,
          use_hubspot_integration=True,  # Можно сделать параметром из формы
          # ...
      )
  ```

- [ ] Обновить функцию обработки формы для принятия флага использования HubSpot:
  ```python
  @app.post("/api/sessions", tags=["Sessions"], summary="Create a new processing session")
  async def create_new_session(
      file: UploadFile = File(...), 
      context_text: Optional[str] = Form(None), 
      run_standard_pipeline: bool = Form(True),
      run_llm_deep_search_pipeline: bool = Form(True),
      use_hubspot_integration: bool = Form(True)
  ):
      # ...
      # Сохраняем параметр в метаданных сессии
      session_metadata = {
          # ...
          "use_hubspot_integration": use_hubspot_integration,
          # ...
      }
      # ...
  ```

### 6. Обновление форм пользовательского интерфейса (frontend)

- [ ] Добавить чекбокс в `frontend/index.html` для включения/отключения интеграции с HubSpot:
  ```html
  <!-- Добавить в форму загрузки файла -->
  <div class="form-group">
      <label>
          <input type="checkbox" name="use_hubspot_integration" checked>
          Использовать интеграцию с HubSpot (проверять существующие описания)
      </label>
  </div>
  ```

- [ ] Обновить JavaScript в `frontend/app.js` для передачи параметра при отправке формы:
  ```javascript
  // В функции, которая обрабатывает отправку формы
  const formData = new FormData(uploadForm);
  formData.append('use_hubspot_integration', document.querySelector('input[name="use_hubspot_integration"]').checked);
  ```

### 7. Обновление Dockerfile

- [ ] Обновить Dockerfile, чтобы скопировать новый файл клиента HubSpot:
  ```dockerfile
  # ...существующие инструкции...
  
  # Копируем клиент HubSpot
  COPY hubspot_client.py /app/hubspot_client.py
  
  # ...остальные инструкции...
  ```

### 8. Тестирование и отладка

- [ ] Создать тестовый API ключ HubSpot
- [ ] Запустить приложение локально с включенной интеграцией
- [ ] Проверить логи на наличие сообщений о подключении к HubSpot
- [ ] Протестировать обработку компаний, которые:
  - [ ] Существуют в HubSpot с свежим описанием
  - [ ] Существуют в HubSpot с устаревшим описанием
  - [ ] Не существуют в HubSpot

### 9. Документация и оптимизация

- [ ] Добавить комментарии к новому коду
- [ ] Создать или обновить документацию по установке и настройке
- [ ] Оптимизировать запросы к HubSpot API (кеширование, пакетная обработка)
- [ ] Добавить обработку ошибок и ретраи для API запросов

## Дополнительные улучшения (опционально)

- [ ] Синхронизация новых данных обратно в HubSpot после обработки
- [ ] Добавление UI для просмотра статуса интеграции с HubSpot
- [ ] Логирование статистики использования данных из HubSpot vs. генерируемых данных
- [ ] Создание отдельного модуля для работы с CRM системами с возможностью расширения 

# План интеграции пайплайна с HubSpot

## 1. Подготовка проекта и структуры

- [ ] **Создать структуру каталогов для интеграции с HubSpot**
  ```bash
  mkdir -p hubspot_integration
  touch hubspot_integration/__init__.py
  touch hubspot_integration/client.py
  touch hubspot_integration/models.py
  touch hubspot_integration/service.py
  touch hubspot_integration/config.py
  touch hubspot_integration/utils.py
  touch hubspot_pipeline_adapter.py
  ```

- [ ] **Настроить переменные окружения для API HubSpot**
  - [ ] Добавить в `.env` файл (или создать, если отсутствует):
    ```
    HUBSPOT_API_KEY=your_api_key_here
    HUBSPOT_BASE_URL=https://api.hubapi.com
    ```
  - [ ] Обеспечить загрузку переменных окружения в приложении:
    ```python
    # В config.py или другом файле конфигурации
    import os
    from dotenv import load_dotenv

    load_dotenv()
    
    HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")
    HUBSPOT_BASE_URL = os.getenv("HUBSPOT_BASE_URL", "https://api.hubapi.com")
    ```

## 2. Реализация клиента для API HubSpot

- [ ] **Создать базовый класс для работы с API HubSpot в `client.py`**
  - [ ] Реализовать методы для аутентификации
  - [ ] Добавить обработку ошибок и повторные попытки при сбоях
  - [ ] Настроить HTTP-клиент с таймаутами и логированием

- [ ] **Реализовать методы для работы с компаниями:**
  - [ ] `find_company_by_domain(domain)` - поиск компании по домену
  - [ ] `get_company_by_id(company_id)` - получение данных компании по ID
  - [ ] `update_company_properties(company_id, properties)` - обновление свойств компании
  - [ ] `create_company(properties)` - создание новой компании

- [ ] **Реализовать кэширование для снижения нагрузки на API**
  - [ ] Настроить временное кэширование результатов поиска
  - [ ] Добавить опцию для принудительного обновления кэша

## 3. Моделирование данных и бизнес-логика

- [ ] **Создать модели данных в `models.py`**
  - [ ] Определить класс `HubSpotCompany` с необходимыми полями
  - [ ] Реализовать методы сериализации/десериализации для API HubSpot

- [ ] **Реализовать сервисный слой в `service.py`**
  - [ ] Создать класс `HubSpotIntegrationService` с основными методами:
    - [ ] `should_process_company(domain)` - проверка необходимости обработки компании
    - [ ] `save_company_description(domain, company_name, description)` - сохранение описания компании
    - [ ] `get_last_update_timestamp(domain)` - получение времени последнего обновления

- [ ] **Добавить бизнес-логику для определения необходимости обработки:**
  - [ ] Проверка существования компании в HubSpot
  - [ ] Проверка времени последнего обновления описания
  - [ ] Проверка других условий (например, флаг "требуется обновление")

## 4. Интеграция с существующим пайплайном

- [ ] **Создать адаптер пайплайна для HubSpot в `hubspot_pipeline_adapter.py`**
  - [ ] Наследоваться от существующего класса пайплайна
  - [ ] Переопределить необходимые методы для интеграции с HubSpot

- [ ] **Модифицировать процесс обработки компании:**
  - [ ] Добавить проверку компании в HubSpot перед обработкой
  - [ ] Включить сохранение результатов в HubSpot после успешной обработки
  - [ ] Добавить обработку ошибок и повторные попытки

- [ ] **Реализовать обновление свойств компании в HubSpot:**
  - [ ] Обновление свойства `ai_description` значением описания компании
  - [ ] Обновление свойства `ai_description_updated` текущим временем
  - [ ] Добавление дополнительных метаданных (источник данных, версия модели и т.д.)

## 5. Улучшение обработки входных данных

- [ ] **Расширить функцию загрузки данных для поддержки различных форматов:**
  - [ ] Добавить поддержку CSV с произвольным разделителем
  - [ ] Добавить поддержку Excel-файлов
  - [ ] Реализовать валидацию входных данных

- [ ] **Улучшить логику определения доменов компаний:**
  - [ ] Добавить нормализацию URL (удаление www, протокола, пути)
  - [ ] Реализовать проверку действительности домена
  - [ ] Добавить извлечение домена из URL, если он указан в полном формате

## 6. Оптимизация производительности

- [ ] **Реализовать асинхронную обработку запросов к HubSpot:**
  - [ ] Использовать асинхронный HTTP-клиент
  - [ ] Ограничить количество одновременных запросов

- [ ] **Добавить пакетную обработку для больших наборов данных:**
  - [ ] Реализовать обработку компаний пакетами
  - [ ] Добавить отчет о прогрессе обработки
  - [ ] Реализовать возможность возобновления обработки с точки прерывания

- [ ] **Оптимизировать использование API HubSpot:**
  - [ ] Минимизировать количество запросов (объединение запросов, кэширование)
  - [ ] Добавить учет ограничений API (rate limiting)
  - [ ] Реализовать экспоненциальную задержку при повторных попытках

## 7. Создание точки входа и настройка конфигурации

- [ ] **Создать исполняемый скрипт для запуска интеграции:**
  ```python
  # hubspot_pipeline_runner.py
  
  import asyncio
  from hubspot_integration.service import HubSpotIntegrationService
  from hubspot_pipeline_adapter import HubSpotPipelineAdapter
  
  async def main():
      # Инициализация сервиса HubSpot
      hubspot_service = HubSpotIntegrationService()
      
      # Создание адаптера пайплайна
      pipeline = HubSpotPipelineAdapter(hubspot_service=hubspot_service)
      
      # Запуск обработки
      await pipeline.run_pipeline_for_file(
          input_file_path="input_companies.csv",
          output_csv_path="output_results.csv",
          company_col_index=0,  # Колонка с названием компании
          # другие параметры...
      )
  
  if __name__ == "__main__":
      asyncio.run(main())
  ```

- [ ] **Создать файл конфигурации для настройки интеграции:**
  ```yaml
  # hubspot_config.yaml
  
  hubspot:
    # Настройки API
    api_retry_attempts: 3
    api_timeout_seconds: 30
    
    # Настройки обработки компаний
    update_interval_days: 7  # Обновлять описание не чаще раз в 7 дней
    force_update: false      # Принудительное обновление всех компаний
    
    # Свойства HubSpot
    description_property: "ai_description"
    update_timestamp_property: "ai_description_updated"
  ```

## 8. Тестирование и отладка

- [ ] **Создать модульные тесты для компонентов интеграции:**
  - [ ] Тесты для клиента HubSpot (с моками API)
  - [ ] Тесты для сервисного слоя
  - [ ] Тесты для адаптера пайплайна

- [ ] **Реализовать интеграционные тесты:**
  - [ ] Тест для полного процесса обработки компании
  - [ ] Тест для обработки пакета компаний

- [ ] **Добавить функциональность для отладки:**
  - [ ] Включить подробное логирование
  - [ ] Добавить режим имитации (без фактического обновления данных)
  - [ ] Создать инструменты для визуализации обработки

## 9. Документация и инструкции

- [ ] **Создать README.md с описанием интеграции:**
  - [ ] Общее описание и архитектура
  - [ ] Инструкции по установке и настройке
  - [ ] Примеры использования

- [ ] **Добавить комментарии к коду для автогенерации документации**

- [ ] **Создать инструкцию по устранению неполадок**

## 10. Расширение функциональности

- [ ] **Расширить функциональность для работы с другими объектами HubSpot:**
  - [ ] Интеграция с контактами
  - [ ] Интеграция с сделками

- [ ] **Добавить возможность двунаправленной синхронизации:**
  - [ ] Загрузка данных из HubSpot для обработки
  - [ ] Создание задач по обновлению описаний на основе событий в HubSpot

- [ ] **Рассмотреть возможности для автоматизации:**
  - [ ] Интеграция с workflow HubSpot
  - [ ] Настройка периодического запуска обработки 