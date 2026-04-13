from __future__ import annotations

import io
import os
import wave
from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(slots=True)
class SpeechTurn:
    transcript: str
    is_final: bool = True
    source: str = "typed"


class SpeechToTextBackend:
    def capture_turn(self) -> SpeechTurn | None:
        raise NotImplementedError


class TypedTurnAsr(SpeechToTextBackend):
    def __init__(
        self,
        input_func: Callable[[str], str] = input,
        prompt: str = "[listening] speak now> ",
    ) -> None:
        self._input = input_func
        self._prompt = prompt

    def capture_turn(self) -> SpeechTurn | None:
        try:
            transcript = self._input(self._prompt)
        except EOFError:
            return None
        text = transcript.strip()
        if not text:
            return None
        return SpeechTurn(transcript=text, is_final=True, source="typed")


class OpenAITurnAsr(SpeechToTextBackend):
    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini-transcribe",
        language: str | None = None,
        sample_rate: int = 16000,
        channels: int = 1,
        max_record_seconds: float = 6.0,
        silence_seconds_to_stop: float = 0.8,
        energy_threshold: float = 0.015,
        chunk_seconds: float = 0.25,
        stream_latency: str | float = "high",
    ) -> None:
        self.model = model
        self.language = language
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_record_seconds = max_record_seconds
        self.silence_seconds_to_stop = silence_seconds_to_stop
        self.energy_threshold = energy_threshold
        self.chunk_seconds = chunk_seconds
        self.stream_latency = stream_latency

    def capture_turn(self) -> SpeechTurn | None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("sounddevice is required for microphone capture") from exc

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required for OpenAI ASR") from exc

        print(
            f"[listening] recording until silence "
            f"(max {self.max_record_seconds:.1f}s, stop after {self.silence_seconds_to_stop:.1f}s silence) "
            f"at {self.sample_rate} Hz..."
        )
        recording = _record_until_silence(
            sd=sd,
            sample_rate=self.sample_rate,
            channels=self.channels,
            max_record_seconds=self.max_record_seconds,
            silence_seconds_to_stop=self.silence_seconds_to_stop,
            energy_threshold=self.energy_threshold,
            chunk_seconds=self.chunk_seconds,
            stream_latency=self.stream_latency,
        )
        if recording is None:
            return None

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(recording.tobytes())
        audio_bytes = buffer.getvalue()

        client = OpenAI(api_key=api_key)
        transcript = client.audio.transcriptions.create(
            model=self.model,
            file=("command.wav", audio_bytes, "audio/wav"),
            language=self.language,
        )

        text = getattr(transcript, "text", "") or ""
        text = text.strip()
        if not text:
            return None
        return SpeechTurn(transcript=text, is_final=True, source="openai")


def _record_until_silence(
    *,
    sd,
    sample_rate: int,
    channels: int,
    max_record_seconds: float,
    silence_seconds_to_stop: float,
    energy_threshold: float,
    chunk_seconds: float,
    stream_latency,
):
    chunk_frames = max(1, int(sample_rate * chunk_seconds))
    max_frames = int(sample_rate * max_record_seconds)
    silence_chunks_to_stop = max(1, int(silence_seconds_to_stop / chunk_seconds))

    chunks: list[np.ndarray] = []
    total_frames = 0
    speech_started = False
    trailing_silence_chunks = 0

    with sd.InputStream(
        samplerate=sample_rate,
        channels=channels,
        dtype="float32",
        blocksize=chunk_frames,
        latency=stream_latency,
    ) as stream:
        while total_frames < max_frames:
            chunk, overflowed = stream.read(chunk_frames)
            total_frames += len(chunk)
            chunks.append(chunk.copy())

            energy = _chunk_energy(chunk)
            if energy >= energy_threshold:
                speech_started = True
                trailing_silence_chunks = 0
            elif speech_started:
                trailing_silence_chunks += 1
                if trailing_silence_chunks >= silence_chunks_to_stop:
                    break

    if not speech_started:
        return None

    audio = np.concatenate(chunks, axis=0)
    audio = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio * 32767.0).astype(np.int16)
    return audio_int16


def _chunk_energy(chunk: np.ndarray) -> float:
    if chunk.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(chunk, dtype=np.float32))))
