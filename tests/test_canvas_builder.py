from __future__ import annotations

from realtime_asr.context.concept_registry import ConceptRegistry
from realtime_asr.context.lane_assigner import LaneAssigner
from realtime_asr.events import BridgeConcept, FocusMass, Phase, PhaseTransition, TopTermsEvent
from realtime_asr.web.canvas_builder import CanvasStateBuilder


def _event(ts: float, phase_id: int = 1, transition: PhaseTransition | None = None) -> TopTermsEvent:
    return TopTermsEvent(
        ts=ts,
        window_sec=60,
        top_k=10,
        terms=[("Machine Learning", 2.0), ("Neural Network", 1.5)],
        focus=FocusMass(
            ts=ts,
            dominant_id="machine_learning",
            dominant_display="Machine Learning",
            distribution=[("machine_learning", "Machine Learning", 0.57), ("neural_network", "Neural Network", 0.43)],
            velocity={"machine_learning": 0.12, "neural_network": -0.05},
            phase_id=phase_id,
        ),
        phase=Phase(
            id=phase_id,
            ts_start=ts - 1.0,
            ts_end=None,
            lane_min=0,
            lane_max=2,
            label="supporting",
            centroid=[("machine_learning", 1.2)],
        ),
        transition=transition,
    )


def test_canvas_builder_basic_schema() -> None:
    builder = CanvasStateBuilder()
    registry = ConceptRegistry()
    lane = LaneAssigner()
    registry.register("Machine Learning")
    registry.register("Neural Network")
    lane.assign("machine_learning", 1)
    lane.assign("neural_network", 1)

    builder.ingest(_event(10.0), lane, registry)
    payload = builder.to_dict()

    assert payload["session_start"] == 10.0
    assert payload["snapshot_count"] == 1
    assert payload["focus"] is not None
    assert payload["phase"] is not None
    assert isinstance(payload["nodes"], list)
    assert isinstance(payload["edges"], list)
    assert payload["bridge"] is None


def test_canvas_builder_bridge_and_debug(monkeypatch) -> None:
    monkeypatch.setenv("COTVIS_CANVAS_DEBUG", "1")
    builder = CanvasStateBuilder()
    registry = ConceptRegistry()
    lane = LaneAssigner()
    registry.register("Machine Learning")
    registry.register("Neural Network")
    lane.assign("machine_learning", 1)
    lane.assign("neural_network", 1)

    transition = PhaseTransition(
        ts=11.0,
        from_phase_id=1,
        to_phase_id=2,
        bridge=BridgeConcept(
            concept_id="neural_network",
            display="Neural Network",
            score_in_previous=0.6,
            score_in_current=0.5,
        ),
    )
    builder.ingest(_event(10.0, phase_id=1), lane, registry)
    builder.ingest(_event(11.0, phase_id=2, transition=transition), lane, registry)
    payload = builder.to_dict()

    assert payload["bridge"] is not None
    assert payload["bridge"]["concept_id"] == "neural_network"
    assert payload["_debug"] is not None
    assert "lane_assignments" in payload["_debug"]


def test_canvas_builder_honors_canvas_top_n_limit() -> None:
    builder = CanvasStateBuilder(canvas_top_n=1)
    registry = ConceptRegistry()
    lane = LaneAssigner()
    registry.register("Machine Learning")
    registry.register("Neural Network")
    lane.assign("machine_learning", 1)
    lane.assign("neural_network", 1)

    builder.ingest(_event(10.0), lane, registry)
    payload = builder.to_dict()
    assert len(payload["nodes"]) == 1
