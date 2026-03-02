from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin, sqrt

DEFAULT_SAFE_MARGIN = 24.0
DEFAULT_MAX_ATTEMPTS = 500


@dataclass(frozen=True, slots=True)
class TermBox:
    term: str
    x: float
    y: float
    w: float
    h: float


def _hash_string(text: str) -> int:
    h = 2166136261
    for ch in text:
        h ^= ord(ch)
        h = (h + (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24)) & 0xFFFFFFFF
    return abs(h)


def _overlaps(a: TermBox, b: TermBox, pad: float = 4.0) -> bool:
    return not (
        a.x + a.w + pad < b.x
        or b.x + b.w + pad < a.x
        or a.y + a.h + pad < b.y
        or b.y + b.h + pad < a.y
    )


def _overlap_area(a: TermBox, b: TermBox) -> float:
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x + a.w, b.x + b.w)
    y2 = min(a.y + a.h, b.y + b.h)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return float((x2 - x1) * (y2 - y1))


def _in_bounds(box: TermBox, stage_w: float, stage_h: float, safe_margin: float) -> bool:
    return (
        box.x >= safe_margin
        and box.y >= safe_margin
        and (box.x + box.w) <= (stage_w - safe_margin)
        and (box.y + box.h) <= (stage_h - safe_margin)
    )


def place_term_boxes(
    stage_w: float,
    stage_h: float,
    terms: list[tuple[str, float, float]],
    safe_margin: float = DEFAULT_SAFE_MARGIN,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> list[TermBox]:
    """Deterministic word-cloud placement mirrored from frontend spiral strategy.

    Args:
        stage_w: width of cloud canvas
        stage_h: height of cloud canvas
        terms: [(term, measured_width, measured_height)] in ranked order
        safe_margin: minimum edge inset for every term box
    """
    cx = stage_w / 2.0
    cy = stage_h / 2.0
    placed: list[TermBox] = []

    for idx, (term, node_w, node_h) in enumerate(terms):
        seed = _hash_string(f"{term}-{idx}")
        start_angle = (seed % 360) * (pi / 180.0)
        ellipse_y = 0.72

        best: TermBox | None = None
        best_overlap = float("inf")

        for t in range(max_attempts):
            angle = start_angle + t * 0.58
            # Lower-rank terms begin further out while still allowing full spiral search.
            base_radius = 14.0 + sqrt(float(idx)) * 24.0
            radius = base_radius + t * 4.8
            x = cx + cos(angle) * radius - node_w / 2.0
            y = cy + sin(angle) * radius * ellipse_y - node_h / 2.0
            candidate = TermBox(term=term, x=x, y=y, w=node_w, h=node_h)
            if not _in_bounds(candidate, stage_w, stage_h, safe_margin):
                continue

            overlap_sum = sum(_overlap_area(candidate, p) for p in placed)
            if overlap_sum == 0.0:
                best = candidate
                best_overlap = 0.0
                break
            if overlap_sum < best_overlap:
                best = candidate
                best_overlap = overlap_sum

        if best is None:
            # Bounded deterministic fallback so count stays equal to term count.
            best = TermBox(
                term=term,
                x=max(safe_margin, min(stage_w - node_w - safe_margin, cx - node_w / 2.0)),
                y=max(safe_margin, min(stage_h - node_h - safe_margin, cy - node_h / 2.0)),
                w=node_w,
                h=node_h,
            )
        placed.append(best)

    return placed
