from __future__ import annotations

from realtime_asr.document.models import Document, Paragraph


def locate_start_paragraph(
    document: Document,
    paragraph_index: int = 1,
    match_text: str | None = None,
) -> Paragraph:
    if not document.paragraphs:
        raise ValueError("Document has no readable paragraphs.")

    if match_text:
        lowered = match_text.lower()
        for paragraph in document.paragraphs:
            if paragraph.readable and lowered in paragraph.text.lower():
                return paragraph
        raise ValueError(f"No paragraph contains: {match_text}")

    preferred = document.primary_paragraphs or document.readable_paragraphs
    if not preferred:
        raise ValueError("Document has no readable paragraphs.")

    target = max(1, paragraph_index)
    if target > len(preferred):
        raise ValueError(f"Preferred paragraph index out of range: {target}")
    return preferred[target - 1]
