import json
import logging
import time
from typing import List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk, Document
from app.services.embeddings_store import bytes_to_embedding, cosine_similarity
from app.services.llm import active_embed_model_label, embed_text
from app.services.observability import span_retrieval

logger = logging.getLogger(__name__)


async def retrieve_chunks(
    db: Session,
    document_id: int,
    query: str,
    session_id: Optional[int] = None,
) -> List[Chunk]:
    t0 = time.perf_counter()
    doc = db.get(Document, document_id)
    current_model = active_embed_model_label()
    if doc and doc.embedding_model and doc.embedding_model != current_model:
        raise ValueError(
            f"Document was indexed with {doc.embedding_model} but current provider is "
            f"{current_model}. Delete and re-upload the document."
        )

    chunks = (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id, Chunk.embedding.isnot(None))
        .order_by(Chunk.chunk_index)
        .all()
    )
    if not chunks:
        logger.warning("No chunks for document_id=%s", document_id)
        return []

    query_vec = np.array(await embed_text(query), dtype=np.float32)
    matrix = np.stack([bytes_to_embedding(c.embedding) for c in chunks if c.embedding])
    if matrix.shape[1] != query_vec.shape[0]:
        raise ValueError(
            "Embedding dimension mismatch. Re-upload the document after changing OpenAI/Ollama settings."
        )
    scores = cosine_similarity(query_vec, matrix)
    k = min(settings.top_k_chunks, len(chunks))
    top_indices = np.argsort(scores)[::-1][:k]
    selected = [chunks[i] for i in top_indices]
    score_list = [round(float(scores[i]), 3) for i in top_indices]
    logger.info(
        "Retrieved top_%s chunks for document_id=%s in %.2fs (scores=%s)",
        k,
        document_id,
        time.perf_counter() - t0,
        score_list,
    )
    if session_id is not None:
        span_retrieval(
            session_id=session_id,
            document_id=document_id,
            query=query,
            chunk_indices=[c.chunk_index for c in selected],
            scores=score_list,
            embedding_model=current_model or active_embed_model_label(),
        )
    return selected


def build_rag_messages(
    user_message: str,
    chunks: list[Chunk],
    history: list[tuple[str, str]],
) -> list[dict[str, str]]:
    context_blocks: list[str] = []
    for i, ch in enumerate(chunks, start=1):
        meta = ""
        if ch.metadata_json:
            try:
                m = json.loads(ch.metadata_json)
                if "pages" in m:
                    meta = f" (pages: {', '.join(str(p) for p in m['pages'])})"
            except json.JSONDecodeError:
                pass
        context_blocks.append(f"[{i}]{meta}\n{ch.content}")

    context = "\n\n---\n\n".join(context_blocks) if context_blocks else "(no context retrieved)"

    system = (
        "You are a helpful assistant that answers questions about the user's document. "
        "Use only the provided context. If the answer is not in the context, say you "
        "cannot find it in the document. Cite context numbers like [1] when relevant.\n\n"
        f"Context:\n{context}"
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for role, content in history:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages
