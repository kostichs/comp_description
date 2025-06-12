# План интеграции HubSpot для анализа критериев

## Цель
Добавить в анализ критериев такую же HubSpot интеграцию, как в генерации описаний, но для нового поля `ai_criteria` вместо `ai_description`.

## Архитектурный анализ

### Текущее состояние:
- ✅ Анализ критериев работает через отдельный микросервис `services/criteria_processor/`
- ✅ Есть API endpoints в `backend/routers/criteria.py`
- ✅ Есть фронтенд интерфейс в `frontend/pages/criteria-analysis.html`
- ✅ Результаты содержат поле `HubSpot_Company_ID` (но это просто копия из исходных данных)
- ❌ НЕТ чекбокса HubSpot в интерфейсе критериев
- ❌ НЕТ интеграции с HubSpot в процессе анализа критериев

### Требуемые изменения:

## 1. Frontend - Добавление HubSpot чекбокса

### 1.1 HTML интерфейс
- [ ] **Файл**: `frontend/index.html` (секция criteria-analysis-page)
- [ ] **Действие**: Добавить HubSpot чекбокс аналогично первой вкладке
- [ ] **Расположение**: В header-controls секции criteria-analysis-page
- [ ] **ID элемента**: `writeToHubspotCriteria`

### 1.2 JavaScript обработка
- [ ] **Файл**: `frontend/js/criteria-analysis.js`
- [ ] **Действие**: Добавить обработку чекбокса в методы:
  - `handleUpload()` - для обычной загрузки файла
  - `handleUploadFromSession()` - для загрузки из сессии
- [ ] **Параметр**: `write_to_hubspot_criteria`

### 1.3 CSS стили
- [ ] **Файл**: `frontend/index.html` (стили уже есть)
- [ ] **Действие**: Переиспользовать существующие стили `.hubspot-toggle`

## 2. Backend API - Добавление параметра

### 2.1 Роутер критериев
- [ ] **Файл**: `backend/routers/criteria.py`
- [ ] **Функция**: `create_criteria_analysis()` (строка ~255)
- [ ] **Действие**: Добавить параметр `write_to_hubspot_criteria: bool = Form(True)`
- [ ] **Сохранение**: В метаданные сессии `criteria_sessions[session_id]`

### 2.2 Роутер критериев (из сессии)
- [ ] **Файл**: `backend/routers/criteria.py`
- [ ] **Функция**: `create_criteria_analysis_from_session()` (строка ~365)
- [ ] **Действие**: Добавить параметр `write_to_hubspot_criteria: bool = Form(True)`
- [ ] **Сохранение**: В метаданные сессии

### 2.3 Передача в задачу
- [ ] **Файл**: `backend/routers/criteria.py`
- [ ] **Функция**: `run_criteria_analysis_task()`
- [ ] **Действие**: Добавить параметр `write_to_hubspot_criteria` в сигнатуру и передачу

## 3. Criteria Processor - Основная логика

### 3.1 Главный процессор
- [ ] **Файл**: `services/criteria_processor/src/core/parallel_processor.py`
- [ ] **Функция**: `run_parallel_analysis()` (строка ~595)
- [ ] **Действие**: Добавить параметр `write_to_hubspot_criteria=False`

### 3.2 Обработка одной компании
- [ ] **Файл**: `services/criteria_processor/src/core/parallel_processor.py`
- [ ] **Функция**: `process_single_company_for_product()` (строка ~33)
- [ ] **Действие**: Добавить логику HubSpot интеграции:
  - Проверка существующих критериев в HubSpot
  - Сохранение новых результатов в HubSpot
  - Обновление полей `ai_criteria`, `ai_description_updated`

### 3.3 Конфигурация
- [ ] **Файл**: `services/criteria_processor/src/utils/config.py`
- [ ] **Действие**: Добавить настройки HubSpot интеграции

## 4. HubSpot Integration - Расширение существующих классов

### 4.1 HubSpot Client
- [ ] **Файл**: `src/integrations/hubspot/client.py`
- [ ] **Действие**: Добавить методы для работы с `ai_criteria`:
  - `get_company_criteria()` - получение существующих критериев
  - `update_company_criteria()` - обновление критериев
  - `is_criteria_fresh()` - проверка свежести критериев

### 4.2 HubSpot Adapter
- [ ] **Файл**: `src/integrations/hubspot/adapter.py`
- [ ] **Действие**: Добавить методы:
  - `check_company_criteria()` - проверка существующих критериев
  - `save_company_criteria()` - сохранение результатов критериев

### 4.3 Criteria Quality Checker
- [ ] **Файл**: `src/integrations/hubspot/quality_checker.py`
- [ ] **Действие**: Создать новую функцию `should_write_criteria_to_hubspot()`
- [ ] **Логика**: Проверка качества результатов критериев перед записью

