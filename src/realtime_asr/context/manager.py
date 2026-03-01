from __future__ import annotations

import time
from collections import deque
from threading import Lock

from realtime_asr.context.tokenizer import count_tokens
from realtime_asr.events import TopTermsEvent, TranscriptEvent
from realtime_asr.lm import LanguageModelScorer


class ContextManager:
    def __init__(
        self,
        final_window_sec: int = 60,
        partial_window_sec: int = 10,
        top_k: int = 60,
        final_weight: float = 1.0,
        partial_weight: float = 0.3,
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
        final_cutoff = now - float(self.final_window_sec)

        with self._lock:
            while self.stable_segments and self.stable_segments[0][0] < final_cutoff:
                self.stable_segments.popleft()

            final_texts = [text for _, text in self.stable_segments]
            final_counts = count_tokens(final_texts)
            merged: dict[str, float] = {
                token: count * self.final_weight for token, count in final_counts.items()
            }

            phrase_texts = list(final_texts)
            if self.ephemeral_text and (now - self.ephemeral_ts) <= self.partial_window_sec:
                partial_counts = count_tokens([self.ephemeral_text])
                for token, count in partial_counts.items():
                    merged[token] = merged.get(token, 0.0) + (count * self.partial_weight)
                phrase_texts.append(self.ephemeral_text)

            merged = self._lm_scorer.rescore_tokens(merged)
            for phrase, score in self._lm_scorer.phrase_scores(phrase_texts).items():
                merged[phrase] = merged.get(phrase, 0.0) + score

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
        if full_text.startswith(previous):
            return full_text[len(previous) :].strip()
        return full_text

    def _extract_partial_tail(self, full_text: str) -> str:
        if not self.last_full_text:
            return full_text
        if full_text.startswith(self.last_full_text):
            return full_text[len(self.last_full_text) :].strip()
        return full_text
