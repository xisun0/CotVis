from __future__ import annotations

from dataclasses import dataclass, field

from realtime_asr.events import ReviewCandidate, ReviewInstruction
from realtime_asr.runtime.state_machine import SessionState


@dataclass(slots=True)
class ReviewTarget:
    target_type: str
    paragraph_id: str
    sentence_id: str | None
    source_text: str
    section_label: str = ""
    document_overview: str = ""


@dataclass(slots=True)
class ReviewCycle:
    target: ReviewTarget
    request_text: str
    instruction: ReviewInstruction
    candidates: list[ReviewCandidate] = field(default_factory=list)
    working_text: str = ""
    proposed_text: str = ""
    return_state: SessionState = SessionState.READING
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    round_index: int = 1
