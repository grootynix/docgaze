from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: int
    filename: str
    content_type: Optional[str]
    size_bytes: int
    status: Literal["processing", "ready", "failed"]
    error_message: Optional[str]
    created_at: datetime
    chunk_count: Optional[int] = None

    model_config = {"from_attributes": True}


class ChatSessionOut(BaseModel):
    id: int
    document_id: int
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    session_id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=16000)


class CreateSessionRequest(BaseModel):
    title: str = Field(default="Chat", max_length=256)


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    llm_provider: Literal["openai", "ollama", "none"] = "none"
    openai: bool = False
    openai_error: Optional[str] = None
    ollama: bool = False
    ollama_error: Optional[str] = None
