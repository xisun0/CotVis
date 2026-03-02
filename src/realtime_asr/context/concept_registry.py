from __future__ import annotations

import re


def canonical_id(raw: str) -> str:
    text = str(raw).strip().lower()
    if not text:
        return ""
    text = re.sub(r"[‐‑‒–—−]+", "-", text)
    text = re.sub(r"[^\w\s-]+", " ", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text.strip("_")


class ConceptRegistry:
    def __init__(self) -> None:
        self._display_by_id: dict[str, str] = {}

    def register(self, raw: str) -> str:
        cid = canonical_id(raw)
        if not cid:
            return ""
        self._display_by_id[cid] = str(raw).strip() or cid
        return cid

    def display(self, concept_id: str) -> str:
        return self._display_by_id.get(concept_id, concept_id)
