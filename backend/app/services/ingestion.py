from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk, Document, DocumentStatus
from app.services.chunking import chunk_segments
from app.services.embeddings_store import embedding_to_bytes
from app.services.llm import active_embed_model_label, embed_texts
from app.services.observability import trace_ingest_complete
from app.services.parsers import parse_file

logger = logging.getLogger(__name__)


async def ingest_document(db: Session, document: Document, upload_path: Path) -> None:
    try:
        t0 = time.perf_counter()
        logger.info("Ingest start document_id=%s file=%s", document.id, document.filename)
        segments = parse_file(upload_path, document.content_type, document.filename)
        drafts = chunk_segments(segments)
        if not drafts:
            raise ValueError("Document contained no text to index")
        logger.info("Parsed %s chunks for document_id=%s", len(drafts), document.id)

        embed_result = await embed_texts([d.content for d in drafts])
        label = active_embed_model_label()
        for draft, vec in zip(drafts, embed_result.vectors):
            chunk = Chunk(
                document_id=document.id,
                chunk_index=draft.chunk_index,
                content=draft.content,
                embedding=embedding_to_bytes(vec),
                metadata_json=draft.metadata_json,
            )
            db.add(chunk)

        document.status = DocumentStatus.ready
        document.error_message = None
        document.embedding_model = label
        db.commit()
        logger.info(
            "Ingest done document_id=%s chunks=%s model=%s elapsed=%.2fs",
            document.id,
            len(drafts),
            label,
            time.perf_counter() - t0,
        )
        trace_ingest_complete(
            document_id=document.id,
            filename=document.filename,
            chunk_count=len(drafts),
            embedding_model=label,
            usage_details=embed_result.usage.to_langfuse_usage_details()
            if embed_result.usage.total_tokens
            else None,
        )
    except Exception as e:
        db.rollback()
        document.status = DocumentStatus.failed
        document.error_message = str(e)
        db.commit()
        trace_ingest_complete(
            document_id=document.id,
            filename=document.filename,
            chunk_count=0,
            embedding_model="",
            error=str(e),
        )
        raise


def save_upload_file(document_id: int, filename: str, src: Path) -> Path:
    dest_dir = settings.uploads_dir / str(document_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    shutil.copy2(src, dest)
    return dest


def delete_document_files(document_id: int) -> None:
    dest_dir = settings.uploads_dir / str(document_id)
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
