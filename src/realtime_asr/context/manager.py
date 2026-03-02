from __future__ import annotations

import time
import re
from collections import deque
from threading import Lock

from realtime_asr.context.tokenizer import count_tokens
from realtime_asr.events import TopTermsEvent, TranscriptEvent
from realtime_asr.lm import LanguageModelScorer
from realtime_asr.lm.llm_reranker import LocalLLMReranker


class ContextManager:
    def __init__(
        self,
        final_window_sec: int = 60,
        partial_window_sec: int = 10,
        top_k: int = 60,
        final_weight: float = 1.0,
        partial_weight: float = 0.3,
        llm_reranker: LocalLLMReranker | None = None,
        llm_interval_sec: float = 12.0,
        llm_weight: float = 2.0,
        llm_top_k: int = 30,
        llm_primary: bool = False,
        llm_only: bool = False,
        enable_lm_rescoring: bool = True,
        enable_phrase_scoring: bool = True,
    ) -> None:
        self.final_window_sec = final_window_sec
        self.partial_window_sec = partial_window_sec
        self.top_k = top_k
        self.final_weight = final_weight
        self.partial_weight = partial_weight

        self.stable_segments: deque[tuple[float, str]] = deque()
        self.ephemeral_text = ""
        self.ephemeral_ts = 0.0
        self.last_full_text = ""
        self._lock = Lock()
        self._lm_scorer = LanguageModelScorer(lang="en")
        self._llm_reranker = llm_reranker
        self._llm_interval_sec = llm_interval_sec
        self._llm_weight = llm_weight
        self._llm_top_k = llm_top_k
        self._llm_primary = llm_primary
        self._llm_only = llm_only
        self._enable_lm_rescoring = enable_lm_rescoring
        self._enable_phrase_scoring = enable_phrase_scoring
        self._last_llm_ts = 0.0
        self._llm_cache: dict[str, float] = {}

    def on_event(self, event: TranscriptEvent) -> None:
        text = event.text.strip()
        if not text:
            return

        with self._lock:
            if event.is_final:
                new_text = self._extract_new_stable_text(text)
                if new_text:
                    self.stable_segments.append((event.ts, new_text))
                self.last_full_text = text
                self.ephemeral_text = ""
                self.ephemeral_ts = 0.0
                return

            self.ephemeral_text = self._extract_partial_tail(text)
            self.ephemeral_ts = event.ts

    def compute_top_terms(self, now_ts: float | None = None) -> TopTermsEvent:
        now = now_ts if now_ts is not None else time.time()
        final_cutoff = now - float(self.final_window_sec) if self.final_window_sec > 0 else None

        with self._lock:
            if final_cutoff is not None:
                while self.stable_segments and self.stable_segments[0][0] < final_cutoff:
                    self.stable_segments.popleft()

            final_texts = [text for _, text in self.stable_segments]
            merged: dict[str, float] = {}
            if not self._llm_only:
                final_counts = count_tokens(final_texts)
                merged = {
                    token: count * self.final_weight for token, count in final_counts.items()
                }

            phrase_texts = list(final_texts)
            if self.ephemeral_text and (now - self.ephemeral_ts) <= self.partial_window_sec:
                if not self._llm_only:
                    partial_counts = count_tokens([self.ephemeral_text])
                    for token, count in partial_counts.items():
                        merged[token] = merged.get(token, 0.0) + (count * self.partial_weight)
                phrase_texts.append(self.ephemeral_text)

            if (not self._llm_only) and self._enable_lm_rescoring:
                merged = self._lm_scorer.rescore_tokens(merged)
            if (not self._llm_only) and (not self._llm_primary) and self._enable_phrase_scoring:
                for phrase, score in self._lm_scorer.phrase_scores(phrase_texts).items():
                    merged[phrase] = merged.get(phrase, 0.0) + score
            llm_cache = dict(self._llm_cache)

        now_for_llm = time.time()
        if (
            self._llm_reranker is not None
            and (now_for_llm - self._last_llm_ts) >= self._llm_interval_sec
        ):
            try:
                llm_scores = self._llm_reranker.suggest_scores(
                    texts=phrase_texts,
                    base_terms=merged,
                    top_k=min(self.top_k, self._llm_top_k),
                )
                with self._lock:
                    self._llm_cache = llm_scores
                llm_cache = llm_scores
                self._last_llm_ts = now_for_llm
            except Exception:
                pass

        if self._llm_only:
            merged = dict(llm_cache)
        elif self._llm_primary and llm_cache:
            # In primary mode, concept terms from LLM become the ranking backbone.
            # Keep weights in 0..1-ish range for semantic confidence readability.
            merged = {term: s for term, s in llm_cache.items()}
        else:
            for term, s in llm_cache.items():
                merged[term] = merged.get(term, 0.0) + (s * self._llm_weight)

        top_terms = sorted(merged.items(), key=lambda item: item[1], reverse=True)[: self.top_k]

        return TopTermsEvent(
            ts=now,
            window_sec=self.final_window_sec,
            top_k=self.top_k,
            terms=top_terms,
        )

    def _extract_new_stable_text(self, full_text: str) -> str:
        previous = self.last_full_text
        if not previous:
            return full_text
        if full_text == previous:
            return ""
        delta = self._extract_aligned_suffix(previous, full_text)
        return delta

    def _extract_partial_tail(self, full_text: str) -> str:
        if not self.last_full_text:
            return full_text
        return self._extract_aligned_suffix(self.last_full_text, full_text)

    def _extract_aligned_suffix(self, previous_text: str, current_text: str) -> str:
        previous_tokens = self._split_words(previous_text)
        current_tokens = self._split_words(current_text)
        if not current_tokens:
            return ""
        if not previous_tokens:
            return " ".join(current_tokens).strip()

        normalized_previous = [self._normalize_word(t) for t in previous_tokens]
        normalized_current = [self._normalize_word(t) for t in current_tokens]
        matched_current_indices = self._lcs_current_indices(
            normalized_previous,
            normalized_current,
        )
        if not matched_current_indices:
            return " ".join(current_tokens).strip()

        last_matched_idx = matched_current_indices[-1]
        if last_matched_idx >= len(current_tokens) - 1:
            return ""
        return " ".join(current_tokens[last_matched_idx + 1 :]).strip()

    @staticmethod
    def _split_words(text: str) -> list[str]:
        # Keep alphanumeric/' tokens and Han chunks for robust multilingual diffing.
        return re.findall(r"[A-Za-z0-9']+|[\u4e00-\u9fff]+", text)

    @staticmethod
    def _normalize_word(token: str) -> str:
        if token.isascii():
            return token.lower()
        return token

    @staticmethod
    def _lcs_current_indices(previous: list[str], current: list[str]) -> list[int]:
        n = len(previous)
        m = len(current)
        if n == 0 or m == 0:
            return []

        dp = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            pi = previous[i - 1]
            for j in range(1, m + 1):
                if pi == current[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    left = dp[i][j - 1]
                    up = dp[i - 1][j]
                    dp[i][j] = left if left >= up else up

        indices: list[int] = []
        i = n
        j = m
        while i > 0 and j > 0:
            if previous[i - 1] == current[j - 1]:
                indices.append(j - 1)
                i -= 1
                j -= 1
            elif dp[i - 1][j] >= dp[i][j - 1]:
                i -= 1
            else:
                j -= 1
        indices.reverse()
        return indices
