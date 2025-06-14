# 🔧 Детальный план рефакторинга бэкенда Company Canvas

## 📊 Анализ текущего состояния

### Основные проблемы
1. **Монолитный main.py (736 строк)** - смешивание множественных ответственностей
2. **Отсутствие архитектурных слоев** - прямая связь API с бизнес-логикой
3. **Дублирование кода** - повторяющиеся паттерны обработки ошибок
4. **Сложная обработка состояний** - управление активными задачами в main.py
5. **Отсутствие тестируемости** - тесная связанность компонентов

### Анализ файловой структуры

#### `backend/main.py` (736 строк)
**Содержит:**
- Инициализацию FastAPI приложения
- CORS middleware
- Импорты и настройку путей
- WebSocket обработчик
- Управление активными задачами
- 12 API endpoints
- Обработку статических файлов
- Shutdown логику

**Основные функции:**
```python
execute_pipeline_for_session_async()  # 100+ строк
_processing_task_done_callback()      # 50+ строк
create_new_session()                  # 120+ строк
get_session_results()                 # 70+ строк
download_session_archive()            # 80+ строк
```

#### `backend/processing_runner.py` (290 строк) 
**Содержит:**
- Запуск пайплайна обработки
- Инициализацию API клиентов
- Конфигурацию и логирование
- Управление состоянием сессий

#### `backend/routers/` (существующие роутеры)
- `sessions.py` (173 строки)
- `criteria.py` (1302 строки) ⚠️
- `clay.py` (368 строк)

---

## 🏗️ Новая архитектура

### Принципы рефакторинга
1. **Single Responsibility Principle** - каждый модуль имеет одну ответственность
2. **Dependency Injection** - слабая связанность компонентов
3. **Layered Architecture** - четкое разделение слоев
4. **Error Handling Consistency** - единообразная обработка ошибок
5. **Testability** - каждый компонент легко тестируется

### Целевая структура
```
backend/
├── main.py                    # Только инициализация приложения (~50 строк)
├── core/                      # Ядро приложения
│   ├── __init__.py
│   ├── config.py             # Конфигурация приложения
│   ├── database.py           # Соединения с БД (будущее)
│   ├── dependencies.py       # FastAPI зависимости
│   ├── exceptions.py         # Кастомные исключения
│   └── security.py           # Аутентификация (будущее)
├── api/                      # API слой
│   ├── __init__.py
│   ├── middleware/           # Middleware
│   │   ├── __init__.py
│   │   ├── cors.py
│   │   ├── logging.py
│   │   └── error_handler.py
│   ├── routes/              # API routes
│   │   ├── __init__.py
│   │   ├── sessions.py
│   │   ├── companies.py
│   │   ├── criteria.py
│   │   ├── health.py
│   │   └── files.py
│   └── websocket/           # WebSocket обработчики
│       ├── __init__.py
│       ├── manager.py
│       └── handlers.py
├── services/                # Бизнес-логика
│   ├── __init__.py
│   ├── session_service.py
│   ├── company_service.py
│   ├── processing_service.py
│   ├── file_service.py
│   ├── notification_service.py
│   └── task_service.py
├── models/                  # Модели данных
│   ├── __init__.py
│   ├── schemas/            # Pydantic схемы
│   │   ├── __init__.py
│   │   ├── session.py
│   │   ├── company.py
│   │   ├── criteria.py
│   │   └── common.py
│   └── enums.py           # Enum классы
├── repositories/           # Доступ к данным
│   ├── __init__.py
│   ├── base.py
│   ├── session_repository.py
│   ├── company_repository.py
│   └── file_repository.py
├── utils/                  # Утилиты
│   ├── __init__.py
│   ├── logger.py
│   ├── validators.py
│   ├── formatters.py
│   └── helpers.py
└── tests/                 # Тесты
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    ├── integration/
    └── e2e/
```

---

## 🔄 Пошаговый план рефакторинга

### Этап 1: Подготовка и базовая структура (Неделя 1)

