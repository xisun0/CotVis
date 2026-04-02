from __future__ import annotations

from realtime_asr.document.models import Document, Paragraph, Sentence


def first_sentence(paragraph: Paragraph) -> Sentence | None:
    if not paragraph.sentences:
        return None
    return paragraph.sentences[0]


def previous_sentence(paragraph: Paragraph, sentence_id: str | None) -> Sentence | None:
    if not paragraph.sentences:
        return None
    if sentence_id is None:
        return None
    for idx, sentence in enumerate(paragraph.sentences):
        if sentence.id == sentence_id:
            if idx == 0:
                return None
            return paragraph.sentences[idx - 1]
    return None


def next_sentence(paragraph: Paragraph, sentence_id: str | None) -> Sentence | None:
    if not paragraph.sentences:
        return None
    if sentence_id is None:
        return paragraph.sentences[0]
    for idx, sentence in enumerate(paragraph.sentences):
        if sentence.id == sentence_id:
            if idx + 1 >= len(paragraph.sentences):
                return None
            return paragraph.sentences[idx + 1]
    return None


def next_readable_paragraph(document: Document, current_index: int) -> Paragraph | None:
    for paragraph in document.paragraphs[current_index:]:
        if paragraph.readable:
            return paragraph
    return None


def previous_readable_paragraph(document: Document, current_index: int) -> Paragraph | None:
    for paragraph in reversed(document.paragraphs[: current_index - 1]):
        if paragraph.readable:
            return paragraph
    return None


def next_readable_paragraph_outside_marker(
    document: Document,
    current_index: int,
    marker_id: str | None,
) -> Paragraph | None:
    if marker_id is None:
        return next_readable_paragraph(document, current_index)
    for paragraph in document.paragraphs[current_index:]:
        if paragraph.readable and marker_id not in paragraph.section_path_ids:
            return paragraph
    return None


def first_readable_paragraph_of_marker_group(
    document: Document,
    paragraph: Paragraph,
    marker_id: str | None,
    *,
    mode: str,
) -> Paragraph:
    candidate = paragraph
    while True:
        previous = previous_readable_paragraph(document, candidate.index)
        if previous is None:
            return candidate
        if mode == "subsection":
            previous_marker = deepest_marker_id(previous)
        else:
            previous_marker = top_marker_id(previous)
        if previous_marker != marker_id:
            return candidate
        candidate = previous


def deepest_marker_id(paragraph: Paragraph) -> str | None:
    if not paragraph.section_path_ids:
        return None
    return paragraph.section_path_ids[-1]


def top_marker_id(paragraph: Paragraph) -> str | None:
    if not paragraph.section_path_ids:
        return None
    return paragraph.section_path_ids[0]
