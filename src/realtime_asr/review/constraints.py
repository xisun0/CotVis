from __future__ import annotations


def normalize_constraints(raw_constraints: list[str]) -> list[str]:
    return [item.strip() for item in raw_constraints if item.strip()]