#### Шаг 1.1: Создание структуры папок
```bash
mkdir -p backend/{core,api/{middleware,routes,websocket},services,models/{schemas},repositories,utils,tests/{unit,integration,e2e}}
touch backend/{core,api,api/middleware,api/routes,api/websocket,services,models,models/schemas,repositories,utils,tests}/__init__.py
```

#### Шаг 1.2: Создание базовых файлов

**backend/core/config.py**
```python
from pydantic import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # API Keys
    openai_api_key: str
    serper_api_key: str
    scrapingbee_api_key: str
    hubspot_api_key: Optional[str] = None
    
    # Application settings
    app_name: str = "Company Canvas API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Paths
    output_dir: str = "output"
    sessions_dir: str = "output/sessions"
    
    # Processing
    max_concurrent_tasks: int = 10
    task_timeout: int = 3600
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
```

**backend/core/exceptions.py**
```python
from fastapi import HTTPException
from typing import Optional, Dict, Any

class CompanyCanvasException(Exception):
    """Base exception for Company Canvas application"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

class SessionNotFoundError(CompanyCanvasException):
    """Session not found error"""
    pass

class SessionAlreadyExistsError(CompanyCanvasException):
    """Session already exists error"""
    pass

class ProcessingError(CompanyCanvasException):
    """Processing pipeline error"""
    pass

class ValidationError(CompanyCanvasException):
    """Data validation error"""
    pass

class FileOperationError(CompanyCanvasException):
    """File operation error"""
    pass

# HTTP Exception handlers
def create_http_exception(exc: CompanyCanvasException, status_code: int = 500) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "message": exc.message,
            "type": exc.__class__.__name__,
            "details": exc.details
        }
    )
```

#### Шаг 1.3: Создание моделей данных

**backend/models/enums.py**
```python
from enum import Enum

class SessionStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running" 
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
```

**backend/models/schemas/session.py**
```python
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from ..enums import SessionStatus

class SessionCreate(BaseModel):
    original_filename: str
    context_text: Optional[str] = None
    run_llm_deep_search: bool = True
    write_to_hubspot: bool = True

class SessionUpdate(BaseModel):
    status: Optional[SessionStatus] = None
    error_message: Optional[str] = None
    processing_messages: Optional[List[str]] = None

class SessionBase(BaseModel):
    session_id: str
    original_filename: str
    status: SessionStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
class SessionDetail(SessionBase):
    input_file_path: Optional[str] = None
    output_csv_path: Optional[str] = None
    pipeline_log_path: Optional[str] = None
    context_used: Optional[str] = None
    initial_upload_count: int = 0
    processed_count: int = 0
    error_message: Optional[str] = None
    processing_messages: List[str] = []
    run_llm_deep_search: bool = True
    write_to_hubspot: bool = True

class SessionResponse(SessionDetail):
    class Config:
        from_attributes = True
```

### Этап 2: Извлечение сервисного слоя (Неделя 1-2)

#### Шаг 2.1: Создание базового сервиса

**backend/services/base_service.py**
```python
from abc import ABC
import structlog
from typing import Optional, Dict, Any

class BaseService(ABC):
    """Base service class with common functionality"""
    
    def __init__(self):
        self.logger = structlog.get_logger(self.__class__.__name__)
    
    def _log_operation(self, operation: str, **kwargs):
        """Log service operation with context"""
        self.logger.info(f"Operation: {operation}", **kwargs)
    
    def _log_error(self, error: Exception, operation: str, **kwargs):
        """Log service error with context"""
        self.logger.error(
            f"Error in {operation}",
            error=str(error),
            error_type=type(error).__name__,
            **kwargs
        )
```

#### Шаг 2.2: Создание сервиса сессий

