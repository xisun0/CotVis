from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PatchTarget:
    target_type: str
    paragraph_id: str
    sentence_id: str | None = None


@dataclass(slots=True)
class TextPatch:
    target: PatchTarget
    operation: str
    original: str
    replacement: str


def plan_patch(
    *,
    target_type: str,
    paragraph_id: str,
    original: str,
    replacement: str,
    sentence_id: str | None = None,
    operation: str = "replace",
) -> TextPatch:
    return TextPatch(
        target=PatchTarget(
            target_type=target_type,
            paragraph_id=paragraph_id,
            sentence_id=sentence_id,
        ),
        operation=operation,
        original=original,
        replacement=replacement,
    )
