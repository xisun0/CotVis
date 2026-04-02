from __future__ import annotations

import shutil
import subprocess


class TextToSpeechBackend:
    def speak(self, _text: str, interruptible: bool = True) -> None:
        raise NotImplementedError("TTS adapter is introduced after Phase 0.")


class NullTextToSpeech(TextToSpeechBackend):
    def speak(self, _text: str, interruptible: bool = True) -> None:
        return None


class ConsoleTextToSpeech(TextToSpeechBackend):
    def speak(self, text: str, interruptible: bool = True) -> None:
        del interruptible
        print(f"[speak] {text}")


class SystemTextToSpeech(TextToSpeechBackend):
    def __init__(self, voice: str | None = None) -> None:
        self.voice = voice

    def speak(self, text: str, interruptible: bool = True) -> None:
        del interruptible
        if shutil.which("say") is None:
            raise RuntimeError("macOS `say` command is not available.")
        cmd = ["say"]
        if self.voice:
            cmd.extend(["-v", self.voice])
        cmd.append(text)
        subprocess.run(cmd, check=True)