**backend/services/session_service.py**
```python
from typing import List, Optional
from pathlib import Path
import asyncio
from datetime import datetime

from .base_service import BaseService
from ..models.schemas.session import SessionCreate, SessionUpdate, SessionDetail
from ..models.enums import SessionStatus
from ..repositories.session_repository import SessionRepository
from ..core.exceptions import SessionNotFoundError, SessionAlreadyExistsError
from ..utils.helpers import generate_session_id

class SessionService(BaseService):
    """Service for managing processing sessions"""
    
    def __init__(self, session_repository: SessionRepository):
        super().__init__()
        self.repository = session_repository
    
    async def create_session(self, session_data: SessionCreate) -> SessionDetail:
        """Create a new processing session"""
        self._log_operation("create_session", filename=session_data.original_filename)
        
        # Generate unique session ID
        session_id = generate_session_id(session_data.original_filename)
        
        # Check if session already exists
        existing = await self.repository.get_by_id(session_id)
        if existing:
            raise SessionAlreadyExistsError(f"Session {session_id} already exists")
        
        # Create session object
        session = SessionDetail(
            session_id=session_id,
            original_filename=session_data.original_filename,
            status=SessionStatus.CREATED,
            created_at=datetime.utcnow(),
            run_llm_deep_search=session_data.run_llm_deep_search,
            write_to_hubspot=session_data.write_to_hubspot
        )
        
        # Save to repository
        saved_session = await self.repository.create(session)
        
        self._log_operation("session_created", session_id=session_id)
        return saved_session
    
    async def get_session(self, session_id: str) -> SessionDetail:
        """Get session by ID"""
        session = await self.repository.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found")
        return session
    
    async def list_sessions(self) -> List[SessionDetail]:
        """List all sessions"""
        return await self.repository.list_all()
    
    async def update_session(self, session_id: str, updates: SessionUpdate) -> SessionDetail:
        """Update session"""
        session = await self.get_session(session_id)
        
        # Apply updates
        if updates.status:
            session.status = updates.status
        if updates.error_message:
            session.error_message = updates.error_message
        if updates.processing_messages:
            session.processing_messages.extend(updates.processing_messages)
        
        session.updated_at = datetime.utcnow()
        
        # Save updates
        updated_session = await self.repository.update(session_id, session)
        
        self._log_operation("session_updated", session_id=session_id, status=updates.status)
        return updated_session
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        session = await self.get_session(session_id)  # Проверяем существование
        result = await self.repository.delete(session_id)
        
        self._log_operation("session_deleted", session_id=session_id)
        return result
```

#### Шаг 2.3: Создание сервиса обработки

