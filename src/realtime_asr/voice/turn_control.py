from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True)
class TriggerDecision:
    action: str
    raw: str | None = None


class ExplicitTriggerTurnController:
    def __init__(
        self,
        input_func: Callable[[str], str] = input,
        prompt: str = "[voice] press Enter to speak, or type :skip / :quit > ",
    ) -> None:
        self._input = input_func
        self._prompt = prompt

    def wait_for_trigger(self) -> TriggerDecision:
        try:
            raw = self._input(self._prompt)
        except EOFError:
            return TriggerDecision(action="quit")

        text = raw.strip()
        if not text:
            return TriggerDecision(action="listen")
        if text == ":skip":
            return TriggerDecision(action="skip")
        if text == ":quit":
            return TriggerDecision(action="quit")
        return TriggerDecision(action="unknown", raw=text)
