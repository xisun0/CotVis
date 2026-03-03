from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TranscriptEvent:
    text: str
    is_final: bool
    ts: float
    lang: str | None
    source: str


@dataclass(slots=True)
class TopTermsEvent:
    ts: float
    window_sec: int
    top_k: int
    terms: list[tuple[str, float]]
    focus: FocusMass | None = None
    phase: Phase | None = None
    transition: PhaseTransition | None = None
    phases: list[Phase] | None = None


@dataclass(slots=True)
class FocusMass:
    ts: float
    dominant_id: str
    dominant_display: str
    distribution: list[tuple[str, str, float]]
    velocity: dict[str, float]
    phase_id: int


@dataclass(slots=True)
class BridgeConcept:
    concept_id: str
    display: str
    score_in_previous: float
    score_in_current: float


@dataclass(slots=True)
class PhaseTransition:
    ts: float
    from_phase_id: int
    to_phase_id: int
    bridge: BridgeConcept | None


@dataclass(slots=True)
class Phase:
    id: int
    ts_start: float
    ts_end: float | None
    lane_min: int
    lane_max: int
    label: str | None
    centroid: list[tuple[str, float]] = field(default_factory=list)