**backend/services/processing_service.py**
```python
from typing import Optional, Dict, Any
import asyncio
from pathlib import Path

from .base_service import BaseService
from .session_service import SessionService
from .task_service import TaskService
from ..models.schemas.session import SessionUpdate
from ..models.enums import SessionStatus
from ..core.exceptions import ProcessingError
from ..core.config import settings

class ProcessingService(BaseService):
    """Service for managing processing pipeline"""
    
    def __init__(
        self, 
        session_service: SessionService,
        task_service: TaskService
    ):
        super().__init__()
        self.session_service = session_service
        self.task_service = task_service
    
    async def start_processing(self, session_id: str) -> Dict[str, Any]:
        """Start processing for a session"""
        self._log_operation("start_processing", session_id=session_id)
        
        # Get session
        session = await self.session_service.get_session(session_id)
        
        # Check if already processing
        if self.task_service.is_task_active(session_id):
            return {"status": "already_running", "session_id": session_id}
        
        # Update session status
        await self.session_service.update_session(
            session_id, 
            SessionUpdate(status=SessionStatus.RUNNING)
        )
        
        # Create and start background task
        task = asyncio.create_task(
            self._run_processing_pipeline(session_id)
        )
        
        # Register task with callback
        task.add_done_callback(
            lambda t: asyncio.create_task(self._processing_done_callback(t, session_id))
        )
        
        # Track task
        self.task_service.register_task(session_id, task)
        
        return {"status": "started", "session_id": session_id}
    
    async def cancel_processing(self, session_id: str) -> Dict[str, Any]:
        """Cancel processing for a session"""
        self._log_operation("cancel_processing", session_id=session_id)
        
        # Cancel task if exists
        if self.task_service.is_task_active(session_id):
            self.task_service.cancel_task(session_id)
            
            # Update session status
            await self.session_service.update_session(
                session_id,
                SessionUpdate(
                    status=SessionStatus.CANCELLED,
                    error_message="Processing cancelled by user"
                )
            )
            
            return {"status": "cancelled", "session_id": session_id}
        
        return {"status": "no_active_task", "session_id": session_id}
    
    async def _run_processing_pipeline(self, session_id: str):
        """Run the actual processing pipeline"""
        try:
            session = await self.session_service.get_session(session_id)
            
            # Import and run pipeline
            from ..pipeline.runner import PipelineRunner
            
            runner = PipelineRunner(session_id)
            results = await runner.run()
            
            # Update session with results
            await self.session_service.update_session(
                session_id,
                SessionUpdate(
                    status=SessionStatus.COMPLETED,
                    processing_messages=[f"Processed {len(results)} companies"]
                )
            )
            
            self._log_operation("processing_completed", session_id=session_id, count=len(results))
            
        except Exception as e:
            self._log_error(e, "processing_pipeline", session_id=session_id)
            
            await self.session_service.update_session(
                session_id,
                SessionUpdate(
                    status=SessionStatus.ERROR,
                    error_message=str(e)
                )
            )
            
            raise ProcessingError(f"Processing failed for session {session_id}: {str(e)}")
    
    async def _processing_done_callback(self, task: asyncio.Task, session_id: str):
        """Callback when processing task is done"""
        try:
            if task.cancelled():
                self._log_operation("task_cancelled", session_id=session_id)
            elif task.exception():
                self._log_error(task.exception(), "task_exception", session_id=session_id)
            else:
                self._log_operation("task_completed", session_id=session_id)
        except Exception as e:
            self._log_error(e, "task_callback", session_id=session_id)
        finally:
            # Cleanup task
            self.task_service.unregister_task(session_id)
```

### Этап 3: Создание репозиториев (Неделя 2)

#### Шаг 3.1: Базовый репозиторий

**backend/repositories/base.py**
```python
from abc import ABC, abstractmethod
from typing import List, Optional, TypeVar, Generic

T = TypeVar('T')

class BaseRepository(ABC, Generic[T]):
    """Base repository interface"""
    
    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create new entity"""
        pass
    
    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[T]:
        """Get entity by ID"""
        pass
    
    @abstractmethod
    async def list_all(self) -> List[T]:
        """List all entities"""
        pass
    
    @abstractmethod
    async def update(self, id: str, entity: T) -> T:
        """Update entity"""
        pass
    
    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Delete entity"""
        pass
```

#### Шаг 3.2: Session Repository

**backend/repositories/session_repository.py**
```python
import json
import asyncio
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from .base import BaseRepository
from ..models.schemas.session import SessionDetail
from ..core.config import settings
from ..core.exceptions import FileOperationError

class SessionRepository(BaseRepository[SessionDetail]):
    """File-based session repository"""
    
    def __init__(self):
        self.metadata_file = Path(settings.sessions_dir).parent / "sessions_metadata.json"
        self._lock = asyncio.Lock()
    
    async def _load_metadata(self) -> List[dict]:
        """Load sessions metadata from file"""
        if not self.metadata_file.exists():
            return []
        
        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            raise FileOperationError(f"Failed to load sessions metadata: {e}")
    
    async def _save_metadata(self, metadata: List[dict]):
        """Save sessions metadata to file"""
        try:
            # Ensure directory exists
            self.metadata_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            raise FileOperationError(f"Failed to save sessions metadata: {e}")
    
    async def create(self, session: SessionDetail) -> SessionDetail:
        """Create new session"""
        async with self._lock:
            metadata = await self._load_metadata()
            
            # Convert to dict for storage
            session_dict = session.model_dump()
            metadata.append(session_dict)
            
            await self._save_metadata(metadata)
            return session
    
    async def get_by_id(self, session_id: str) -> Optional[SessionDetail]:
        """Get session by ID"""
        async with self._lock:
            metadata = await self._load_metadata()
            
            for session_data in metadata:
                if session_data.get('session_id') == session_id:
                    return SessionDetail(**session_data)
            
            return None
    
    async def list_all(self) -> List[SessionDetail]:
        """List all sessions"""
        async with self._lock:
            metadata = await self._load_metadata()
            return [SessionDetail(**data) for data in metadata]
    
    async def update(self, session_id: str, session: SessionDetail) -> SessionDetail:
        """Update session"""
        async with self._lock:
            metadata = await self._load_metadata()
            
            for i, session_data in enumerate(metadata):
                if session_data.get('session_id') == session_id:
                    metadata[i] = session.model_dump()
                    await self._save_metadata(metadata)
                    return session
            
            raise FileOperationError(f"Session {session_id} not found for update")
    
    async def delete(self, session_id: str) -> bool:
        """Delete session"""
        async with self._lock:
            metadata = await self._load_metadata()
            
            for i, session_data in enumerate(metadata):
                if session_data.get('session_id') == session_id:
                    del metadata[i]
                    await self._save_metadata(metadata)
                    return True
            
            return False
```

