from __future__ import annotations

import platform
import threading
import time
from typing import Callable

from realtime_asr.asr_backend.base import ASRBackend
from realtime_asr.events import TranscriptEvent

try:
    import AVFoundation
    import Speech
    from Foundation import NSLocale
except Exception:  # pragma: no cover - import errors are handled at runtime in start()
    AVFoundation = None
    Speech = None
    NSLocale = None


class MacSpeechBackendError(RuntimeError):
    """Raised when macOS speech backend cannot start or continue."""


class MacSpeechBackend(ASRBackend):
    """macOS Speech Framework backend."""

    def __init__(
        self,
        lang: str = "en-US",
        verbose: bool = False,
        silence_finalize_sec: float = 1.8,
    ) -> None:
        self.lang = lang
        self.verbose = verbose
        self.silence_finalize_sec = silence_finalize_sec
        self._callback: Callable[[TranscriptEvent], None] | None = None
        self._running = False
        self._lock = threading.Lock()

        self._audio_engine = None
        self._input_node = None
        self._request = None
        self._recognizer = None
        self._task = None

        self._audio_tap_block = None
        self._result_handler = None

        self._last_error: str | None = None
        self._audio_buffer_count = 0
        self._result_callback_count = 0
        self._last_audio_ts = 0.0
        self._last_result_ts = 0.0
        self._silence_timer: threading.Timer | None = None
        self._latest_partial_text = ""
        self._last_emitted_final_text = ""

    def start(self, callback: Callable[[TranscriptEvent], None]) -> None:
        with self._lock:
            if self._running:
                return
            self._callback = callback
            self._last_error = None

        self._validate_platform()
        self._log(f"Starting macOS speech backend with lang={self.lang}")
        self._ensure_frameworks_available()
        self._ensure_permissions()
        self._start_streaming()
        self._log("Backend started. Listening to microphone input.")

    def get_last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def stop(self) -> None:
        with self._lock:
            self._running = False

        if self._task is not None:
            try:
                self._task.cancel()
            except Exception:
                pass
            self._task = None

        if self._request is not None:
            try:
                self._request.endAudio()
            except Exception:
                pass
            self._request = None

        if self._input_node is not None:
            try:
                self._input_node.removeTapOnBus_(0)
            except Exception:
                pass
            self._input_node = None

        if self._audio_engine is not None:
            try:
                self._audio_engine.stop()
            except Exception:
                pass
            self._audio_engine = None

        self._audio_tap_block = None
        self._result_handler = None
        self._recognizer = None
        self._latest_partial_text = ""
        self._cancel_silence_timer()

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def _validate_platform(self) -> None:
        if platform.system() != "Darwin":
            raise MacSpeechBackendError("MacSpeechBackend requires macOS (Darwin).")

    def _ensure_frameworks_available(self) -> None:
        if AVFoundation is None or Speech is None or NSLocale is None:
            raise MacSpeechBackendError(
                "Missing macOS framework bindings. Run `make setup` on macOS to install pyobjc dependencies."
            )

    def _ensure_permissions(self) -> None:
        speech_status = Speech.SFSpeechRecognizer.authorizationStatus()
        if speech_status == Speech.SFSpeechRecognizerAuthorizationStatusNotDetermined:
            speech_status = self._request_speech_permission()
        if speech_status != Speech.SFSpeechRecognizerAuthorizationStatusAuthorized:
            raise MacSpeechBackendError(
                "Speech recognition permission is not granted. Enable it in System Settings > Privacy & Security > Speech Recognition."
            )

        mic_status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(
            AVFoundation.AVMediaTypeAudio
        )
        if mic_status == AVFoundation.AVAuthorizationStatusNotDetermined:
            mic_status = self._request_mic_permission()
        if mic_status != AVFoundation.AVAuthorizationStatusAuthorized:
            raise MacSpeechBackendError(
                "Microphone permission is not granted. Enable it in System Settings > Privacy & Security > Microphone."
            )

    def _request_speech_permission(self) -> int:
        done = threading.Event()
        result: dict[str, int] = {}

        def handler(status: int) -> None:
            result["status"] = int(status)
            done.set()

        Speech.SFSpeechRecognizer.requestAuthorization_(handler)
        if not done.wait(timeout=15.0):
            raise MacSpeechBackendError("Timed out while requesting speech recognition permission.")
        return result.get("status", Speech.SFSpeechRecognizerAuthorizationStatusDenied)

    def _request_mic_permission(self) -> int:
        done = threading.Event()
        result: dict[str, int] = {}

        def handler(granted: bool) -> None:
            result["status"] = (
                AVFoundation.AVAuthorizationStatusAuthorized
                if granted
                else AVFoundation.AVAuthorizationStatusDenied
            )
            done.set()

        AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            AVFoundation.AVMediaTypeAudio,
            handler,
        )
        if not done.wait(timeout=15.0):
            raise MacSpeechBackendError("Timed out while requesting microphone permission.")
        return result.get("status", AVFoundation.AVAuthorizationStatusDenied)

    def _start_streaming(self) -> None:
        locale = NSLocale.localeWithLocaleIdentifier_(self.lang)
        self._recognizer = Speech.SFSpeechRecognizer.alloc().initWithLocale_(locale)
        if self._recognizer is None:
            raise MacSpeechBackendError(f"Unsupported speech locale: {self.lang}")
        if not self._recognizer.isAvailable():
            raise MacSpeechBackendError("Speech recognizer is currently unavailable.")
        self._log("Speech recognizer is available.")

        self._request = Speech.SFSpeechAudioBufferRecognitionRequest.alloc().init()
        self._request.setShouldReportPartialResults_(True)

        self._audio_engine = AVFoundation.AVAudioEngine.alloc().init()
        self._input_node = self._audio_engine.inputNode()
        if self._input_node is None:
            raise MacSpeechBackendError("No audio input device found.")
        self._log("Audio input node is ready.")

        recording_format = self._input_node.outputFormatForBus_(0)
        self._log(
            "Input format: "
            f"sample_rate={recording_format.sampleRate():.1f}, "
            f"channels={recording_format.channelCount()}"
        )

        def tap_block(buffer, _when) -> None:
            if self._request is not None:
                self._request.appendAudioPCMBuffer_(buffer)
                with self._lock:
                    self._audio_buffer_count += 1
                    self._last_audio_ts = time.time()

        self._audio_tap_block = tap_block
        self._input_node.installTapOnBus_bufferSize_format_block_(
            0,
            1024,
            recording_format,
            self._audio_tap_block,
        )
        self._log("Installed audio tap on input node.")

        def result_handler(result, error) -> None:
            if error is not None:
                self._set_error(f"Speech recognition error: {error}")
                self.stop()
                return
            if result is None:
                return

            with self._lock:
                self._result_callback_count += 1
                self._last_result_ts = time.time()

            text = str(result.bestTranscription().formattedString()).strip()
            if not text:
                return

            is_final = bool(result.isFinal())
            if is_final:
                with self._lock:
                    self._last_emitted_final_text = text
                    self._latest_partial_text = ""
                self._cancel_silence_timer()
            else:
                with self._lock:
                    self._latest_partial_text = text
                self._arm_silence_timer()
            event = TranscriptEvent(
                text=text,
                is_final=is_final,
                ts=time.time(),
                lang=self.lang,
                source="mac_speech",
            )
            cb = self._callback
            if cb is None:
                return
            try:
                cb(event)
            except Exception as exc:
                self._set_error(f"Callback error: {exc}")

        self._result_handler = result_handler
        self._task = self._recognizer.recognitionTaskWithRequest_resultHandler_(
            self._request,
            self._result_handler,
        )
        if self._task is None:
            self.stop()
            raise MacSpeechBackendError("Failed to create speech recognition task.")
        self._log("Speech recognition task created.")

        self._audio_engine.prepare()
        start_result = self._audio_engine.startAndReturnError_(None)
        started = start_result[0] if isinstance(start_result, tuple) else bool(start_result)
        if not started:
            self.stop()
            raise MacSpeechBackendError("Failed to start audio engine.")
        self._log("Audio engine started successfully.")

        with self._lock:
            self._running = True

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
        self._log(message)

    def _arm_silence_timer(self) -> None:
        self._cancel_silence_timer()
        timer = threading.Timer(self.silence_finalize_sec, self._emit_silence_final)
        timer.daemon = True
        self._silence_timer = timer
        timer.start()

    def _cancel_silence_timer(self) -> None:
        if self._silence_timer is not None:
            try:
                self._silence_timer.cancel()
            except Exception:
                pass
            self._silence_timer = None

    def _emit_silence_final(self) -> None:
        with self._lock:
            if not self._running:
                return
            text = self._latest_partial_text.strip()
            if not text or text == self._last_emitted_final_text:
                return
            self._last_emitted_final_text = text
            self._latest_partial_text = ""

        cb = self._callback
        if cb is None:
            return
        self._log("No native FINAL received; emitting synthetic FINAL after silence.")
        try:
            cb(
                TranscriptEvent(
                    text=text,
                    is_final=True,
                    ts=time.time(),
                    lang=self.lang,
                    source="mac_speech",
                )
            )
        except Exception as exc:
            self._set_error(f"Callback error: {exc}")

    def get_debug_stats(self) -> dict[str, float]:
        with self._lock:
            return {
                "audio_buffer_count": float(self._audio_buffer_count),
                "result_callback_count": float(self._result_callback_count),
                "last_audio_ts": self._last_audio_ts,
                "last_result_ts": self._last_result_ts,
            }

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[MacSpeechBackend] {message}")
