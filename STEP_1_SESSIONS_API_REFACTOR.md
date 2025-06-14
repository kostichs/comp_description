# 🎯 Этап 1: Извлечение Session API из main.py

## 🔍 Приоритет и обоснование

**ПОЧЕМУ НАЧИНАЕМ С ЭТОГО:**
1. **Наименьший риск** - просто перемещение кода без изменения логики
2. **Мгновенный результат** - main.py уменьшится с 736 до ~500 строк  
3. **Изолированность** - Session API не зависит от других компонентов
4. **Легко тестировать** - можем проверить что все работает как раньше

## 📊 Анализ текущего состояния

### Session endpoints в main.py (строки 263-450):
```python
# 6 основных endpoints:
@app.get("/api/sessions")                           # 10 строк
@app.post("/api/sessions")                          # 120 строк ⚠️
@app.post("/api/sessions/{session_id}/start")       # 70 строк  
@app.get("/api/sessions/{session_id}/results")      # 60 строк
@app.get("/api/sessions/{session_id}/logs/{log_type}") # 40 строк
@app.post("/api/sessions/{session_id}/cancel")      # 30 строк
```

**Общий объем: ~330 строк чистого API кода**

### Зависимости которые нужно перенести:
```python
# Импорты (используются только в Session API):
from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR
import pandas as pd
import aiofiles
import shutil
import tempfile

# Глобальные переменные:
active_processing_tasks: Dict[str, asyncio.Task] = {}
```

## ✅ Детальный чеклист выполнения

### Шаг 1: Подготовка структуры (15 мин)

#### 1.1 Создать папки и файлы
```bash
# Выполнить в корне проекта:
mkdir -p backend/api/routes
touch backend/api/__init__.py
touch backend/api/routes/__init__.py
touch backend/api/routes/sessions.py
```

#### 1.2 Создать базовые импорты
**backend/api/__init__.py:**
```python
# Empty for now
```

**backend/api/routes/__init__.py:**
```python
from .sessions import router as sessions_router

__all__ = ["sessions_router"]
```

### Шаг 2: Создание sessions.py роутера (45 мин)

#### 2.1 Базовая структура файла
**backend/api/routes/sessions.py:**
```python
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import PlainTextResponse, FileResponse
from typing import Optional, Dict, List, Any
import asyncio
import logging
import time
import shutil
import tempfile
import aiofiles
import pandas as pd
from pathlib import Path

# Импорты из существующей системы
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR
from backend.processing_runner import run_session_pipeline

# Глобальная переменная для отслеживания активных задач
# TODO: В будущем перенести в TaskService
active_processing_tasks: Dict[str, asyncio.Task] = {}

# Создаем роутер
router = APIRouter(prefix="/api/sessions", tags=["Sessions"])

# Callback функция для завершения задач
def _processing_task_done_callback(task: asyncio.Task, session_id: str):
    """Callback when processing task is done"""
    # TODO: Перенести эту логику в TaskService
    # Копируем логику из main.py
    pass

# Broadcast функция (временная)
async def broadcast_update(data: dict):
    """Temporary broadcast function - TODO: move to WebSocketService"""
    # Заглушка пока не создан WebSocketService
    pass
```

#### 2.2 Перенос первого endpoint (GET /api/sessions)
```python
@router.get("/", summary="List all processing sessions")
async def get_sessions():
    """Retrieves metadata for all recorded processing sessions."""
    try:
        metadata = load_session_metadata()
        # Optional: Sort sessions by timestamp_created descending?
        # metadata.sort(key=lambda s: s.get('timestamp_created', ''), reverse=True)
        return metadata
    except Exception as e:
        logging.error(f"Error loading sessions metadata: {e}")
        raise HTTPException(status_code=500, detail="Failed to load sessions")
```

#### 2.3 Перенос POST /api/sessions (точная копия)
Скопировать всю функцию `create_new_session` из main.py без изменений

#### 2.4 Перенос остальных endpoints
- `start_session_processing`
- `get_session_results`  
- `get_session_log`
- `cancel_processing_session`

### Шаг 3: Интеграция в main.py (20 мин)

