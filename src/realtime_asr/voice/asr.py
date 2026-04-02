from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SpeechTurn:
    transcript: str
    is_final: bool = True


class SpeechToTextBackend:
    def transcribe_turn(self, _audio_chunk: bytes) -> SpeechTurn:
        raise NotImplementedError("ASR adapter is introduced after Phase 0.")
