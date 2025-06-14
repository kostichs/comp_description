"""
Session Pydantic Models
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel

class SessionStatus(str, Enum):
    """Session processing status"""
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"

class SessionCreate(BaseModel):
    """Model for creating new session"""
    context_text: Optional[str] = ""
    run_llm_deep_search_pipeline: bool = True
    write_to_hubspot: bool = True

class SessionResponse(BaseModel):
    """Session response model"""
    session_id: str
    status: SessionStatus
    timestamp_created: Optional[str] = ""
    input_filename: Optional[str] = ""
    context_text: Optional[str] = ""
    run_llm_deep_search_pipeline: Optional[bool] = True
    write_to_hubspot: Optional[bool] = True
    progress_percentage: Optional[float] = 0.0
    processed_count: Optional[int] = 0
    error_count: Optional[int] = 0
    error_message: Optional[str] = "" 