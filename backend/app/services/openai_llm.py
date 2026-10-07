from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 64


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_langfuse_usage_details(self) -> Dict[str, int]:
        details: Dict[str, int] = {}
        if self.prompt_tokens:
            details["input"] = self.prompt_tokens
        if self.completion_tokens:
            details["output"] = self.completion_tokens
        return details

    def merge(self, other: TokenUsage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens


@dataclass
class EmbedBatchResult:
    vectors: List[List[float]]
    usage: TokenUsage = field(default_factory=TokenUsage)


def _client() -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _usage_from_response(usage: object) -> TokenUsage:
    if usage is None:
        return TokenUsage()
    return TokenUsage(
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
    )


async def openai_embed_text(text: str) -> List[float]:
    result = await openai_embed_texts([text])
    return result.vectors[0]


async def openai_embed_texts(texts: List[str]) -> EmbedBatchResult:
    if not texts:
        return EmbedBatchResult(vectors=[], usage=TokenUsage())
    client = _client()
    all_vectors: List[List[float]] = []
    total_usage = TokenUsage()
    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start : start + _BATCH_SIZE]
        response = await client.embeddings.create(
            model=settings.openai_embed_model,
            input=batch,
        )
        ordered = sorted(response.data, key=lambda row: row.index)
        all_vectors.extend([list(row.embedding) for row in ordered])
        total_usage.merge(_usage_from_response(response.usage))
        logger.info(
            "openai embed batch %s-%s/%s tokens=%s",
            start + 1,
            start + len(batch),
            len(texts),
            total_usage.total_tokens,
        )
    return EmbedBatchResult(vectors=all_vectors, usage=total_usage)


async def openai_chat_stream(
    messages: List[dict[str, str]],
    on_usage: Optional[Callable[[TokenUsage], None]] = None,
) -> AsyncIterator[str]:
    client = _client()
    stream = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )
    async for chunk in stream:
        if chunk.usage and on_usage:
            on_usage(_usage_from_response(chunk.usage))
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


async def check_openai() -> Tuple[bool, Optional[str]]:
    if not settings.openai_api_key:
        return False, "OPENAI_API_KEY not set"
    try:
        await openai_embed_text("health-check")
        return True, None
    except Exception as e:
        logger.warning("OpenAI health check failed: %s", e)
        return False, str(e)
