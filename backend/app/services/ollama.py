from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Optional, Tuple

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def _ollama_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    resp = await client.request(method, f"{settings.ollama_base_url}{path}", json=payload)
    if resp.is_success:
        return resp.json()
    detail = resp.text
    try:
        body = resp.json()
        if isinstance(body, dict) and body.get("error"):
            detail = str(body["error"])
    except json.JSONDecodeError:
        pass
    raise httpx.HTTPStatusError(
        f"Ollama {path}: {detail}",
        request=resp.request,
        response=resp,
    )


async def list_local_models(client: httpx.AsyncClient) -> list[str]:
    resp = await client.get(f"{settings.ollama_base_url}/api/tags")
    resp.raise_for_status()
    data = resp.json()
    models = data.get("models") or []
    names: list[str] = []
    for m in models:
        name = m.get("name") or m.get("model")
        if name:
            names.append(name)
    return names


def _model_present(available: list[str], wanted: str) -> bool:
    if wanted in available:
        return True
    prefix = wanted.split(":")[0]
    return any(m == wanted or m.startswith(f"{prefix}:") for m in available)


async def check_ollama() -> Tuple[bool, Optional[str]]:
    """True when Ollama is up, chat + embed models exist, and embeddings work."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            available = await list_local_models(client)
    except Exception as e:
        return False, f"Cannot reach Ollama at {settings.ollama_base_url}: {e}"

    if not _model_present(available, settings.ollama_chat_model):
        return (
            False,
            f"Chat model '{settings.ollama_chat_model}' not found. "
            f"Run: ollama pull {settings.ollama_chat_model}",
        )

    if not _model_present(available, settings.ollama_embed_model):
        return (
            False,
            f"Embedding model '{settings.ollama_embed_model}' not found. "
            f"Run: ollama pull {settings.ollama_embed_model}",
        )

    try:
        await ollama_embed_text("health-check", client=None)
    except httpx.HTTPStatusError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

    return True, None


async def ollama_embed_text(text: str, client: httpx.AsyncClient | None = None) -> list[float]:
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=120.0)
    try:
        try:
            data = await _ollama_json(
                client,
                "POST",
                "/api/embed",
                {"model": settings.ollama_embed_model, "input": text},
            )
            embeddings = data.get("embeddings")
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
        except httpx.HTTPStatusError:
            data = await _ollama_json(
                client,
                "POST",
                "/api/embeddings",
                {"model": settings.ollama_embed_model, "prompt": text},
            )
            embedding = data.get("embedding")
            if embedding:
                return embedding
        raise RuntimeError(
            "Ollama returned no embedding vector. Ensure embeddings are enabled "
            "(restart Ollama with embedding support) and the embed model is pulled."
        )
    finally:
        if owns_client and client is not None:
            await client.aclose()


async def ollama_chat_stream(
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_base_url}/api/chat",
            json={"model": settings.ollama_chat_model, "messages": messages, "stream": True},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("done"):
                    break
                msg = payload.get("message") or {}
                content = msg.get("content") or ""
                thinking = msg.get("thinking") or ""
                piece = content or thinking
                if piece:
                    yield piece