### Этап 4: Создание API слоя (Неделя 2-3)

#### Шаг 4.1: Dependency injection

**backend/core/dependencies.py**
```python
from fastapi import Depends
from typing import Annotated

from ..services.session_service import SessionService
from ..services.processing_service import ProcessingService
from ..services.file_service import FileService
from ..repositories.session_repository import SessionRepository

# Repository dependencies
def get_session_repository() -> SessionRepository:
    return SessionRepository()

# Service dependencies
def get_session_service(
    session_repo: Annotated[SessionRepository, Depends(get_session_repository)]
) -> SessionService:
    return SessionService(session_repo)

def get_processing_service(
    session_service: Annotated[SessionService, Depends(get_session_service)]
) -> ProcessingService:
    from ..services.task_service import TaskService
    task_service = TaskService()
    return ProcessingService(session_service, task_service)

def get_file_service() -> FileService:
    return FileService()
```

#### Шаг 4.2: Session API routes

**backend/api/routes/sessions.py**
```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from typing import List, Optional, Annotated

from ...core.dependencies import get_session_service, get_processing_service, get_file_service
from ...services.session_service import SessionService
from ...services.processing_service import ProcessingService
from ...services.file_service import FileService
from ...models.schemas.session import SessionCreate, SessionResponse, SessionDetail
from ...core.exceptions import create_http_exception, CompanyCanvasException

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])

@router.get("/", response_model=List[SessionResponse])
async def list_sessions(
    session_service: Annotated[SessionService, Depends(get_session_service)]
):
    """List all processing sessions"""
    try:
        sessions = await session_service.list_sessions()
        return sessions
    except CompanyCanvasException as e:
        raise create_http_exception(e, 500)

@router.post("/", response_model=SessionResponse)
async def create_session(
    file: UploadFile = File(...),
    context_text: Optional[str] = Form(None),
    run_llm_deep_search: bool = Form(True),
    write_to_hubspot: bool = Form(True),
    session_service: Annotated[SessionService, Depends(get_session_service)] = None,
    file_service: Annotated[FileService, Depends(get_file_service)] = None
):
    """Create a new processing session"""
    try:
        # Validate file
        await file_service.validate_upload_file(file)
        
        # Create session
        session_data = SessionCreate(
            original_filename=file.filename,
            context_text=context_text,
            run_llm_deep_search=run_llm_deep_search,
            write_to_hubspot=write_to_hubspot
        )
        
        session = await session_service.create_session(session_data)
        
        # Save file
        await file_service.save_session_file(session.session_id, file, context_text)
        
        return session
        
    except CompanyCanvasException as e:
        raise create_http_exception(e, 400)

@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    session_service: Annotated[SessionService, Depends(get_session_service)]
):
    """Get session details"""
    try:
        session = await session_service.get_session(session_id)
        return session
    except CompanyCanvasException as e:
        raise create_http_exception(e, 404)

@router.post("/{session_id}/start")
async def start_processing(
    session_id: str,
    processing_service: Annotated[ProcessingService, Depends(get_processing_service)]
):
    """Start processing for a session"""
    try:
        result = await processing_service.start_processing(session_id)
        return result
    except CompanyCanvasException as e:
        raise create_http_exception(e, 400)

@router.post("/{session_id}/cancel")
async def cancel_processing(
    session_id: str,
    processing_service: Annotated[ProcessingService, Depends(get_processing_service)]
):
    """Cancel processing for a session"""
    try:
        result = await processing_service.cancel_processing(session_id)
        return result
    except CompanyCanvasException as e:
        raise create_http_exception(e, 400)
```

