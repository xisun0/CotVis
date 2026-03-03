from __future__ import annotations

import re
from dataclasses import replace

from realtime_asr.events import BridgeConcept, FocusMass, Phase, PhaseTransition


class ConceptTracker:
    def __init__(
        self,
        jaccard_threshold: float = 0.4,
        min_streak: int = 2,
        bridge_top_k: int = 10,
    ) -> None:
        self.jaccard_threshold = float(jaccard_threshold)
        self.min_streak = int(min_streak)
        self.bridge_top_k = int(bridge_top_k)

        self._prev_scores: dict[str, float] = {}
        self._prev_ids: set[str] = set()
        self._ages: dict[str, int] = {}
        self._low_streak = 0
        self._phase_id = 0
        self._current_phase: Phase | None = None
        self._phase_sum_scores: dict[str, float] = {}
        self._phase_snapshot_count = 0
        self._phase_reference_ids: set[str] = set()
        self._ephemeral_text = ""
        self._jaccard_last = 1.0
        self._transition_history: list[PhaseTransition] = []
        self._phase_history: list[Phase] = []

    def set_ephemeral_text(self, text: str) -> None:
        self._ephemeral_text = text or ""

    def get_age(self, concept_id: str) -> int:
        return self._ages.get(concept_id, 0)

    def get_jaccard_last(self) -> float:
        return self._jaccard_last

    def get_transition_history(self) -> list[PhaseTransition]:
        return list(self._transition_history)

    def get_phases(self) -> list[Phase]:
        return [replace(p) for p in self._phase_history]

    def update(
        self,
        id_to_score: dict[str, float],
        now_ts: float,
        snapshot_count: int,
    ) -> tuple[FocusMass, Phase, PhaseTransition | None]:
        total = sum(float(v) for v in id_to_score.values() if v > 0.0)
        if total > 0.0:
            distribution = sorted(
                [(cid, "", float(score) / total) for cid, score in id_to_score.items() if score > 0.0],
                key=lambda x: (-x[2], x[0]),
            )
        else:
            distribution = []

        dominant_id = (
            sorted(id_to_score.items(), key=lambda item: (-float(item[1]), str(item[0])))[0][0]
            if id_to_score
            else ""
        )
        velocity = {
            cid: float(score) - float(self._prev_scores.get(cid, 0.0))
            for cid, score in id_to_score.items()
        }

        for cid in id_to_score:
            self._ages[cid] = self._ages.get(cid, 0) + 1

        current_ids = set(id_to_score.keys())
        transition: PhaseTransition | None = None

        if self._current_phase is None:
            self._phase_id = 1
            self._current_phase = Phase(
                id=self._phase_id,
                ts_start=now_ts,
                ts_end=None,
                lane_min=0,
                lane_max=0,
                label=None,
                centroid=[],
            )
            self._phase_reference_ids = set(current_ids)
            self._phase_history = [replace(self._current_phase)]
        else:
            jaccard = self._jaccard(self._phase_reference_ids, current_ids)
            self._jaccard_last = jaccard
            if jaccard < self.jaccard_threshold:
                self._low_streak += 1
            else:
                self._low_streak = 0
            if self._low_streak >= self.min_streak:
                previous_reference_ids = set(self._phase_reference_ids)
                prev_phase = self._close_current_phase(now_ts)
                self._phase_id += 1
                self._current_phase = Phase(
                    id=self._phase_id,
                    ts_start=now_ts,
                    ts_end=None,
                    lane_min=0,
                    lane_max=0,
                    label=None,
                    centroid=[],
                )
                self._phase_sum_scores.clear()
                self._phase_snapshot_count = 0
                self._phase_reference_ids = set(current_ids)
                bridge = self._pick_bridge(prev_phase, previous_reference_ids, id_to_score)
                transition = PhaseTransition(
                    ts=now_ts,
                    from_phase_id=prev_phase.id,
                    to_phase_id=self._current_phase.id,
                    bridge=bridge,
                )
                self._transition_history.append(transition)
                self._low_streak = 0
                self._phase_history.append(replace(self._current_phase))

        self._accumulate_centroid(id_to_score)
        if self._current_phase is not None:
            self._current_phase.centroid = self._build_centroid()
            self._current_phase.label = self._detect_label(self._ephemeral_text)
            self._phase_history[-1] = replace(self._current_phase)

        focus = FocusMass(
            ts=now_ts,
            dominant_id=dominant_id,
            dominant_display=dominant_id,
            distribution=distribution,
            velocity=velocity,
            phase_id=self._current_phase.id if self._current_phase is not None else 0,
        )

        self._prev_scores = dict(id_to_score)
        self._prev_ids = set(current_ids)

        return focus, replace(self._current_phase) if self._current_phase is not None else Phase(0, now_ts, None, 0, 0, None, []), transition

    def _accumulate_centroid(self, id_to_score: dict[str, float]) -> None:
        self._phase_snapshot_count += 1
        for cid, score in id_to_score.items():
            self._phase_sum_scores[cid] = self._phase_sum_scores.get(cid, 0.0) + float(score)

    def _build_centroid(self) -> list[tuple[str, float]]:
        if self._phase_snapshot_count <= 0:
            return []
        centroid = [
            (cid, total / float(self._phase_snapshot_count))
            for cid, total in self._phase_sum_scores.items()
        ]
        centroid.sort(key=lambda x: x[1], reverse=True)
        return centroid

    def _close_current_phase(self, now_ts: float) -> Phase:
        if self._current_phase is None:
            return Phase(id=0, ts_start=now_ts, ts_end=now_ts, lane_min=0, lane_max=0, label=None, centroid=[])
        self._current_phase.ts_end = now_ts
        self._current_phase.centroid = self._build_centroid()
        self._current_phase.label = self._detect_label(self._ephemeral_text)
        self._phase_history[-1] = replace(self._current_phase)
        return replace(self._current_phase)

    def _pick_bridge(
        self,
        previous_phase: Phase,
        previous_reference_ids: set[str],
        current_scores: dict[str, float],
    ) -> BridgeConcept | None:
        centroid_top = dict(previous_phase.centroid[: self.bridge_top_k])
        if not centroid_top:
            return None
        current_top_ids = {
            cid
            for cid, _ in sorted(current_scores.items(), key=lambda x: x[1], reverse=True)[: self.bridge_top_k]
        }
        candidates = [
            cid
            for cid in centroid_top
            if cid in current_top_ids and cid in previous_reference_ids
        ]
        if not candidates:
            return None
        bridge_id = max(
            candidates,
            key=lambda cid: (centroid_top.get(cid, 0.0) + current_scores.get(cid, 0.0)) / 2.0,
        )
        return BridgeConcept(
            concept_id=bridge_id,
            display=bridge_id,
            score_in_previous=float(centroid_top.get(bridge_id, 0.0)),
            score_in_current=float(current_scores.get(bridge_id, 0.0)),
        )

    @staticmethod
    def _jaccard(prev_ids: set[str], curr_ids: set[str]) -> float:
        if not prev_ids and not curr_ids:
            return 1.0
        union = prev_ids | curr_ids
        if not union:
            return 1.0
        inter = prev_ids & curr_ids
        return float(len(inter)) / float(len(union))

    @staticmethod
    def _detect_label(text: str) -> str | None:
        t = (text or "").lower()
        patterns: list[tuple[str, str]] = [
            ("contrasting", r"\b(however|but|in contrast)\b"),
            ("supporting", r"\b(because|therefore|thus)\b"),
            ("defining", r"\b(means|is defined as)\b"),
            ("exemplifying", r"\b(for example|such as)\b"),
            ("concluding", r"\b(in conclusion|to summarize)\b"),
        ]
        for label, pattern in patterns:
            if re.search(pattern, t):
                return label
        return None
