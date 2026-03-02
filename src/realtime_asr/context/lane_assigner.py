from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LaneGroup:
    start_index: int
    members: list[str]
    next_index: int


class LaneAssigner:
    def __init__(
        self,
        theta: float = 2.0,
        theta_min: float = 1.0,
        warmup_n: int = 10,
        gap: int = 2,
    ) -> None:
        self.theta = float(theta)
        self.theta_min = float(theta_min)
        self.warmup_n = int(warmup_n)
        self.gap = int(gap)

        self._groups: list[LaneGroup] = []
        self._assignments: dict[str, int] = {}
        self._cooc: dict[str, dict[str, int]] = {}
        self._next_free = 0

    def update_cooc(self, concept_ids: list[str]) -> None:
        ordered: list[str] = []
        seen: set[str] = set()
        for cid in concept_ids:
            if cid and cid not in seen:
                seen.add(cid)
                ordered.append(cid)
        for i in range(len(ordered)):
            a = ordered[i]
            for j in range(i + 1, len(ordered)):
                b = ordered[j]
                self._cooc.setdefault(a, {})
                self._cooc.setdefault(b, {})
                self._cooc[a][b] = self._cooc[a].get(b, 0) + 1
                self._cooc[b][a] = self._cooc[b].get(a, 0) + 1

    def assign(self, concept_id: str, snapshot_count: int) -> int:
        if concept_id in self._assignments:
            return self._assignments[concept_id]

        effective_theta = self.theta_min if snapshot_count < self.warmup_n else self.theta
        best_idx = -1
        best_score = float("-inf")
        for idx, group in enumerate(self._groups):
            score = self._group_score(concept_id, group)
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx >= 0 and best_score >= effective_theta:
            group = self._groups[best_idx]
            lane_index = group.next_index
            group.members.append(concept_id)
            group.next_index += 1
        else:
            lane_index = self._next_free
            self._groups.append(
                LaneGroup(
                    start_index=lane_index,
                    members=[concept_id],
                    next_index=lane_index + 1,
                )
            )
            self._next_free += 1 + self.gap

        self._assignments[concept_id] = lane_index
        return lane_index

    def warmup_complete(self, snapshot_count: int) -> bool:
        return snapshot_count >= self.warmup_n

    def get_all_assignments(self) -> dict[str, int]:
        return dict(self._assignments)

    def get_group_count(self) -> int:
        return len(self._groups)

    def get_lane_count(self) -> int:
        if not self._assignments:
            return 0
        return max(self._assignments.values()) + 1

    def get_cooc_top(self, top_n: int = 10) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for cid, neigh in self._cooc.items():
            pairs = sorted(neigh.items(), key=lambda x: x[1], reverse=True)[:top_n]
            out[cid] = {k: v for k, v in pairs}
        return out

    def _group_score(self, concept_id: str, group: LaneGroup) -> float:
        if not group.members:
            return 0.0
        total = 0.0
        for member in group.members:
            total += float(self._cooc.get(concept_id, {}).get(member, 0))
        return total / float(len(group.members))
