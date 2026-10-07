from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Callable, List, Optional, Tuple

from app.config import settings
from app.services import ollama as ollama_svc
from app.services.openai_llm import (
    EmbedBatchResult,
    TokenUsage,
    check_openai,
    openai_chat_stream,
    openai_embed_text,
    openai_embed_texts,
)

logger = logging.getLogger(__name__)


def _openai_only() -> bool:
    return settings.openai_required


def _require_openai_key() -> None:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")


def active_embed_model_label() -> str:
    if settings.openai_api_key or _openai_only():
        return f"openai:{settings.openai_embed_model}"
    return f"ollama:{settings.ollama_embed_model}"


async def embed_text(text: str) -> List[float]:
    if _openai_only():
        _require_openai_key()
        return await openai_embed_text(text)
    if settings.openai_api_key:
        try:
            return await openai_embed_text(text)
        except Exception as e:
            logger.warning("OpenAI embed failed, using Ollama: %s", e)
    return await ollama_svc.ollama_embed_text(text)


async def embed_texts(texts: List[str]) -> EmbedBatchResult:
    if not texts:
        return EmbedBatchResult(vectors=[], usage=TokenUsage())
    if _openai_only():
        _require_openai_key()
        return await openai_embed_texts(texts)
    if settings.openai_api_key:
        try:
            return await openai_embed_texts(texts)
        except Exception as e:
            logger.warning("OpenAI batch embed failed, using Ollama: %s", e)
    vectors: List[List[float]] = []
    for i, text in enumerate(texts, start=1):
        vectors.append(await ollama_svc.ollama_embed_text(text))
        if i % 5 == 0 or i == len(texts):
            logger.info("Ollama embed progress %s/%s", i, len(texts))
    return EmbedBatchResult(vectors=vectors, usage=TokenUsage())


async def chat_stream(
    messages: List[dict[str, str]],
    on_usage: Optional[Callable[[TokenUsage], None]] = None,
) -> AsyncIterator[str]:
    if _openai_only():
        _require_openai_key()
        async for token in openai_chat_stream(messages, on_usage=on_usage):
            yield token
        return
    if settings.openai_api_key:
        try:
            async for token in openai_chat_stream(messages, on_usage=on_usage):
                yield token
            return
        except Exception as e:
            logger.warning("OpenAI chat failed, using Ollama: %s", e)
    async for token in ollama_svc.ollama_chat_stream(messages):
        yield token


async def check_llm_health() -> Tuple[bool, str, bool, Optional[str], bool, Optional[str]]:
    openai_ok, openai_err = await check_openai()
    if _openai_only():
        provider = "openai" if openai_ok else "none"
        return openai_ok, provider, openai_ok, openai_err, False, "disabled in openai-only mode"

    ollama_ok, ollama_err = await ollama_svc.check_ollama()
    if settings.openai_api_key and openai_ok:
        return True, "openai", True, None, ollama_ok, ollama_err
    if settings.openai_api_key and not openai_ok and ollama_ok:
        return True, "ollama", False, openai_err, True, None
    if not settings.openai_api_key and ollama_ok:
        return True, "ollama", False, openai_err, True, None
    if settings.openai_api_key:
        return False, "none", False, openai_err, ollama_ok, ollama_err
    return False, "none", False, openai_err, ollama_ok, ollama_err
