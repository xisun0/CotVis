from __future__ import annotations

import re
import time
from pathlib import Path

import pexpect


ROOT = Path(__file__).resolve().parent
ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text).replace("\r", "")


class CodexPexpectSession:
    def __init__(
        self,
        *,
        working_directory: str | None = None,
        model_reasoning_effort: str = "low",
    ) -> None:
        self._working_directory = working_directory or str(Path.cwd())
        self._model_reasoning_effort = model_reasoning_effort
        self._child: pexpect.spawn | None = None
        self._raw_chunks: list[str] = []

    def start(self, initial_prompt: str | None = None) -> None:
        if self._child is not None:
            return
        command = "codex"
        args = [
            "--no-alt-screen",
            "-C",
            self._working_directory,
            "-a",
            "never",
            "-s",
            "danger-full-access",
            "-c",
            f"model_reasoning_effort={self._model_reasoning_effort}",
        ]
        if initial_prompt:
            args.append(initial_prompt)
        self._child = pexpect.spawn(
            command,
            args,
            cwd=self._working_directory,
            encoding="utf-8",
            timeout=1,
        )
        self._dismiss_startup_prompts()

    def _dismiss_startup_prompts(self) -> None:
        startup_text = self.read_until_quiet(initial_wait=2.0, idle_rounds=2)
        if "Press enter to continue" in startup_text:
            assert self._child is not None
            self._child.send("2")
            time.sleep(0.1)
            self._child.sendline("")
            self.read_until_quiet(initial_wait=0.8, idle_rounds=3)

    def ask(self, prompt: str, *, initial_wait: float = 0.3, idle_rounds: int = 3) -> str:
        if self._child is None:
            self.start()
        assert self._child is not None
        self._child.sendline(prompt)
        return self.read_until_quiet(initial_wait=initial_wait, idle_rounds=idle_rounds)

    def read_until_quiet(
        self, *, initial_wait: float = 0.3, idle_rounds: int = 3, chunk_size: int = 4096
    ) -> str:
        if self._child is None:
            raise RuntimeError("Session not started.")
        time.sleep(max(0.0, initial_wait))
        idle_hits = 0
        parts: list[str] = []
        while True:
            try:
                chunk = self._child.read_nonblocking(chunk_size, timeout=0.7)
            except pexpect.TIMEOUT:
                idle_hits += 1
                if idle_hits >= idle_rounds:
                    break
                continue
            except pexpect.EOF:
                break
            if not chunk:
                idle_hits += 1
                if idle_hits >= idle_rounds:
                    break
                continue
            idle_hits = 0
            parts.append(chunk)
            self._raw_chunks.append(chunk)
        return strip_ansi("".join(parts)).strip()

    def transcript(self) -> str:
        return strip_ansi("".join(self._raw_chunks))

    def close(self) -> None:
        if self._child is None:
            return
        try:
            self._child.sendcontrol("c")
            time.sleep(0.2)
        except Exception:
            pass
        try:
            self._child.terminate(force=True)
        finally:
            self._child = None


def main() -> int:
    session = CodexPexpectSession(working_directory=str(Path.cwd()))
    try:
        session.start()
        reply_1 = session.ask("Reply with exactly: ok")
        reply_2 = session.ask("Reply with exactly: still ok")
    finally:
        session.close()

    print("[turn-1]")
    print(reply_1)
    print("")
    print("[turn-2]")
    print(reply_2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
