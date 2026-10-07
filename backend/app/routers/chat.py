import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models import ChatSession, Document, DocumentStatus, Message, MessageRole
from app.schemas import ChatRequest, ChatSessionOut, CreateSessionRequest, MessageOut
from app.services.llm import chat_stream
from app.services.observability import trace_chat_complete
from app.services.openai_llm import TokenUsage
from app.services.retrieval import build_rag_messages, retrieve_chunks

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/documents/{document_id}/sessions", response_model=ChatSessionOut)
def create_session(
    document_id: int,
    body: CreateSessionRequest,
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.status != DocumentStatus.ready:
        raise HTTPException(400, f"Document is not ready (status: {doc.status.value})")

    session = ChatSession(document_id=document_id, title=body.title or "Chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info("Created session_id=%s document_id=%s", session.id, document_id)
    return session


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(session_id: int, db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return messages


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: int, body: ChatRequest, db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    doc = db.get(Document, session.document_id)
    if not doc or doc.status != DocumentStatus.ready:
        raise HTTPException(400, "Document is not available for chat")

    logger.info("Chat session_id=%s message_len=%s", session_id, len(body.message))

    user_msg = Message(session_id=session_id, role=MessageRole.user, content=body.message)
    db.add(user_msg)
    db.commit()

    prior = (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.id != user_msg.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    history: list[tuple[str, str]] = [
        (m.role.value, m.content) for m in prior if m.role in (MessageRole.user, MessageRole.assistant)
    ]

    try:
        chunks = await retrieve_chunks(
            db, session.document_id, body.message, session_id=session_id
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    messages = build_rag_messages(body.message, chunks, history)
    logger.info("RAG context chunks=%s for session_id=%s", len(chunks), session_id)
    async def event_stream() -> AsyncIterator[str]:
        full_parts: list[str] = []
        t0 = time.perf_counter()
        first_token_at: Optional[float] = None
        usage = TokenUsage()

        def on_usage(u: TokenUsage) -> None:
            usage.merge(u)

        yield f"data: {json.dumps({'type': 'started'})}\n\n"
        try:
            async for token in chat_stream(messages, on_usage=on_usage):
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                    logger.info(
                        "First token session_id=%s after %.2fs",
                        session_id,
                        first_token_at - t0,
                    )
                full_parts.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            assistant_text = "".join(full_parts)
            if not assistant_text.strip():
                assistant_text = (
                    "No response was generated. Check server logs and LLM configuration."
                )
                yield f"data: {json.dumps({'type': 'token', 'content': assistant_text})}\n\n"
            with SessionLocal() as write_db:
                assistant_msg = Message(
                    session_id=session_id,
                    role=MessageRole.assistant,
                    content=assistant_text,
                )
                write_db.add(assistant_msg)
                write_db.commit()
                write_db.refresh(assistant_msg)
                done_id = assistant_msg.id
            elapsed_ms = (time.perf_counter() - t0) * 1000
            ttft_ms = (
                (first_token_at - t0) * 1000 if first_token_at is not None else None
            )
            trace_chat_complete(
                session_id=session_id,
                document_id=session.document_id,
                user_message=body.message,
                messages=messages,
                assistant_text=assistant_text,
                model=settings.openai_chat_model,
                latency_ms=elapsed_ms,
                time_to_first_token_ms=ttft_ms,
                chunk_count=len(chunks),
                usage_details=usage.to_langfuse_usage_details()
                if usage.total_tokens
                else None,
            )
            logger.info(
                "Chat complete session_id=%s chars=%s elapsed=%.2fs",
                session_id,
                len(assistant_text),
                time.perf_counter() - t0,
            )
            yield f"data: {json.dumps({'type': 'done', 'message_id': done_id})}\n\n"
        except Exception as e:
            logger.exception("Chat stream failed session_id=%s", session_id)
            trace_chat_complete(
                session_id=session_id,
                document_id=session.document_id,
                user_message=body.message,
                messages=messages,
                assistant_text="",
                model=settings.openai_chat_model,
                latency_ms=(time.perf_counter() - t0) * 1000,
                time_to_first_token_ms=None,
                chunk_count=len(chunks),
                error=str(e),
            )
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
