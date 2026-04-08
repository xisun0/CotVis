from __future__ import annotations

from pathlib import Path

from realtime_asr.document.markdown import parse_markdown_text
from realtime_asr.document.models import Document


def load_document(path: Path) -> Document:
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")
    if path.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("Phase 0 supports only .md and .txt documents.")

    text = path.read_text(encoding="utf-8")
    paragraphs = parse_markdown_text(text)
    return Document(path=path, paragraphs=paragraphs, raw_text=text)
