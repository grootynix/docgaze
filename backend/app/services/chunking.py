import json
from dataclasses import dataclass
from typing import List, Optional

from app.config import settings
from app.services.parsers import TextSegment


@dataclass
class ChunkDraft:
    content: str
    chunk_index: int
    metadata_json: Optional[str]


def chunk_segments(segments: List[TextSegment]) -> List[ChunkDraft]:
    full_parts: List[tuple] = []
    for seg in segments:
        full_parts.append((seg.text, seg.metadata))

    combined = "\n\n".join(t[0] for t in full_parts)
    if not combined.strip():
        return []

    size = settings.chunk_size
    overlap = settings.chunk_overlap
    chunks: List[ChunkDraft] = []
    start = 0
    idx = 0
    while start < len(combined):
        end = min(start + size, len(combined))
        piece = combined[start:end].strip()
        if piece:
            meta = _metadata_for_range(full_parts, start, end)
            chunks.append(
                ChunkDraft(
                    content=piece,
                    chunk_index=idx,
                    metadata_json=json.dumps(meta) if meta else None,
                )
            )
            idx += 1
        if end >= len(combined):
            break
        start = end - overlap
        if start < 0:
            start = 0

    return chunks


def _metadata_for_range(
    parts: List[tuple],
    start: int,
    end: int,
) -> dict:
    """Best-effort page hint from segment boundaries."""
    offset = 0
    pages: set[int] = set()
    for text, meta in parts:
        seg_start = offset
        seg_end = offset + len(text) + 2
        if seg_end > start and seg_start < end:
            page = meta.get("page")
            if isinstance(page, int):
                pages.add(page)
        offset = seg_end
    if pages:
        return {"pages": sorted(pages)}
    return {}