#### 3.1 Добавить импорт роутера в main.py
```python
# В начало main.py добавить:
from backend.api.routes.sessions import router as sessions_router

# В раздел где регистрируются роутеры:
app.include_router(sessions_router)
```

#### 3.2 Удалить старые endpoints из main.py
- Удалить все функции от строки 263 до 450
- Сохранить только комментарий где они были

#### 3.3 Перенести глобальные переменные
В sessions.py скопировать:
- `active_processing_tasks`
- `_processing_task_done_callback`

### Шаг 4: Тестирование функциональности (30 мин)

#### 4.1 Запуск сервера
```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

#### 4.2 Проверка endpoints через curl:
```bash
# Проверить список сессий
curl http://localhost:8001/api/sessions

# Проверить создание сессии
curl -X POST "http://localhost:8001/api/sessions" \
  -F "file=@test_companies.csv" \
  -F "context_text=test context" \
  -F "run_llm_deep_search_pipeline=true" \
  -F "write_to_hubspot=false"

# Проверить детали сессии  
curl http://localhost:8001/api/sessions/{session_id}

# Проверить запуск обработки
curl -X POST "http://localhost:8001/api/sessions/{session_id}/start"
```

#### 4.3 Проверка фронтенда
- Открыть http://localhost:8001
- Проверить что все кнопки работают
- Создать новую сессию через UI
- Запустить обработку

### Шаг 5: Очистка и документация (15 мин)

#### 5.1 Очистить imports в main.py
Удалить неиспользуемые импорты после переноса:
```python
# Можно удалить если больше не используются:
from src.data_io import load_session_metadata, save_session_metadata, SESSIONS_DIR
import pandas as pd  # если не используется в других местах
import aiofiles  # если не используется в других местах
```

#### 5.2 Добавить TODO комментарии
```python
# В sessions.py добавить:
# TODO: Refactor _processing_task_done_callback to TaskService
# TODO: Move active_processing_tasks to TaskService  
# TODO: Move broadcast_update to WebSocketService
# TODO: Add proper error handling and logging
# TODO: Extract file operations to FileService
# TODO: Add input validation using Pydantic models
```

#### 5.3 Обновить размеры файлов
Проверить результат:
- `main.py`: было 736 строк → стало ~400 строк ✅
- `sessions.py`: новый файл ~350 строк ✅

## 🧪 Критерии успеха

### Функциональные тесты:
- [ ] GET /api/sessions возвращает список сессий
- [ ] POST /api/sessions создает новую сессию
- [ ] POST /api/sessions/{id}/start запускает обработку
- [ ] POST /api/sessions/{id}/cancel останавливает обработку  
- [ ] GET /api/sessions/{id}/results возвращает результаты
- [ ] GET /api/sessions/{id}/logs/{type} возвращает логи
- [ ] Фронтенд работает без изменений
- [ ] WebSocket уведомления работают

### Технические критерии:
- [ ] main.py уменьшился до ~400 строк
- [ ] Нет дублирования кода
- [ ] Все импорты корректны
- [ ] Сервер запускается без ошибок
- [ ] Логирование работает

### Регрессионные тесты:
- [ ] Создание сессии с файлом CSV
- [ ] Создание сессии с файлом Excel  
- [ ] Загрузка контекста
- [ ] Отмена обработки
- [ ] Скачивание архива сессии

## 🚀 Результат этапа

После выполнения получим:
1. **Изолированный Session API** в отдельном файле
2. **Уменьшенный main.py** (на 45% меньше кода)
3. **Готовую основу** для следующих этапов рефакторинга
4. **Работающую систему** без потери функциональности

## 📝 Примечания

### Что НЕ делаем на этом этапе:
- ❌ Не меняем бизнес-логику
- ❌ Не добавляем dependency injection
- ❌ Не создаем сервисы
- ❌ Не меняем структуру данных
- ❌ Не добавляем тесты (пока)

### Следующий этап будет:
- Извлечение Task management логики
- Создание TaskService
- Рефакторинг WebSocket логики

## ⏱️ Временные затраты
**Общее время: ~2 часа**
- Подготовка: 15 мин
- Создание роутера: 45 мин  
- Интеграция: 20 мин
- Тестирование: 30 мин
- Документация: 15 мин

Этот этап можно выполнить за одну рабочую сессию с минимальными рисками. 