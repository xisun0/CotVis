from __future__ import annotations

from typing import Callable

from realtime_asr.asr_backend.base import ASRBackend
from realtime_asr.events import TranscriptEvent


class MacSpeechBackend(ASRBackend):
    """macOS Speech Framework backend (TODO)."""

    def __init__(self, lang: str = "en-US") -> None:
        self.lang = lang
        self._running = False

    def start(self, callback: Callable[[TranscriptEvent], None]) -> None:
        raise NotImplementedError("MacSpeechBackend is not implemented yet.")

    def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running
