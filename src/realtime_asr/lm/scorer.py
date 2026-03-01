from __future__ import annotations

from collections import Counter
from typing import Iterable

from realtime_asr.context.tokenizer import tokenize

try:
    from wordfreq import zipf_frequency
except Exception:  # pragma: no cover
    zipf_frequency = None

FUNCTION_WORDS = {
    "i", "we", "you", "he", "she", "they", "it",
    "me", "us", "them", "my", "our", "your", "their",
    "this", "that", "these", "those",
    "is", "am", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had",
    "can", "could", "may", "might", "must", "shall", "should", "will", "would",
}


class LanguageModelScorer:
    """Downweight high-frequency function words using corpus frequency.

    This is a lightweight local scorer (no cloud API). It rescales token counts
    by how common the word is in general English and adds phrase-level signals.
    """

    def __init__(self, lang: str = "en") -> None:
        self.lang = lang

    def rescore_tokens(self, counts: dict[str, float]) -> dict[str, float]:
        rescored: dict[str, float] = {}
        for token, value in counts.items():
            factor = self._content_factor(token)
            score = value * factor
            if score > 0.0:
                rescored[token] = score
        return rescored

    def phrase_scores(self, texts: Iterable[str], base_weight: float = 0.9) -> dict[str, float]:
        phrase_counts: Counter[str] = Counter()
        for text in texts:
            toks = tokenize(text)
            if len(toks) < 2:
                continue
            for a, b in zip(toks, toks[1:]):
                if not self._phrase_token_ok(a) or not self._phrase_token_ok(b):
                    continue
                phrase = f"{a} {b}"
                phrase_counts[phrase] += 1

        scores: dict[str, float] = {}
        for phrase, count in phrase_counts.items():
            scores[phrase] = base_weight * float(count)
        return scores

    def _content_factor(self, token: str) -> float:
        if not token:
            return 0.0
        if any("\u4e00" <= ch <= "\u9fff" for ch in token):
            return 1.0
        if token in FUNCTION_WORDS:
            return 0.12
        if zipf_frequency is None:
            return 1.0

        zf = float(zipf_frequency(token, self.lang))
        if zf <= 0:
            return 1.25

        # High-zipf words (very common) get downweighted aggressively.
        # Examples: "we", "should", "this".
        raw = (7.0 - zf) / 3.5
        if raw < 0.05:
            return 0.05
        if raw > 1.4:
            return 1.4
        return raw

    def _phrase_token_ok(self, token: str) -> bool:
        if len(token) <= 2:
            return False
        if any("\u4e00" <= ch <= "\u9fff" for ch in token):
            return len(token) >= 2
        return token.isalpha()
