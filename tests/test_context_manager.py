from __future__ import annotations

from collections import Counter

from realtime_asr.context.manager import ContextManager
from realtime_asr.events import TranscriptEvent


def _build_manager() -> ContextManager:
    return ContextManager(
        final_window_sec=0,
        partial_window_sec=10,
        top_k=20,
        final_weight=1.0,
        partial_weight=0.0,
        llm_reranker=None,
        llm_primary=False,
        enable_lm_rescoring=False,
        enable_phrase_scoring=False,
    )


def _event(text: str, is_final: bool, ts: float) -> TranscriptEvent:
    return TranscriptEvent(
        text=text,
        is_final=is_final,
        ts=ts,
        lang="en-US",
        source="test",
    )


def _stable_texts(manager: ContextManager) -> list[str]:
    return [text for _, text in manager.stable_segments]


def _replay_finals(finals: list[str]) -> list[str]:
    manager = _build_manager()
    ts = 1.0
    for text in finals:
        manager.on_event(_event(text, True, ts))
        ts += 1.0
    top = manager.compute_top_terms(now_ts=ts)
    return [term for term, _ in top.terms[:3]]


def test_normal_append_commits_only_new_suffix() -> None:
    manager = _build_manager()
    manager.on_event(_event("hello world", True, 1.0))
    manager.on_event(_event("hello world how are you", True, 2.0))
    assert _stable_texts(manager) == ["hello world", "how are you"]


def test_mid_sentence_revision_commits_only_new_tail() -> None:
    manager = _build_manager()
    manager.on_event(_event("the quick fox", True, 1.0))
    manager.on_event(_event("the slow fox jumped", True, 2.0))
    assert _stable_texts(manager) == ["the quick fox", "jumped"]


def test_identical_repeat_adds_no_segment() -> None:
    manager = _build_manager()
    manager.on_event(_event("hello", True, 1.0))
    manager.on_event(_event("hello", True, 2.0))
    assert _stable_texts(manager) == ["hello"]


def test_full_restart_no_overlap_commits_full_text() -> None:
    manager = _build_manager()
    manager.on_event(_event("abc", True, 1.0))
    manager.on_event(_event("xyz", True, 2.0))
    assert _stable_texts(manager) == ["abc", "xyz"]


def test_partial_then_final_clears_ephemeral_and_commits_final_delta() -> None:
    manager = _build_manager()
    manager.on_event(_event("hello", True, 1.0))
    manager.on_event(_event("hello how are", False, 2.0))
    assert manager.ephemeral_text == "how are"
    manager.on_event(_event("hello how are you", True, 3.0))
    assert manager.ephemeral_text == ""
    assert manager.ephemeral_ts == 0.0
    assert _stable_texts(manager) == ["hello", "how are you"]


def test_replaying_identical_final_three_times_does_not_duplicate_counts() -> None:
    manager = _build_manager()
    for ts in (1.0, 2.0, 3.0):
        manager.on_event(_event("delta alpha beta", True, ts))
    top = manager.compute_top_terms(now_ts=4.0)
    terms = dict(top.terms)
    assert terms["delta"] == 1.0
    assert terms["alpha"] == 1.0
    assert terms["beta"] == 1.0


def test_quality_gate_term_counts_do_not_exceed_true_occurrence_counts() -> None:
    manager = _build_manager()
    finals = [
        "solar battery system",
        "solar battery storage system",
        "battery storage safety",
        "solar system design",
    ]
    ts = 1.0
    for text in finals:
        manager.on_event(_event(text, True, ts))
        ts += 1.0

    top = manager.compute_top_terms(now_ts=ts)
    observed = dict(top.terms)
    truth = Counter(" ".join(finals).split())

    for term, score in observed.items():
        assert score <= float(truth.get(term, 0))


def test_quality_gate_top3_is_stable_across_two_replays() -> None:
    finals = [
        "solar battery system",
        "solar battery storage system",
        "battery storage safety",
        "solar system design",
    ]
    run1 = _replay_finals(finals)
    run2 = _replay_finals(finals)
    assert run1 == run2
