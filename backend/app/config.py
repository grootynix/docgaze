from __future__ import annotations

import os
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProvider = Literal["auto", "openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: LlmProvider = "auto"
    openai_api_key: Optional[str] = None
    openai_chat_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"
    database_url: str = "sqlite:///./data/docgaze.db"
    top_k_chunks: int = 5
    chunk_size: int = 800
    chunk_overlap: int = 100
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
    log_level: str = "INFO"
    data_dir: Path = Path("./data")

    langfuse_public_key: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("LANGFUSE_PUBLIC_KEY", "langfuse_public_key")
    )
    langfuse_secret_key: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("LANGFUSE_SECRET_KEY", "langfuse_secret_key")
    )
    langfuse_host: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("LANGFUSE_HOST", "LANGFUSE_BASE_URL", "langfuse_host"),
    )

    @field_validator("data_dir", mode="before")
    @classmethod
    def _coerce_data_dir(cls, v: object) -> object:
        if v is None or v == "":
            return Path(os.environ.get("DATA_DIR", "./data"))
        return v

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def openai_required(self) -> bool:
        return self.llm_provider == "openai"


settings = Settings()
