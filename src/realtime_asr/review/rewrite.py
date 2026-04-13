from __future__ import annotations

from realtime_asr.events import ReviewCandidate


def rewrite_text(text: str, instruction: str) -> list[ReviewCandidate]:
    return [
        ReviewCandidate(
            version_id=1,
            text=text.strip(),
            rationale=f"Phase 0 placeholder for instruction: {instruction.strip() or 'none'}",
        )
    ]
