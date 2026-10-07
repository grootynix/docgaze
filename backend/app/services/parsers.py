from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

from pypdf import PdfReader


@dataclass
class TextSegment:
    text: str
    metadata: Dict[str, Union[str, int]]


def parse_file(file_path: Path, content_type: Optional[str], filename: str) -> List[TextSegment]:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf" or (content_type and "pdf" in content_type):
        return _parse_pdf(file_path)
    if suffix in (".txt", ".md") or (content_type and "text" in content_type):
        return _parse_plain(file_path)
    raise ValueError(f"Unsupported file type: {filename}")


def _parse_plain(file_path: Path) -> List[TextSegment]:
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return [TextSegment(text=text.strip(), metadata={})]


def _parse_pdf(file_path: Path) -> List[TextSegment]:
    reader = PdfReader(str(file_path))
    segments: List[TextSegment] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            segments.append(TextSegment(text=text, metadata={"page": i + 1}))
    if not segments:
        raise ValueError("No text could be extracted from the PDF")
    return segments
