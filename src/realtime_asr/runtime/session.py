from __future__ import annotations

from dataclasses import dataclass

from realtime_asr.document.locator import locate_start_paragraph
from realtime_asr.document.models import Document, Paragraph
from realtime_asr.runtime.state_machine import SessionState


@dataclass(slots=True)
class ReadingAnchor:
    paragraph_id: str
    sentence_id: str | None
    fallback_direction: str
    last_known_paragraph_index: int
    last_known_sentence_index: int | None


@dataclass(slots=True)
class ReviewSession:
    document: Document
    state: SessionState
    anchor: ReadingAnchor

    @classmethod
    def start(
        cls,
        document: Document,
        start_paragraph: int = 1,
        match_text: str | None = None,
    ) -> "ReviewSession":
        paragraph = locate_start_paragraph(
            document=document,
            paragraph_index=start_paragraph,
            match_text=match_text,
        )
        return cls(
            document=document,
            state=SessionState.LOCATING_START,
            anchor=ReadingAnchor(
                paragraph_id=paragraph.id,
                sentence_id=paragraph.sentences[0].id if paragraph.sentences else None,
                fallback_direction="forward",
                last_known_paragraph_index=paragraph.index,
                last_known_sentence_index=paragraph.sentences[0].index if paragraph.sentences else None,
            ),
        )

    @property
    def current_paragraph(self) -> Paragraph:
        return self.document.get_paragraph_by_id(self.anchor.paragraph_id)
