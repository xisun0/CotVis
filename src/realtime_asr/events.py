from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ReviewInstruction:
    raw_text: str
    intent: str
    constraints: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReviewCandidate:
    version_id: int
    text: str
    rationale: str