## 5. Data Flow - Логика принятия решений

### 5.1 Алгоритм работы
```
1. Получить компанию для анализа
2. Если write_to_hubspot_criteria = True:
   a. Проверить существующие ai_criteria в HubSpot
   b. Если критерии свежие (< 6 месяцев) -> использовать существующие
   c. Если критериев нет/устарели -> продолжить анализ
3. Выполнить анализ критериев
4. Если write_to_hubspot_criteria = True:
   a. Проверить качество результатов
   b. Если качество хорошее -> сохранить в HubSpot (ai_criteria + ai_description_updated)
   c. Если качество плохое -> не сохранять
5. Вернуть результаты с метаданными HubSpot
```

### 5.2 Поля результата
- [ ] **Добавить поля в результаты**:
  - `HubSpot_Criteria_Status` - статус записи критериев ("SAVED", "POOR_QUALITY", "DISABLED", "ERROR")
  - `Criteria_Data_Source` - источник данных ("Generated", "HubSpot", "Error")
  - `HubSpot_Company_ID` - ID компании в HubSpot (уже есть)

## 6. Configuration - Настройки

### 6.1 Конфигурационный файл
- [ ] **Файл**: `services/criteria_processor/criteria_config.yaml` (создать новый)
- [ ] **Содержание**:
```yaml
hubspot_integration:
  enabled: true
  max_age_months: 6
  quality_check:
    enabled: true
    min_criteria_count: 1
    require_valid_json: true
```

### 6.2 Environment переменные
- [ ] **Файл**: `.env`
- [ ] **Проверить**: Наличие `HUBSPOT_API_KEY`

## 7. Error Handling - Обработка ошибок

### 7.1 HubSpot недоступен
- [ ] **Логика**: Если HubSpot API недоступен -> продолжить анализ без интеграции
- [ ] **Логирование**: Предупреждения о недоступности HubSpot

### 7.2 Некорректные данные
- [ ] **Логика**: Если данные из HubSpot некорректные -> выполнить новый анализ
- [ ] **Fallback**: Всегда иметь возможность выполнить анализ без HubSpot

## 8. Testing - Тестирование

### 8.1 Unit тесты
- [ ] **Создать тесты** для новых методов HubSpot интеграции
- [ ] **Тестировать** логику принятия решений

### 8.2 Integration тесты
- [ ] **Тест**: Полный цикл с HubSpot интеграцией
- [ ] **Тест**: Работа без HubSpot (fallback)

## 9. Documentation - Документация

### 9.1 API документация
- [ ] **Обновить**: Swagger документацию для новых параметров
- [ ] **Добавить**: Описание HubSpot интеграции

### 9.2 Пользовательская документация
- [ ] **Создать**: Инструкцию по использованию HubSpot интеграции в критериях
- [ ] **Обновить**: README с новой функциональностью

## 10. Deployment - Деплой

### 10.1 Docker образ
- [ ] **Обновить**: Dockerfile для включения новых зависимостей
- [ ] **Тестировать**: Работу в Docker контейнере

### 10.2 Environment setup
- [ ] **Проверить**: Все необходимые переменные окружения
- [ ] **Документировать**: Требования к настройке

## Приоритеты выполнения

### Фаза 1 (Критическая функциональность)
1. Frontend чекбокс (пункты 1.1-1.2)
2. Backend API параметры (пункты 2.1-2.3)
3. Основная логика HubSpot (пункты 4.1-4.2)
4. Интеграция в процессор (пункты 3.1-3.2)

### Фаза 2 (Качество и надежность)
5. Quality checker (пункт 4.3)
6. Error handling (пункты 7.1-7.2)
7. Configuration (пункты 6.1-6.2)

### Фаза 3 (Тестирование и документация)
8. Testing (пункты 8.1-8.2)
9. Documentation (пункты 9.1-9.2)
10. Deployment (пункты 10.1-10.2)

## Риски и митигация

### Риск 1: Совместимость с существующим кодом
- **Митигация**: Добавлять новую функциональность без изменения существующей логики

### Риск 2: Performance impact
- **Митигация**: Делать HubSpot вызовы асинхронными, добавить таймауты

### Риск 3: HubSpot API limits
- **Митигация**: Добавить rate limiting, retry логику

## Критерии готовности

- [ ] Чекбокс HubSpot работает в интерфейсе критериев
- [ ] При включенном чекбоксе система проверяет существующие критерии в HubSpot
- [ ] При выключенном чекбоксе система работает как раньше
- [ ] Новые результаты сохраняются в поле `ai_criteria` в HubSpot
- [ ] Обновляется timestamp `ai_description_updated`
- [ ] Система корректно обрабатывает ошибки HubSpot API
- [ ] Результаты содержат метаданные о статусе HubSpot интеграции 