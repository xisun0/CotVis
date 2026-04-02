from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Diagnosis:
    summary: str


def diagnose_text(text: str) -> Diagnosis:
    if not text.strip():
        return Diagnosis(summary="No text selected for review.")
    return Diagnosis(summary="Phase 0 placeholder: diagnosis is not implemented yet.")
