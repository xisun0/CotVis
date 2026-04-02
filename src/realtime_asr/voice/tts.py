from __future__ import annotations


class TextToSpeechBackend:
    def speak(self, _text: str, interruptible: bool = True) -> None:
        raise NotImplementedError("TTS adapter is introduced after Phase 0.")


class NullTextToSpeech(TextToSpeechBackend):
    def speak(self, _text: str, interruptible: bool = True) -> None:
        return None