#### Шаг 4.3: WebSocket manager

**backend/api/websocket/manager.py**
```python
import json
from typing import List, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
import structlog

logger = structlog.get_logger(__name__)

class WebSocketManager:
    """WebSocket connection manager"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.session_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str = None):
        """Connect websocket"""
        await websocket.accept()
        self.active_connections.append(websocket)
        
        if session_id:
            if session_id not in self.session_connections:
                self.session_connections[session_id] = []
            self.session_connections[session_id].append(websocket)
        
        logger.info("WebSocket connected", session_id=session_id)
    
    def disconnect(self, websocket: WebSocket, session_id: str = None):
        """Disconnect websocket"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        
        if session_id and session_id in self.session_connections:
            if websocket in self.session_connections[session_id]:
                self.session_connections[session_id].remove(websocket)
                
                # Clean up empty session connections
                if not self.session_connections[session_id]:
                    del self.session_connections[session_id]
        
        logger.info("WebSocket disconnected", session_id=session_id)
    
    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """Send message to specific websocket"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error("Failed to send personal message", error=str(e))
            self.disconnect(websocket)
    
    async def send_to_session(self, message: Dict[str, Any], session_id: str):
        """Send message to all websockets in a session"""
        if session_id not in self.session_connections:
            return
        
        dead_connections = []
        for websocket in self.session_connections[session_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error("Failed to send session message", error=str(e), session_id=session_id)
                dead_connections.append(websocket)
        
        # Clean up dead connections
        for websocket in dead_connections:
            self.disconnect(websocket, session_id)
    
    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected websockets"""
        dead_connections = []
        for websocket in self.active_connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error("Failed to broadcast message", error=str(e))
                dead_connections.append(websocket)
        
        # Clean up dead connections
        for websocket in dead_connections:
            self.disconnect(websocket)

# Global manager instance
websocket_manager = WebSocketManager()
```

### Этап 5: Создание нового main.py (Неделя 3)

#### Шаг 5.1: Минимальный main.py

**backend/main.py** (новый, ~50 строк)
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import structlog

from .core.config import settings
from .api.middleware.cors import setup_cors
from .api.middleware.error_handler import setup_error_handlers
from .api.middleware.logging import setup_logging_middleware
from .api.routes import sessions, companies, criteria, health, files
from .api.websocket.handlers import setup_websocket_routes
from .utils.logger import configure_logging

# Configure logging
configure_logging()
logger = structlog.get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug
)

# Setup middleware
setup_cors(app)
setup_error_handlers(app)
setup_logging_middleware(app)

# Setup routes
app.include_router(sessions.router)
app.include_router(companies.router)
app.include_router(criteria.router)
app.include_router(health.router)
app.include_router(files.router)

# Setup WebSocket
setup_websocket_routes(app)

# Static files
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def read_root():
    return FileResponse("frontend/index.html")

@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up", version=settings.app_version)

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down")
    # Cleanup tasks will be handled by services

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
```

---

## 🧪 Тестирование

### Структура тестов
```
tests/
├── conftest.py                    # Pytest конфигурация
├── unit/                         # Единичные тесты
│   ├── services/
│   │   ├── test_session_service.py
│   │   ├── test_processing_service.py
│   │   └── test_file_service.py
│   ├── repositories/
│   │   └── test_session_repository.py
│   └── utils/
│       └── test_helpers.py
├── integration/                  # Интеграционные тесты
│   ├── api/
│   │   ├── test_sessions_api.py
│   │   └── test_websocket.py
│   └── services/
│       └── test_processing_flow.py
└── e2e/                         # End-to-end тесты
    └── test_complete_flow.py
