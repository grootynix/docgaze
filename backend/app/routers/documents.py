import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chunk, Document, DocumentStatus
from app.schemas import DocumentOut
from app.services.ingestion import delete_document_files, ingest_document, save_upload_file

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)

ALLOWED_SUFFIXES = {".pdf", ".txt", ".md"}


def _document_out(doc: Document, chunk_count=None) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        status=doc.status.value,
        error_message=doc.error_message,
        created_at=doc.created_at,
        chunk_count=chunk_count,
    )


@router.post("/documents", response_model=DocumentOut)
async def upload_document(file: UploadFile, db: Session = Depends(get_db)):
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, "Only PDF, .txt, and .md files are supported")

    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")

    document = Document(
        filename=file.filename,
        content_type=file.content_type,
        size_bytes=len(content),
        status=DocumentStatus.processing,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    logger.info("Upload started id=%s name=%s bytes=%s", document.id, file.filename, len(content))
    try:
        stored = save_upload_file(document.id, file.filename, tmp_path)
        document.file_path = str(stored)
        db.commit()
        try:
            await ingest_document(db, document, stored)
        except Exception:
            db.refresh(document)
        db.refresh(document)
    finally:
        tmp_path.unlink(missing_ok=True)

    count = db.query(func.count(Chunk.id)).filter(Chunk.document_id == document.id).scalar()
    return _document_out(document, chunk_count=count or 0)


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    result = []
    for doc in docs:
        count = db.query(func.count(Chunk.id)).filter(Chunk.document_id == doc.id).scalar()
        result.append(_document_out(doc, chunk_count=count or 0))
    return result


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    count = db.query(func.count(Chunk.id)).filter(Chunk.document_id == doc.id).scalar()
    return _document_out(doc, chunk_count=count or 0)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    delete_document_files(document_id)
    db.delete(doc)
    db.commit()
    return None
