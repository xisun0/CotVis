from __future__ import annotations

import re

from realtime_asr.document.models import Paragraph, Sentence


def parse_markdown_text(text: str) -> list[Paragraph]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    raw_paragraphs = split_markdown_blocks(normalized)
    paragraphs: list[Paragraph] = []
    for paragraph_index, paragraph_text in enumerate(raw_paragraphs, start=1):
        paragraph_id = f"p{paragraph_index}"
        kind = classify_paragraph(paragraph_text)
        reading_priority = classify_reading_priority(kind, paragraph_text)
        readable = reading_priority in {"primary", "secondary"}
        sentences = [
            Sentence(
                id=f"{paragraph_id}s{sentence_index}",
                index=sentence_index,
                text=sentence_text,
            )
            for sentence_index, sentence_text in enumerate(
                split_sentences(paragraph_text),
                start=1,
            )
        ] if readable else []
        paragraphs.append(
            Paragraph(
                id=paragraph_id,
                index=paragraph_index,
                kind=kind,
                text=paragraph_text,
                readable=readable,
                reading_priority=reading_priority,
                skip_reason=None if readable else explain_skip(kind, paragraph_text),
                sentences=sentences,
            )
        )
    return paragraphs


def split_markdown_blocks(text: str) -> list[str]:
    lines = text.split("\n")
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    fence_marker = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                if current:
                    blocks.append("\n".join(current).strip())
                    current = []
                in_fence = True
                fence_marker = marker
                current.append(line)
            else:
                current.append(line)
                blocks.append("\n".join(current).strip())
                current = []
                in_fence = False
                fence_marker = ""
            continue

        if in_fence:
            current.append(line)
            continue

        if not stripped:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue

        current.append(line)

    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def split_sentences(text: str) -> list[str]:
    sanitized = re.sub(r"\s+", " ", text.strip())
    sanitized = re.sub(r"(?i)\b(e\.g|i\.e|mr|mrs|ms|dr|prof|fig|eq|sec|u\.s)\.", lambda m: m.group(0).replace(".", "<DOT>"), sanitized)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])", sanitized)
    if len(parts) == 1:
        parts = re.split(r"(?<=[.!?])\s+", sanitized)
    restored = [part.replace("<DOT>", ".").strip() for part in parts]
    return [part for part in restored if part]


def classify_paragraph(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "blank"
    if re.fullmatch(r"<[^>]+>", stripped):
        return "html_block"
    if stripped.startswith("```") or stripped.startswith("~~~"):
        return "code_fence"
    if stripped.startswith("#"):
        return "heading"
    if stripped.startswith((">", "&gt;")):
        return "blockquote"
    if re.match(r"^[-*+]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
        return "list_item"
    if re.fullmatch(r"[-*_]{3,}", stripped):
        return "rule"
    if re.fullmatch(r"\*\*[^*]+\*\*(\s{2,}.*)?", stripped):
        return "metadata"
    if looks_like_centered_metadata(stripped):
        return "metadata"
    if looks_like_html_wrapper(stripped):
        return "html_wrapper"
    return "paragraph"


def classify_reading_priority(kind: str, text: str) -> str:
    if kind == "paragraph":
        if looks_like_front_matter_metadata(text):
            return "secondary"
        return "primary" if has_readable_text(text) else "skip"
    if kind in {"blockquote", "list_item"}:
        return "secondary" if has_readable_text(text) else "skip"
    return "skip"


def explain_skip(kind: str, text: str) -> str:
    if kind in {"html_block", "html_wrapper"}:
        return "html wrapper"
    if kind == "heading":
        return "heading kept out of reading flow"
    if kind == "rule":
        return "separator"
    if kind == "code_fence":
        return "code block"
    if kind == "metadata":
        return "metadata line"
    if not has_readable_text(text):
        return "not enough prose content"
    return f"non-readable {kind}"


def looks_like_html_wrapper(text: str) -> bool:
    return text.startswith("<div ") or text.startswith("</div>")


def looks_like_centered_metadata(text: str) -> bool:
    prose = re.sub(r"<[^>]+>", " ", text)
    prose = re.sub(r"[*_`~]", "", prose).strip()
    if not prose:
        return True
    word_count = len(prose.split())
    if word_count > 14:
        return False
    if any(mark in prose for mark in ".?!:;"):
        return False
    return True


def looks_like_front_matter_metadata(text: str) -> bool:
    prose = re.sub(r"<[^>]+>", " ", text)
    prose = re.sub(r"\s+", " ", prose).strip()
    lowered = prose.lower()
    markers = [
        "@",
        "keywords:",
        "jel classification:",
        "zhiguo he is at",
        "yiming qian is at",
        "xi sun is at",
        "wang renxuan is at",
    ]
    return any(marker in lowered for marker in markers)


def has_readable_text(text: str) -> bool:
    prose = re.sub(r"<[^>]+>", " ", text)
    prose = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", prose)
    prose = re.sub(r"^\s*>\s?", "", prose, flags=re.MULTILINE)
    prose = re.sub(r"^\s*[-*+]\s+", "", prose, flags=re.MULTILINE)
    prose = re.sub(r"^\s*\d+\.\s+", "", prose, flags=re.MULTILINE)
    prose = re.sub(r"\s+", " ", prose).strip()
    alpha_count = sum(ch.isalpha() for ch in prose)
    return alpha_count >= 3
