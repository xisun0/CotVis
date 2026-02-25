from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from realtime_asr.events import TranscriptEvent


class ASRBackend(ABC):
    @abstractmethod
    def start(self, callback: Callable[[TranscriptEvent], None]) -> None:
        """Start streaming ASR events and invoke callback for each event."""

    @abstractmethod
    def stop(self) -> None:
        """Stop ASR streaming and release resources."""

    @abstractmethod
    def is_running(self) -> bool:
        """Return whether the backend is currently running."""
