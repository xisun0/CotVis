from __future__ import annotations

import re


def canonical_id(raw: str) -> str:
    text = str(raw).strip().lower()
    if not text:
        return ""
    text = re.sub(r"[‐‑‒–—−]+", "-", text)
    text = re.sub(r"[^\w\s-]+", " ", text)
    text = re.sub(r"[-\s]+", "_", text)
    text = text.strip("_")
    if not text:
        return ""
    tokens = [tok for tok in text.split("_") if tok]
    norm_tokens = [_normalize_token(tok) for tok in tokens]
    return "_".join(tok for tok in norm_tokens if tok)


def _normalize_token(token: str) -> str:
    if not token:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
        return token[:-1]
    return token


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
