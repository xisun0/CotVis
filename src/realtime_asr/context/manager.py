from __future__ import annotations

import time
from collections import deque

from realtime_asr.context.tokenizer import count_tokens
from realtime_asr.events import TopTermsEvent, TranscriptEvent


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

    def on_event(self, event: TranscriptEvent) -> None:
        if event.is_final:
            if event.text.strip():
                self.stable_segments.append((event.ts, event.text.strip()))
            self.ephemeral_text = ""
            self.ephemeral_ts = 0.0
            return

        self.ephemeral_text = event.text.strip()
        self.ephemeral_ts = event.ts

    def compute_top_terms(self, now_ts: float | None = None) -> TopTermsEvent:
        now = now_ts if now_ts is not None else time.time()
        final_cutoff = now - float(self.final_window_sec)

        while self.stable_segments and self.stable_segments[0][0] < final_cutoff:
            self.stable_segments.popleft()

        final_counts = count_tokens(text for _, text in self.stable_segments)
        merged: dict[str, float] = {
            token: count * self.final_weight for token, count in final_counts.items()
        }

        if self.ephemeral_text and (now - self.ephemeral_ts) <= self.partial_window_sec:
            partial_counts = count_tokens([self.ephemeral_text])
            for token, count in partial_counts.items():
                merged[token] = merged.get(token, 0.0) + (count * self.partial_weight)

        top_terms = sorted(merged.items(), key=lambda item: item[1], reverse=True)[: self.top_k]

        return TopTermsEvent(
            ts=now,
            window_sec=self.final_window_sec,
            top_k=self.top_k,
            terms=top_terms,
        )
