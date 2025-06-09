# 🛡️ План реализации Circuit Breaker + State Manager для OpenAI API Rate Limiting

## 📋 **Цель проекта**
Решить проблему превышения лимитов OpenAI API в конце обработки (5-й продукт проваливается) путем создания координированной системы управления запросами и сохранения состояния.

---

## 🔍 **Анализ текущей архитектуры**

### **Файлы для изучения ✅ (изучены)**
- [x] `services/criteria_processor/src/external/openai_client.py` - главный API клиент (45 строк)
- [x] `services/criteria_processor/src/core/parallel_processor.py` - параллельная обработка (515 строк)
- [x] `services/criteria_processor/src/criteria/mandatory.py` - sync mandatory проверки (64 строки)
- [x] `services/criteria_processor/src/criteria/nth.py` - sync NTH проверки (68 строк)
- [x] `services/criteria_processor/src/criteria/base.py` - базовые OpenAI запросы (35 строк)
- [x] `services/criteria_processor/src/utils/config.py` - конфигурация (183 строки)
- [x] `services/criteria_processor/src/data/savers.py` - сохранение результатов (78 строк)

### **OpenAI запросы происходят в:**
1. **`src/external/openai_client.py:9`** - функция `get_openai_response()` 
2. **`src/criteria/base.py:19`** - функция `get_structured_response()` (вызывает openai_client)
3. **Используется в:**
   - `src/criteria/mandatory.py:35` - для mandatory критериев  
   - `src/criteria/nth.py:35` - для NTH критериев
   - `src/criteria/general.py:34` - для general критериев
   - `src/criteria/qualification.py:32` - для qualification вопросов

### **Текущий retry механизм** (в `openai_client.py:24-28`):
```python
if "rate_limit" in str(e).lower() and attempt < max_retries - 1:
    wait_time = (2 ** attempt) * 5  # 5, 10, 20 секунд  
    time.sleep(wait_time)
    continue
```

### **Проблема:**
- Множественные потоки делают retry одновременно → еще больше нагрузки
- Нет координации между потоками
- Нет сохранения прогресса при критических ошибках

---

## 🎯 **Компоненты для реализации**

### **1. 🛡️ Global Circuit Breaker**
**Файл:** `services/criteria_processor/src/utils/circuit_breaker.py` *(новый)*

- [ ] **Класс `OpenAICircuitBreaker`:**
  - [ ] Состояния: `CLOSED`, `OPEN`, `HALF_OPEN`
  - [ ] Счетчик ошибок rate limit
  - [ ] Таймер блокировки (например, 2 минуты)
  - [ ] Thread-safe операции для многопоточности
  - [ ] Метод `can_execute()` - проверка можно ли делать запрос
  - [ ] Метод `record_success()` - запись успешного запроса
  - [ ] Метод `record_failure()` - запись ошибки + возможное открытие circuit
  - [ ] Логирование всех переходов состояний

### **2. 💾 Progress State Manager** 
**Файл:** `services/criteria_processor/src/utils/state_manager.py` *(новый)*

- [ ] **Класс `ProcessingStateManager`:**
  - [ ] Сохранение текущего состояния: `{product_index, company_index, audience, stage}`
  - [ ] Формат JSON файла: `session_id_progress.json` в папке `output/session_id/`
  - [ ] Методы:
    - [ ] `save_progress(product_idx, company_idx, audience, stage)` 
    - [ ] `load_progress()` - загрузка последнего состояния
    - [ ] `clear_progress()` - очистка при успешном завершении
    - [ ] `save_partial_results(results)` - сохранение промежуточных результатов
    - [ ] `load_partial_results()` - загрузка уже обработанных данных

### **3. 🔧 Enhanced OpenAI Client**
**Файл:** `services/criteria_processor/src/external/openai_client.py` *(модификация)*

- [ ] **Интеграция с Circuit Breaker:**
  - [ ] Импорт `OpenAICircuitBreaker` 
  - [ ] Глобальный инстанс breaker: `_circuit_breaker = OpenAICircuitBreaker()`
  - [ ] Строка ~10: добавить проверку `if not _circuit_breaker.can_execute(): raise CircuitOpenException`
  - [ ] Строка ~24: заменить простую проверку rate limit на `_circuit_breaker.record_failure(e)`
  - [ ] Строка ~35: добавить `_circuit_breaker.record_success()` при успехе
  - [ ] Добавить обработку `CircuitOpenException` с логированием

### **4. 🔄 Resilient Parallel Processor** 
**Файл:** `services/criteria_processor/src/core/parallel_processor.py` *(модификация)*

#### **Модификация функции `run_parallel_analysis()` (строка 417):**
- [ ] **Добавить State Manager:**
  - [ ] Строка ~430: создать `state_manager = ProcessingStateManager(session_id)`
  - [ ] Проверить есть ли сохраненное состояние: `state_manager.load_progress()`
  - [ ] Если есть → продолжить с сохраненного места
  - [ ] Если нет → начать с начала

- [ ] **Оборачивание цикла продуктов (строка ~480):**
  - [ ] Добавить try/except вокруг цикла продуктов
  - [ ] При `CircuitOpenException` или превышении лимитов:
    - [ ] Сохранить прогресс: `state_manager.save_progress(product_idx, 0, None, "paused")`
    - [ ] Сохранить частичные результаты: `state_manager.save_partial_results(all_results)`
    - [ ] Логировать паузу и время возобновления
    - [ ] Ждать восстановления circuit breaker или завершить с частичными результатами

