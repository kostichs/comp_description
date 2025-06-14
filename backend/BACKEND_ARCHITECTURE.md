# Backend Architecture Documentation

## 📋 Содержание
1. [Обзор архитектуры](#обзор-архитектуры)
2. [Структура проекта](#структура-проекта)
3. [Доменная организация](#доменная-организация)
4. [Сервисы и оркестрация](#сервисы-и-оркестрация)
5. [Добавление новых компонентов](#добавление-новых-компонентов)
6. [Правила разработки](#правила-разработки)
7. [Масштабирование](#масштабирование)
8. [Поддержка и отладка](#поддержка-и-отладка)

---

## 🏗️ Обзор архитектуры

Backend построен по **доменно-ориентированной архитектуре (Domain-Driven Design)** с четким разделением бизнес-логики по алгоритмам и функциональным областям.

### Основные принципы:
- **Разделение по бизнес-доменам** - каждый алгоритм в своей папке
- **Универсальные сервисы** - общие компоненты вынесены в services
- **Модульность** - каждый компонент независим и переиспользуем
- **Единая точка входа** - main.py только для инфраструктуры

---

## 📁 Структура проекта

```
backend/
├── main.py                     # 🚀 Точка входа FastAPI (только инфраструктура)
├── api/                        # 🎯 Бизнес-домены (API endpoints)
│   ├── descriptions/           # 📝 Алгоритм 1: Генерация описаний компаний
│   │   ├── __init__.py
│   │   └── routes.py          # Endpoints для работы с описаниями
│   ├── criteria/              # 🎯 Алгоритм 2: Анализ по критериям
│   │   ├── __init__.py
│   │   └── routes.py          # Endpoints для анализа критериев
│   ├── integrations/          # 🔌 Внешние интеграции
│   │   └── clay/              # Clay API интеграция
│   │       ├── __init__.py
│   │       └── routes.py
│   └── common/                # 🛠️ Общие утилиты (будущее использование)
├── services/                  # ⚙️ Универсальные сервисы
│   ├── __init__.py
│   ├── pipeline_orchestrator.py  # 🎼 Универсальный оркестратор пайплайнов
│   ├── session_manager.py        # 📊 Управление сессиями и метаданными
│   └── config_loader.py          # ⚙️ Загрузка конфигурации и API ключей
└── BACKEND_ARCHITECTURE.md    # 📖 Эта документация
```

---

## 🎯 Доменная организация

### 1. **Descriptions Domain** (`/api/descriptions/`)
**Назначение:** Генерация описаний компаний через AI

**Endpoints:**
- `POST /api/descriptions/` - Создание новой сессии генерации
- `GET /api/descriptions/` - Список всех сессий
- `GET /api/descriptions/{session_id}` - Информация о сессии
- `GET /api/descriptions/{session_id}/results` - Результаты генерации
- `GET /api/descriptions/{session_id}/download_archive` - Скачать архив сессии
- `DELETE /api/descriptions/{session_id}` - Удалить сессию

**Ключевые функции:**
- Загрузка CSV файлов с компаниями
- Запуск AI пайплайна генерации описаний
- Управление статусами сессий
- Создание архивов результатов

### 2. **Criteria Domain** (`/api/criteria/`)
**Назначение:** Анализ компаний по заданным критериям

**Endpoints:**
- `POST /api/criteria/analyze_from_session` - Анализ из существующей сессии
- `GET /api/criteria/sessions/{session_id}/results` - Результаты анализа
- `GET /api/criteria/sessions/{session_id}/download` - Скачать результаты
- `GET /api/criteria/files` - Список файлов критериев
- И другие endpoints для управления критериями

**Ключевые функции:**
- Загрузка и управление файлами критериев
- Запуск анализа компаний по критериям
- Интеграция с существующими сессиями descriptions

### 3. **Integrations Domain** (`/api/integrations/`)
**Назначение:** Внешние интеграции и API

**Clay Integration** (`/api/integrations/clay/`):
- `POST /api/integrations/clay/enrich` - Обогащение данных через Clay
- Другие Clay-специфичные endpoints

---

## ⚙️ Сервисы и оркестрация

### 1. **Pipeline Orchestrator** (`services/pipeline_orchestrator.py`)
**Назначение:** Универсальный оркестратор для запуска любых пайплайнов

**Ключевые функции:**
- `run_session_pipeline(session_id, broadcast_update)` - Главная функция запуска
- Координация между session_manager и config_loader
- Обработка ошибок и статусов
- WebSocket уведомления

**Использование:**
```python
from backend.services import run_session_pipeline

# В любом domain router
await run_session_pipeline(session_id, broadcast_update_callback)
```

### 2. **Session Manager** (`services/session_manager.py`)
**Назначение:** Управление метаданными сессий

**Ключевые функции:**
- Загрузка и сохранение метаданных сессий
- Управление файловыми путями
- Настройка логирования для сессий
- Обновление статусов

### 3. **Config Loader** (`services/config_loader.py`)
**Назначение:** Загрузка конфигурации и инициализация клиентов

**Ключевые функции:**
- Загрузка API ключей из environment
- Инициализация OpenAI и ScrapingBee клиентов
- Загрузка LLM конфигурации из YAML

---

## ➕ Добавление новых компонентов

### 🆕 Добавление нового бизнес-домена

**Шаг 1:** Создайте структуру папок
```bash
mkdir backend/api/new_domain
touch backend/api/new_domain/__init__.py
touch backend/api/new_domain/routes.py
```

**Шаг 2:** Создайте router в `routes.py`
```python
from fastapi import APIRouter

router = APIRouter(prefix="/new_domain", tags=["New Domain"])

@router.post("/")
async def create_new_domain_session():
    """Create new domain session"""
    pass

@router.get("/{session_id}")
async def get_new_domain_session(session_id: str):
    """Get domain session info"""
    pass
```

**Шаг 3:** Экспортируйте router в `__init__.py`
```python
from .routes import router

__all__ = ['router']
```

**Шаг 4:** Зарегистрируйте в `main.py`
```python
from .api.new_domain import router as new_domain_router

app.include_router(new_domain_router, prefix="/api")
```

### 🔧 Добавление нового сервиса

**Шаг 1:** Создайте файл в `services/`
```python
# backend/services/new_service.py
class NewService:
    """Description of the new service"""
    
    def __init__(self):
        pass
    
    async def process_data(self, data):
        """Process data logic"""
        pass
```

**Шаг 2:** Экспортируйте в `services/__init__.py`
```python
from .new_service import NewService

__all__ = ['run_session_pipeline', 'NewService']
```

**Шаг 3:** Используйте в domain routers
```python
from backend.services import NewService

service = NewService()
result = await service.process_data(data)
```

---

## 📋 Правила разработки

### ❌ ЗАПРЕЩЕНО:

1. **Добавлять бизнес-логику в `main.py`**
   - main.py только для инфраструктуры и регистрации роутеров

2. **Создавать endpoints вне доменных папок**
   - Все endpoints должны быть в соответствующих domain папках

3. **Дублировать функциональность между доменами**
   - Общую логику выносить в services

4. **Хардкодить пути и конфигурацию**
   - Использовать config_loader для всех настроек

5. **Создавать монолитные файлы >300 строк**
   - Разбивать на модули при превышении лимита

### ✅ ОБЯЗАТЕЛЬНО:

1. **Следовать доменной структуре**
   - Каждый алгоритм в своей папке api/

2. **Использовать универсальные сервисы**
   - Переиспользовать pipeline_orchestrator для новых пайплайнов

3. **Документировать новые endpoints**
   - Добавлять docstrings и обновлять эту документацию

4. **Тестировать интеграцию**
   - Проверять работу с существующими компонентами

5. **Логировать операции**
   - Использовать session_manager для настройки логирования

---

## 📈 Масштабирование

### Горизонтальное масштабирование доменов

**Когда домен становится большим (>5 endpoints):**

1. **Разбить на под-домены:**
```
api/descriptions/
├── __init__.py
├── sessions/          # Управление сессиями
│   └── routes.py
├── processing/        # Обработка данных
│   └── routes.py
└── results/          # Работа с результатами
    └── routes.py
```

2. **Создать domain-specific сервисы:**
```
services/descriptions/
├── __init__.py
├── session_processor.py
├── data_validator.py
└── result_formatter.py
```

### Добавление новых алгоритмов

**Для каждого нового алгоритма:**

1. Создать папку в `api/algorithm_name/`
2. Использовать `pipeline_orchestrator` для запуска
3. Создать специфичные адаптеры в `src/pipeline/`
4. Обновить frontend для новых endpoints

### Производительность

**Мониторинг:**
- Логи сессий в `output/sessions/*/logs/`
- WebSocket уведомления для real-time статуса
- Метрики через FastAPI middleware

**Оптимизация:**
- Асинхронная обработка через `pipeline_orchestrator`
- Кэширование результатов в session metadata
- Background tasks для длительных операций

---

## 🔧 Поддержка и отладка

### Структура логов

**Логи сессий:** `output/sessions/{session_id}/logs/`
- `session.log` - основной лог сессии
- `pipeline.log` - лог выполнения пайплайна
- `errors.log` - ошибки и исключения

**Системные логи:** Console output
- FastAPI access logs
- Startup/shutdown events
- Router registration

### Типичные проблемы и решения

**1. Ошибка импорта модулей**
```bash
# Очистить кэш Python
Remove-Item -Recurse -Force backend\__pycache__
Remove-Item -Recurse -Force backend\api\__pycache__
```

**2. Неправильные пути к файлам**
- Проверить `PROJECT_ROOT` в `pipeline_orchestrator.py`
- Использовать `Path(__file__).parent` для относительных путей

**3. Проблемы с WebSocket**
- Проверить `broadcast_update` callback в domain routers
- Убедиться что WebSocket endpoint зарегистрирован в main.py

**4. Ошибки конфигурации**
- Проверить `.env` файл с API ключами
- Убедиться что `config_loader` правильно загружает настройки

### Команды для отладки

**Запуск с отладкой:**
```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug
```

**Проверка структуры API:**
```bash
curl http://localhost:8000/docs  # Swagger UI
curl http://localhost:8000/redoc # ReDoc
```

**Проверка статуса сессии:**
```bash
curl http://localhost:8000/api/descriptions/{session_id}
curl http://localhost:8000/api/criteria/sessions/{session_id}/progress
```

---

## 🎯 Заключение

Эта архитектура обеспечивает:
- **Масштабируемость** - легко добавлять новые алгоритмы
- **Поддерживаемость** - четкое разделение ответственности
- **Переиспользование** - универсальные сервисы для всех доменов
- **Читаемость** - понятная структура и документация

**При любых изменениях:**
1. Следуйте доменной структуре
2. Обновляйте эту документацию
3. Тестируйте интеграцию с существующими компонентами
4. Не нарушайте принципы разделения ответственности

**Помните:** Цель архитектуры - упростить разработку и поддержку, а не усложнить. Если что-то кажется слишком сложным - возможно, стоит пересмотреть подход. 