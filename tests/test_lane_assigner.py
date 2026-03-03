from __future__ import annotations

from realtime_asr.context.concept_registry import ConceptRegistry, canonical_id
from realtime_asr.context.lane_assigner import LaneAssigner


def test_first_concept_gets_lane_zero() -> None:
    assigner = LaneAssigner(gap=2)
    assert assigner.assign("a", snapshot_count=0) == 0


def test_two_unrelated_concepts_open_new_group_with_gap() -> None:
    assigner = LaneAssigner(gap=2)
    assert assigner.assign("a", snapshot_count=0) == 0
    assert assigner.assign("b", snapshot_count=0) == 3


def test_canonical_id_machine_learning() -> None:
    assert canonical_id("Machine Learning") == "machine_learning"


def test_canonical_id_gpt4() -> None:
    assert canonical_id("GPT-4") == "gpt_4"


def test_canonical_id_neural_network() -> None:
    assert canonical_id("neural-network") == "neural_network"


def test_canonical_id_collapses_simple_plurals() -> None:
    assert canonical_id("Models") == "model"
    assert canonical_id("Categories") == "category"


def test_cooc_once_during_warmup_joins_existing_group() -> None:
    assigner = LaneAssigner(theta=2.0, theta_min=1.0, warmup_n=10, gap=2)
    assigner.update_cooc(["a", "b"])
    assert assigner.assign("a", snapshot_count=1) == 0
    assert assigner.assign("b", snapshot_count=1) == 1


def test_same_cooc_after_warmup_isolated_when_below_theta() -> None:
    assigner = LaneAssigner(theta=2.0, theta_min=1.0, warmup_n=10, gap=2)
    assigner.update_cooc(["a", "b"])
    assert assigner.assign("a", snapshot_count=10) == 0
    assert assigner.assign("b", snapshot_count=10) == 3


def test_assignments_are_stable_after_first_write() -> None:
    assigner = LaneAssigner()
    lane = assigner.assign("a", snapshot_count=0)
    for i in range(20):
        assigner.update_cooc(["a", "x", "y"])
        assert assigner.assign("a", snapshot_count=i + 1) == lane


def test_register_and_display_latest_surface_form() -> None:
    registry = ConceptRegistry()
    cid = registry.register("Machine Learning")
    assert cid == "machine_learning"
    assert registry.display("machine_learning") == "Machine Learning"


def test_warmup_complete_boundary() -> None:
    assigner = LaneAssigner(warmup_n=10)
    assert assigner.warmup_complete(9) is False
    assert assigner.warmup_complete(10) is True


def test_get_all_assignments_returns_copy() -> None:
    assigner = LaneAssigner()
    assigner.assign("a", snapshot_count=0)
    copied = assigner.get_all_assignments()
    copied["a"] = 999
    assert assigner.get_all_assignments()["a"] == 0


def test_lane_assigner_max_lanes_fuse_caps_growth() -> None:
    assigner = LaneAssigner(gap=2, max_lanes=20)
    for i in range(120):
        assigner.assign(f"c{i}", snapshot_count=20)
    assert assigner.get_lane_count() <= 20