#### **Модификация функции `process_single_company_for_product()` (строка 32):**
- [ ] **Добавить прогресс-трекинг:**
  - [ ] Параметр: добавить `progress_callback=None`
  - [ ] После каждой successful компании: вызывать `progress_callback(company_name, product, "completed")`
  - [ ] При ошибках: вызывать `progress_callback(company_name, product, "failed", error)`

#### **Модификация функций критериев:**
- [ ] **`check_mandatory_criteria_batch()` (строка 243):**
  - [ ] Оборачивание OpenAI запросов в try/except для `CircuitOpenException`
  - [ ] При circuit open → возвращать специальный результат "CIRCUIT_OPEN" 
  - [ ] Логировать состояние circuit breaker

- [ ] **`check_nth_criteria_batch()` (строка 322):**
  - [ ] Аналогичные изменения как в mandatory
  - [ ] Обработка состояния circuit breaker

### **5. 📊 Recovery & Resume Logic**
**Файл:** `services/criteria_processor/src/core/recovery.py` *(новый)*

- [ ] **Функция `resume_processing(session_id)`:**
  - [ ] Загрузка сохраненного состояния
  - [ ] Загрузка частичных результатов  
  - [ ] Продолжение обработки с сохраненного места
  - [ ] Объединение старых и новых результатов

- [ ] **Функция `validate_partial_results(results)`:**
  - [ ] Проверка целостности данных
  - [ ] Удаление поврежденных записей
  - [ ] Отчет о статусе восстановления

### **6. ⚙️ Configuration Updates**
**Файл:** `services/criteria_processor/src/utils/config.py` *(модификация)*

- [ ] **Добавить секцию CIRCUIT_BREAKER_CONFIG (строка ~180):**
  ```python
  CIRCUIT_BREAKER_CONFIG = {
      'failure_threshold': 5,           # Ошибок для открытия circuit
      'recovery_timeout': 120,          # Секунд до попытки восстановления  
      'success_threshold': 3,           # Успехов для закрытия circuit
      'rate_limit_keywords': ['rate_limit', 'quota_exceeded', 'too_many_requests'],
      'enable_circuit_breaker': True    # Мастер-переключатель
  }
  ```

### **7. 🖥️ CLI Integration**
**Файл:** `services/criteria_processor/main.py` *(модификация)*

- [ ] **Добавить параметры командной строки:**
  - [ ] `--resume-session SESSION_ID` - продолжить прерванную сессию
  - [ ] `--circuit-breaker-enabled` - включить circuit breaker (по умолчанию True)
  - [ ] `--max-rate-limit-failures N` - настройка порога

- [ ] **Логика запуска:**
  - [ ] При `--resume-session`: вызвать `resume_processing(session_id)`
  - [ ] Иначе: обычный `run_parallel_analysis()`

---

## 📅 **План выполнения (поэтапно)**

### **Фаза 1: Core Infrastructure** 
- [ ] Создать `circuit_breaker.py` с классом `OpenAICircuitBreaker`
- [ ] Создать `state_manager.py` с классом `ProcessingStateManager`  
- [ ] Добавить конфигурацию в `config.py`
- [ ] Тестирование базовой функциональности

### **Фаза 2: OpenAI Client Integration**
- [ ] Модифицировать `openai_client.py` для интеграции с circuit breaker
- [ ] Добавить новые исключения и обработку
- [ ] Тестирование с простыми запросами

### **Фаза 3: Parallel Processor Integration** 
- [ ] Модифицировать `run_parallel_analysis()` для использования state manager
- [ ] Добавить прогресс-трекинг в `process_single_company_for_product()`
- [ ] Модифицировать batch функции для circuit breaker
- [ ] Тестирование с несколькими компаниями

### **Фаза 4: Recovery & CLI**
- [ ] Создать `recovery.py` с логикой восстановления
- [ ] Добавить CLI параметры в `main.py`
- [ ] Полное end-to-end тестирование

### **Фаза 5: Testing & Documentation**
- [ ] Создать тесты для rate limiting сценариев
- [ ] Документировать новые функции
- [ ] Финальное тестирование с реальными данными

---

## 🚨 **Критические точки внимания**

### **Thread Safety:**
- Circuit breaker должен быть thread-safe для `ThreadPoolExecutor`
- State manager должен использовать file locking при записи

### **Error Handling:**
- Разделять критические ошибки (network) от rate limit
- Graceful degradation при отказе state manager

### **Performance:**
- Минимальный overhead на каждый OpenAI запрос
- Эффективное сохранение состояния (не после каждого запроса)

### **Data Integrity:**
- Валидация сохраненного состояния при восстановлении
- Защита от дублирования данных при resume

---

## ✅ **Критерии успеха**

1. **Rate Limiting Management:** Circuit breaker предотвращает cascade failures
2. **State Persistence:** Возможность восстановления с любого момента
3. **No Data Loss:** Все обработанные результаты сохраняются 
4. **Performance:** Минимальное влияние на скорость обработки
5. **Reliability:** Стабильная работа при сетевых проблемах

---

## 🎯 **Ожидаемый результат**

После реализации:
- ✅ Нет cascade failures при rate limiting
- ✅ Автоматическое восстановление после пауз  
- ✅ Сохранение всех результатов даже при сбоях
- ✅ Возможность продолжить обработку после перезапуска
- ✅ Стабильная обработка всех 5 продуктов

**Время реализации:** 3-4 часа активной работы
**Сложность:** Средняя-высокая (требует понимания многопоточности и state management) 