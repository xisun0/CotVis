import numpy as np

from realtime_asr.voice.asr import OpenAITurnAsr, TypedTurnAsr, _chunk_energy
from realtime_asr.voice.turn_control import ExplicitTriggerTurnController


def test_typed_turn_asr_returns_final_turn() -> None:
    backend = TypedTurnAsr(input_func=lambda _prompt: "下一节")
    turn = backend.capture_turn()

    assert turn is not None
    assert turn.transcript == "下一节"
    assert turn.is_final is True
    assert turn.source == "typed"


def test_typed_turn_asr_returns_none_for_blank_input() -> None:
    backend = TypedTurnAsr(input_func=lambda _prompt: "   ")
    assert backend.capture_turn() is None


def test_explicit_trigger_turn_controller_listen_on_blank_input() -> None:
    controller = ExplicitTriggerTurnController(input_func=lambda _prompt: "")
    decision = controller.wait_for_trigger()

    assert decision.action == "listen"


def test_explicit_trigger_turn_controller_supports_skip_and_quit() -> None:
    skip_controller = ExplicitTriggerTurnController(input_func=lambda _prompt: ":skip")
    quit_controller = ExplicitTriggerTurnController(input_func=lambda _prompt: ":quit")

    assert skip_controller.wait_for_trigger().action == "skip"
    assert quit_controller.wait_for_trigger().action == "quit"


def test_explicit_trigger_turn_controller_rejects_unknown_trigger_text() -> None:
    controller = ExplicitTriggerTurnController(input_func=lambda _prompt: "暂停")
    decision = controller.wait_for_trigger()

    assert decision.action == "unknown"
    assert decision.raw == "暂停"


def test_openai_turn_asr_keeps_configuration() -> None:
    backend = OpenAITurnAsr(
        max_record_seconds=4.5,
        sample_rate=22050,
        language="zh",
        silence_seconds_to_stop=0.6,
        energy_threshold=0.02,
    )

    assert backend.model == "gpt-4o-mini-transcribe"
    assert backend.max_record_seconds == 4.5
    assert backend.sample_rate == 22050
    assert backend.language == "zh"
    assert backend.silence_seconds_to_stop == 0.6
    assert backend.energy_threshold == 0.02
    assert backend.chunk_seconds == 0.25
    assert backend.stream_latency == "high"


def test_chunk_energy_detects_non_silent_audio() -> None:
    silent = np.zeros((160, 1), dtype=np.float32)
    voiced = np.full((160, 1), 0.1, dtype=np.float32)

    assert _chunk_energy(silent) == 0.0
    assert _chunk_energy(voiced) > 0.0
