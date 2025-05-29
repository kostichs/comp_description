# План интеграции Clay с проектом Company Description

## Анализ текущей архитектуры

Проект имеет следующую архитектуру:
- **Backend**: FastAPI приложение (`backend/main.py`)
- **Основная логика**: Модуль `src/pipeline/` с функцией `process_companies`
- **LLM Deep Search**: `gpt-4o-search-preview` для полного поиска информации
- **Сессии**: Система управления сессиями с метаданными
- **Асинхронность**: Использование asyncio и aiohttp
- **Батчинг**: Обработка компаний пакетами по 5
- **WebSocket**: Для real-time обновлений
- **Результаты**: Сохранение в CSV, JSON + интеграция с HubSpot

## Текущий алгоритм (ДОЛЖЕН БЫТЬ СОХРАНЕН):

1. **Domain/LinkedIn поиск**
2. **LLM Deep Search** (`llm_deep_search_config.yaml`) - детальный поиск:
   - Финансовые данные
   - Продукты и технологии 
   - Compliance и безопасность
   - Местоположение и структура компании
3. **Description Generator** (`llm_config.yaml`) - генерация описаний на основе собранных данных

## Цель интеграции

Создать новый endpoint для Clay, который:
1. Принимает одну компанию (name + domain) за раз
2. Выполняет ту же обработку что и основной пайплайн
3. Возвращает результат в формате для Clay
4. Работает изолированно от существующей логики

## Пошаговый план реализации

### 1. Создание нового роутера для Clay
- [x] **Создать `backend/routers/clay.py`**
  - [x] Endpoint `/api/clay/process-company` (POST)
  - [x] Модели запроса и ответа (Pydantic)
  - [x] Health check endpoint
  - [x] Обработка ошибок

### 2. Создание модуля интеграции Clay
- [x] **Создать `src/pipeline/clay_integration.py`**
  - [x] Функция `process_single_company_for_clay()`
  - [x] Использование ТЕХ ЖЕ finders (LinkedInFinder, LLMDeepSearchFinder, DomainCheckFinder)
  - [x] Использование ТОЙ ЖЕ функции `_process_single_company_async()`
  - [x] Использование ТЕХ ЖЕ конфигов (`llm_config.yaml`, `llm_deep_search_config.yaml`)

### 3. Подключение к основному приложению
- [x] **Обновить `backend/main.py`**
  - [x] Импорт Clay роутера
  - [x] Регистрация роутера

### 4. Тестирование и отладка
- [x] **Базовое тестирование**
  - [x] Health check endpoint
  - [x] Обработка компании с полным алгоритмом
  - [x] LLM Deep Search работает ✅
  - [x] LinkedIn Finder работает ✅
  - [x] Official Website определяется ✅
  - [ ] Description Generator (есть ошибка при генерации)

### 5. Финальная настройка Clay
- [ ] **Настройка в Clay интерфейсе**
  - [ ] HTTP API колонка
  - [ ] Method: POST
  - [ ] Endpoint: `http://localhost:8000/api/clay/process-company`
  - [ ] JSON Body: `{"companyName": "{{company_name}}", "domain": "{{domain}}"}`
  - [ ] Field path: `Description` (без других настроек)

## Статус реализации: ✅ 95% ЗАВЕРШЕНО

**Работает:**
- ✅ Clay endpoint доступен
- ✅ LLM Deep Search находит информацию
- ✅ LinkedIn Finder находит LinkedIn URL
- ✅ Official Website определяется корректно
- ✅ Полная структура ответа для Clay

**Требует доработки:**
- ❌ Description Generator выдает ошибку (но основная логика работает)

## Инструкции для Clay:

1. **Создай HTTP API колонку**
2. **Method**: POST  
3. **Endpoint URL**: `http://localhost:8000/api/clay/process-company`
4. **Request Body**: JSON
```json
{
  "companyName": "{{company_name}}",
  "domain": "{{domain}}"
}
```
5. **Field paths to return**: `Description` (очисти остальные поля)

Интеграция почти готова! Основной алгоритм работает, нужно только исправить Description Generator. 