from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Sentence:
    id: str
    index: int
    text: str


@dataclass(slots=True)
class Paragraph:
    id: str
    index: int
    kind: str
    text: str
    readable: bool
    reading_priority: str
    skip_reason: str | None = None
    sentences: list[Sentence] = field(default_factory=list)


@dataclass(slots=True)
class Document:
    path: Path
    paragraphs: list[Paragraph]

    @property
    def readable_paragraphs(self) -> list[Paragraph]:
        return [paragraph for paragraph in self.paragraphs if paragraph.readable]

    @property
    def primary_paragraphs(self) -> list[Paragraph]:
        return [paragraph for paragraph in self.paragraphs if paragraph.reading_priority == "primary"]

    @property
    def secondary_paragraphs(self) -> list[Paragraph]:
        return [paragraph for paragraph in self.paragraphs if paragraph.reading_priority == "secondary"]

    def get_paragraph_by_id(self, paragraph_id: str) -> Paragraph:
        for paragraph in self.paragraphs:
            if paragraph.id == paragraph_id:
                return paragraph
        raise KeyError(f"Unknown paragraph id: {paragraph_id}")

    def kind_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for paragraph in self.paragraphs:
            counts[paragraph.kind] = counts.get(paragraph.kind, 0) + 1
        return counts
