from __future__ import annotations

import re
from typing import Iterable

EN_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "with", "i"
}

ZH_STOPWORDS = {"的", "了", "和", "是", "在", "就", "都", "而", "及", "与", "着", "或", "一个"}


def tokenize(text: str) -> list[str]:
    en_tokens = re.findall(r"[a-zA-Z']+", text.lower())
    zh_tokens = re.findall(r"[\u4e00-\u9fff]+", text)
    tokens = [tok for tok in en_tokens if tok not in EN_STOPWORDS]
    tokens.extend(tok for tok in zh_tokens if tok not in ZH_STOPWORDS)
    return tokens


def count_tokens(chunks: Iterable[str]) -> dict[str, float]:
    counts: dict[str, float] = {}
    for chunk in chunks:
        for token in tokenize(chunk):
            counts[token] = counts.get(token, 0.0) + 1.0
    return counts
