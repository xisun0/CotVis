from __future__ import annotations

import os

from realtime_asr.context.concept_registry import ConceptRegistry
from realtime_asr.context.lane_assigner import LaneAssigner
from realtime_asr.events import TopTermsEvent


class CanvasStateBuilder:
    def __init__(self, canvas_top_n: int = 15) -> None:
        self._canvas_top_n = max(1, int(canvas_top_n))
        self._session_start: float | None = None
        self._last_ts: float = 0.0
        self._snapshot_count = 0

        self._focus: dict[str, object] | None = None
        self._phase: dict[str, object] | None = None
        self._phases_by_id: dict[int, dict[str, object]] = {}
        self._latest_bridge: dict[str, object] | None = None

        self._node_history: list[dict[str, object]] = []
        self._persistence_edges: dict[str, dict[str, object]] = {}
        self._bridge_edges: list[dict[str, object]] = []
        self._ages: dict[str, int] = {}

        self._lane_assigner: LaneAssigner | None = None
        self._registry: ConceptRegistry | None = None
        self._jaccard_last: float | None = None

    def ingest(
        self,
        event: TopTermsEvent,
        lane_assigner: LaneAssigner,
        registry: ConceptRegistry,
    ) -> None:
        self._lane_assigner = lane_assigner
        self._registry = registry
        self._snapshot_count += 1
        self._last_ts = event.ts
        if self._session_start is None:
            self._session_start = event.ts

        id_to_score: dict[str, float] = {}
        velocity = event.focus.velocity if event.focus is not None else {}
        if event.focus is not None and event.focus.distribution:
            ranked = sorted(
                [(cid, float(weight)) for cid, _, weight in event.focus.distribution],
                key=lambda item: (-item[1], str(item[0])),
            )[: self._canvas_top_n]
            for cid, weight in ranked:
                id_to_score[cid] = float(weight)
        else:
            ranked_terms = sorted(
                [(raw_term, float(score)) for raw_term, score in event.terms],
                key=lambda item: (-item[1], str(item[0])),
            )[: self._canvas_top_n]
            for raw_term, score in ranked_terms:
                cid = registry.register(raw_term)
                if cid:
                    id_to_score[cid] = id_to_score.get(cid, 0.0) + float(score)

        active_ids = list(id_to_score.keys())
        lane_assignments = lane_assigner.get_all_assignments()
        active_set = set(active_ids)
        phase_id = event.phase.id if event.phase is not None else 0

        for cid in active_ids:
            lane_index = lane_assignments.get(cid)
            if lane_index is None:
                lane_index = lane_assigner.assign(cid, self._snapshot_count)
                lane_assignments[cid] = lane_index
            self._ages[cid] = self._ages.get(cid, 0) + 1
            node = {
                "id": cid,
                "display": registry.display(cid),
                "ts": event.ts,
                "lane_index": lane_index,
                "score": float(id_to_score.get(cid, 0.0)),
                "velocity": float(velocity.get(cid, 0.0)),
                "age": self._ages[cid],
                "source": "mixed",
                "phase_id": phase_id,
            }
            self._node_history.append(node)
            edge = self._persistence_edges.get(cid)
            if edge is None:
                self._persistence_edges[cid] = {
                    "type": "persistence",
                    "concept_id": cid,
                    "ts_start": event.ts,
                    "ts_end": event.ts,
                    "lane_index": lane_index,
                }
            else:
                edge["ts_end"] = event.ts
                edge["lane_index"] = lane_index

        for cid, edge in self._persistence_edges.items():
            if cid not in active_set and edge["ts_end"] is None:
                edge["ts_end"] = event.ts

        if event.focus is not None:
            self._focus = {
                "dominant_id": event.focus.dominant_id,
                "dominant_display": registry.display(event.focus.dominant_id),
                "distribution": [
                    {"id": cid, "display": registry.display(cid), "weight": float(weight)}
                    for cid, _, weight in event.focus.distribution[: self._canvas_top_n]
                ],
                "velocity": dict(event.focus.velocity),
            }
        else:
            self._focus = None

        if event.phase is not None:
            phase_dict = {
                "id": event.phase.id,
                "ts_start": event.phase.ts_start,
                "ts_end": event.phase.ts_end,
                "lane_min": event.phase.lane_min,
                "lane_max": event.phase.lane_max,
                "label": event.phase.label,
            }
            existing = self._phases_by_id.get(event.phase.id)
            if existing is None:
                self._phases_by_id[event.phase.id] = phase_dict
            else:
                existing["ts_start"] = min(float(existing["ts_start"]), float(phase_dict["ts_start"]))
                existing["ts_end"] = phase_dict["ts_end"]
                existing["lane_min"] = min(int(existing["lane_min"]), int(phase_dict["lane_min"]))
                existing["lane_max"] = max(int(existing["lane_max"]), int(phase_dict["lane_max"]))
                existing["label"] = phase_dict["label"] or existing["label"]
            self._phase = dict(self._phases_by_id[event.phase.id])

        if event.transition is not None and event.transition.bridge is not None:
            bridge = event.transition.bridge
            lane_index = lane_assignments.get(bridge.concept_id, lane_assigner.assign(bridge.concept_id, self._snapshot_count))
            bridge_dict = {
                "from_phase": event.transition.from_phase_id,
                "to_phase": event.transition.to_phase_id,
                "concept_id": bridge.concept_id,
                "display": registry.display(bridge.concept_id),
                "ts": event.transition.ts,
            }
            self._latest_bridge = bridge_dict
            self._bridge_edges.append(
                {
                    "type": "bridge",
                    "concept_id": bridge.concept_id,
                    "from_phase_id": event.transition.from_phase_id,
                    "to_phase_id": event.transition.to_phase_id,
                    "ts": event.transition.ts,
                    "lane_index": lane_index,
                }
            )

    def to_dict(self) -> dict[str, object]:
        lane_assigner = self._lane_assigner
        warmup_complete = False
        if lane_assigner is not None:
            warmup_complete = lane_assigner.warmup_complete(self._snapshot_count)

        phases = [
            self._phases_by_id[k]
            for k in sorted(self._phases_by_id.keys())
        ]
        edges: list[dict[str, object]] = list(self._persistence_edges.values())
        edges.extend(self._bridge_edges)

        return {
            "session_start": self._session_start or 0.0,
            "ts": self._last_ts,
            "snapshot_count": self._snapshot_count,
            "warmup_complete": warmup_complete,
            "focus": self._focus,
            "phase": self._phase,
            "phases": phases,
            "bridge": self._latest_bridge,
            "nodes": self._node_history,
            "edges": edges,
            "_debug": self._build_debug(),
        }

    def _build_debug(self) -> dict[str, object] | None:
        if os.getenv("COTVIS_CANVAS_DEBUG") != "1":
            return None
        if self._lane_assigner is None:
            return {
                "lane_assignments": {},
                "cooc_top10": {},
                "effective_theta": None,
                "jaccard_last": self._jaccard_last,
                "warmup_complete": False,
                "snapshot_count": self._snapshot_count,
                "group_count": 0,
                "lane_count": 0,
            }

        lane_assigner = self._lane_assigner
        effective_theta = (
            lane_assigner.theta_min
            if self._snapshot_count < lane_assigner.warmup_n
            else lane_assigner.theta
        )
        return {
            "lane_assignments": lane_assigner.get_all_assignments(),
            "cooc_top10": lane_assigner.get_cooc_top(top_n=10),
            "effective_theta": effective_theta,
            "jaccard_last": self._jaccard_last,
            "warmup_complete": lane_assigner.warmup_complete(self._snapshot_count),
            "snapshot_count": self._snapshot_count,
            "group_count": lane_assigner.get_group_count(),
            "lane_count": lane_assigner.get_lane_count(),
        }
