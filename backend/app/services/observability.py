from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_client: Any = None


def _configure_langfuse_env() -> None:
    if settings.langfuse_public_key:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    if settings.langfuse_secret_key:
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    if settings.langfuse_host:
        host = settings.langfuse_host.rstrip("/")
        os.environ["LANGFUSE_HOST"] = host
        os.environ["LANGFUSE_BASE_URL"] = host


def get_langfuse() -> Any:
    global _client
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    if _client is None:
        try:
            _configure_langfuse_env()
            from langfuse import get_client

            _client = get_client()
            ok = _client.auth_check()
            logger.info(
                "Langfuse v3 client ready host=%s auth_check=%s",
                settings.langfuse_host,
                ok,
            )
            if not ok:
                logger.error("Langfuse auth_check failed — check US vs EU base URL and API keys")
        except Exception as e:
            logger.warning("Langfuse init failed: %s", e)
            return None
    return _client


def flush_observability() -> None:
    client = get_langfuse()
    if client is not None:
        try:
            client.flush()
        except Exception as e:
            logger.warning("Langfuse flush failed: %s", e)


def trace_ingest_complete(
    document_id: int,
    filename: str,
    chunk_count: int,
    embedding_model: str,
    usage_details: Optional[Dict[str, int]] = None,
    error: Optional[str] = None,
) -> None:
    client = get_langfuse()
    if client is None:
        return
    try:
        with client.start_as_current_observation(
            as_type="span",
            name="document-ingest",
            input={"document_id": document_id, "filename": filename},
            metadata={"document_id": document_id},
        ) as span:
            if error:
                span.update(output={"error": error}, level="ERROR")
            else:
                span.update(
                    output={
                        "chunk_count": chunk_count,
                        "embedding_model": embedding_model,
                    }
                )
                if usage_details:
                    with client.start_as_current_observation(
                        as_type="generation",
                        name="document-embeddings",
                        model=settings.openai_embed_model,
                    ) as gen:
                        gen.update(usage_details=usage_details)
            span.update_trace(
                name="document-ingest",
                session_id=f"doc-{document_id}",
            )
    except Exception as e:
        logger.warning("Langfuse ingest trace failed: %s", e)
    flush_observability()


def span_retrieval(
    session_id: int,
    document_id: int,
    query: str,
    chunk_indices: List[int],
    scores: List[float],
    embedding_model: str,
) -> None:
    client = get_langfuse()
    if client is None:
        return
    try:
        with client.start_as_current_observation(
            as_type="span",
            name="rag-retrieval",
            input={"query": query},
            metadata={"document_id": document_id},
        ) as span:
            span.update(
                output={
                    "chunk_indices": chunk_indices,
                    "scores": scores,
                    "embedding_model": embedding_model,
                }
            )
            span.update_trace(session_id=str(session_id), user_id=str(document_id))
    except Exception as e:
        logger.warning("Langfuse retrieval trace failed: %s", e)
    flush_observability()


def trace_chat_complete(
    session_id: int,
    document_id: int,
    user_message: str,
    messages: List[dict[str, str]],
    assistant_text: str,
    model: str,
    latency_ms: float,
    time_to_first_token_ms: Optional[float],
    chunk_count: int,
    usage_details: Optional[Dict[str, int]] = None,
    error: Optional[str] = None,
) -> None:
    client = get_langfuse()
    if client is None:
        return
    try:
        with client.start_as_current_observation(
            as_type="span",
            name="chat-turn",
            input=user_message,
            metadata={
                "document_id": document_id,
                "retrieved_chunks": chunk_count,
                "latency_ms": latency_ms,
                "time_to_first_token_ms": time_to_first_token_ms,
            },
        ) as span:
            span.update_trace(session_id=str(session_id), user_id=str(document_id))
            if error:
                span.update(output={"error": error}, level="ERROR")
            else:
                with client.start_as_current_observation(
                    as_type="generation",
                    name="rag-chat-completion",
                    model=model,
                    input=messages,
                ) as gen:
                    gen.update(output=assistant_text, usage_details=usage_details)
                span.update(output=assistant_text)
    except Exception as e:
        logger.warning("Langfuse chat trace failed: %s", e)
    flush_observability()
