from __future__ import annotations

from enum import Enum


class SessionState(str, Enum):
    IDLE = "idle"
    LOADING_DOCUMENT = "loading_document"
    LOCATING_START = "locating_start"
    READING = "reading"
    PAUSED = "paused"
    REVIEWING = "reviewing"
    AWAITING_DECISION = "awaiting_decision"
    APPLYING_PATCH = "applying_patch"
    RESUMING = "resuming"
    COMPLETED = "completed"
