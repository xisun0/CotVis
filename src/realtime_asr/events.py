from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TranscriptEvent:
    text: str
    is_final: bool
    ts: float
    lang: str | None
    source: str


@dataclass(slots=True)
class TopTermsEvent:
    ts: float
    window_sec: int
    top_k: int
    terms: list[tuple[str, float]]
