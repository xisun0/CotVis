from __future__ import annotations

from realtime_asr.context.concept_tracker import ConceptTracker
from realtime_asr.events import TopTermsEvent


def test_stable_scores_keep_single_phase_without_transition() -> None:
    tracker = ConceptTracker(jaccard_threshold=0.4, min_streak=2)
    transitions = []
    phase_ids = []
    for i in range(4):
        _, phase, transition = tracker.update({"a": 2.0, "b": 1.0}, now_ts=float(i), snapshot_count=i + 1)
        phase_ids.append(phase.id)
        transitions.append(transition)
    assert phase_ids == [1, 1, 1, 1]
    assert all(t is None for t in transitions)


def test_hard_pivot_fires_transition_with_no_bridge() -> None:
    tracker = ConceptTracker(jaccard_threshold=0.4, min_streak=2)
    seen_transition = None
    for i in range(3):
        tracker.update({"a": 3.0, "b": 2.0}, now_ts=float(i), snapshot_count=i + 1)
    for i in range(3, 6):
        _, _, transition = tracker.update({"c": 3.0, "d": 2.0}, now_ts=float(i), snapshot_count=i + 1)
        if transition is not None:
            seen_transition = transition
            break
    assert seen_transition is not None
    assert seen_transition.bridge is None


def test_bridged_transition_picks_shared_concept() -> None:
    tracker = ConceptTracker(jaccard_threshold=0.4, min_streak=2)
    for i in range(3):
        tracker.update({"a": 3.0, "b": 2.0}, now_ts=float(i), snapshot_count=i + 1)
    bridge_id = None
    for i in range(3, 6):
        _, _, transition = tracker.update({"b": 3.0, "c": 2.0}, now_ts=float(i), snapshot_count=i + 1)
        if transition is not None and transition.bridge is not None:
            bridge_id = transition.bridge.concept_id
            break
    assert bridge_id == "b"


def test_velocity_signs_reflect_rise_and_fade() -> None:
    tracker = ConceptTracker()
    tracker.update({"a": 1.0, "b": 2.0}, now_ts=1.0, snapshot_count=1)
    focus, _, _ = tracker.update({"a": 3.0, "b": 1.0}, now_ts=2.0, snapshot_count=2)
    assert focus.velocity["a"] > 0
    assert focus.velocity["b"] < 0


def test_velocity_norm_uses_normalized_score_delta() -> None:
    tracker = ConceptTracker()
    tracker.update({"a": 2.0, "b": 1.0}, now_ts=1.0, snapshot_count=1)
    focus, _, _ = tracker.update({"a": 3.0, "b": 1.0}, now_ts=2.0, snapshot_count=2)
    # t1: a=0.6667,b=0.3333 ; t2: a=0.75,b=0.25
    assert abs(focus.velocity["a"] - (0.75 - (2.0 / 3.0))) < 1e-6
    assert abs(focus.velocity["b"] - (0.25 - (1.0 / 3.0))) < 1e-6


def test_age_tracking_counts_presence_snapshots() -> None:
    tracker = ConceptTracker()
    for i in range(5):
        tracker.update({"a": 1.0}, now_ts=float(i), snapshot_count=i + 1)
    assert tracker.get_age("a") == 5


def test_rhetorical_hint_sets_phase_label() -> None:
    tracker = ConceptTracker()
    tracker.set_ephemeral_text("however this fails")
    _, phase, _ = tracker.update({"a": 1.0}, now_ts=1.0, snapshot_count=1)
    assert phase.label == "contrasting"


def test_single_low_jaccard_then_recover_does_not_fire_transition() -> None:
    tracker = ConceptTracker(jaccard_threshold=0.4, min_streak=2)
    tracker.update({"a": 1.0, "b": 1.0}, now_ts=1.0, snapshot_count=1)
    _, _, t1 = tracker.update({"c": 1.0, "d": 1.0}, now_ts=2.0, snapshot_count=2)
    _, _, t2 = tracker.update({"a": 1.0, "b": 1.0}, now_ts=3.0, snapshot_count=3)
    assert t1 is None
    assert t2 is None


def test_top_terms_event_new_fields_default_none() -> None:
    evt = TopTermsEvent(ts=1.0, window_sec=60, top_k=5, terms=[("a", 1.0)])
    assert evt.focus is None
    assert evt.phase is None
    assert evt.transition is None