```

### Пример теста сервиса
**tests/unit/services/test_session_service.py**
```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from backend.services.session_service import SessionService
from backend.models.schemas.session import SessionCreate, SessionDetail
from backend.models.enums import SessionStatus
from backend.core.exceptions import SessionNotFoundError

@pytest.fixture
def mock_session_repository():
    return AsyncMock()

@pytest.fixture
def session_service(mock_session_repository):
    return SessionService(mock_session_repository)

@pytest.mark.asyncio
async def test_create_session_success(session_service, mock_session_repository):
    # Arrange
    session_data = SessionCreate(
        original_filename="test.csv",
        context_text="test context",
        run_llm_deep_search=True,
        write_to_hubspot=False
    )
    
    expected_session = SessionDetail(
        session_id="20241201_120000_test",
        original_filename="test.csv",
        status=SessionStatus.CREATED,
        created_at=datetime.utcnow()
    )
    
    mock_session_repository.get_by_id.return_value = None
    mock_session_repository.create.return_value = expected_session
    
    # Act
    result = await session_service.create_session(session_data)
    
    # Assert
    assert result.session_id == expected_session.session_id
    assert result.original_filename == "test.csv"
    assert result.status == SessionStatus.CREATED
    mock_session_repository.create.assert_called_once()

@pytest.mark.asyncio
async def test_get_session_not_found(session_service, mock_session_repository):
    # Arrange
    mock_session_repository.get_by_id.return_value = None
    
    # Act & Assert
    with pytest.raises(SessionNotFoundError):
        await session_service.get_session("nonexistent_id")
```

---

## 📅 Временные рамки

### Неделя 1: Базовая структура (20 часов)
- **День 1-2**: Создание папок и базовых файлов
- **День 3-4**: Модели данных и исключения
- **День 5**: Базовые сервисы и репозитории

### Неделя 2: Сервисы и репозитории (25 часов)
- **День 1-2**: Полная реализация SessionService
- **День 3**: ProcessingService
- **День 4**: Репозитории и файловые операции
- **День 5**: Тестирование сервисов

### Неделя 3: API и интеграция (30 часов)
- **День 1-2**: API routes и dependency injection
- **День 3**: WebSocket manager
- **День 4**: Новый main.py и middleware
- **День 5**: Интеграционные тесты

### Неделя 4: Финализация и оптимизация (20 часов)
- **День 1-2**: Перенос оставшихся endpoints
- **День 3**: E2E тестирование
- **День 4**: Оптимизация и документация
- **День 5**: Финальное тестирование

---

## 🔍 Критерии успеха

### Технические критерии
- [ ] Все файлы менее 200 строк
- [ ] Покрытие тестами 80%+
- [ ] Нет прямых импортов между слоями
- [ ] Единообразная обработка ошибок
- [ ] Структурированное логирование

### Функциональные критерии
- [ ] Все существующие API работают
- [ ] WebSocket соединения стабильны
- [ ] Фоновые задачи выполняются корректно
- [ ] Файловые операции безопасны
- [ ] Производительность не ухудшилась

### Поддерживаемость
- [ ] Легко добавить новый endpoint
- [ ] Легко изменить логику обработки
- [ ] Легко добавить новые тесты
- [ ] Понятная структура для новых разработчиков

---

## 🚀 Результат рефакторинга

После завершения рефакторинга получим:
1. **Модульную архитектуру** с четким разделением ответственности
2. **Тестируемый код** с высоким покрытием
3. **Масштабируемую структуру** для будущих изменений
4. **Единообразную обработку ошибок** и логирование
5. **Готовность к внедрению базы данных** в будущем

Основная цель - создать maintainable и scalable архитектуру, которая позволит быстро развивать проект в будущем. 