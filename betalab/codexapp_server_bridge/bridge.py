from __future__ import annotations

# This file was annotated with today's date: 2026-04-11.

import json
import os
import pty
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "runner.mjs"
INTERACTIVE_RUNNER = ROOT / "interactive_runner.mjs"


def _build_codex_exec_command(
    prompt: str,
    *,
    working_directory: str | None = None,
    session_id: str | None = None,
    model_reasoning_effort: str = "low",
) -> list[str]:
    base = [
        "codex",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        "danger-full-access",
        "--dangerously-bypass-approvals-and-sandbox",
        "-c",
        f"model_reasoning_effort={model_reasoning_effort}",
        "-c",
        "tools.web_search=false",
    ]
    if working_directory:
        base.extend(["-C", working_directory])
    if session_id:
        base.extend(["resume", session_id, prompt])
    else:
        base.append(prompt)
    return base


def _run_jsonl_command(
    command: list[str], *, cwd: Path, use_pty: bool = False
) -> tuple[list[dict], float]:
    started_at = time.perf_counter()
    if not use_pty:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            cwd=cwd,
            check=False,
        )
        raw_output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            raise RuntimeError(raw_output.strip() or "codex exec failed.")
    else:
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            close_fds=True,
        )
        os.close(slave_fd)
        chunks: list[bytes] = []
        try:
            while True:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
            process.wait(timeout=120)
        finally:
            os.close(master_fd)
        raw_output = b"".join(chunks).decode("utf-8", errors="replace")
        if process.returncode != 0:
            raise RuntimeError(raw_output.strip() or "codex exec failed.")

    events = []
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events, time.perf_counter() - started_at


def _extract_final_response(events: list[dict]) -> str:
    for event in reversed(events):
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                return str(item.get("text", ""))
    return ""


def _extract_thread_id(events: list[dict]) -> str | None:
    for event in events:
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
            if isinstance(thread_id, str) and thread_id:
                return thread_id
    return None


def run_codex_sdk(prompt: str, *, working_directory: str | None = None) -> dict:
    payload = {
        "prompt": prompt,
        "working_directory": working_directory,
    }
    command = ["node", str(RUNNER)]
    completed = subprocess.run(
        command,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stdout.strip() or completed.stderr.strip()
        raise RuntimeError(detail or "Codex SDK runner failed.")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Runner returned non-JSON output: {completed.stdout!r}"
        ) from exc


def run_codex_sdk_multi(
    prompts: list[str], *, working_directory: str | None = None
) -> dict:
    payload = {
        "prompts": prompts,
        "working_directory": working_directory,
    }
    command = ["node", str(RUNNER)]
    completed = subprocess.run(
        command,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stdout.strip() or completed.stderr.strip()
        raise RuntimeError(detail or "Codex SDK runner failed.")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Runner returned non-JSON output: {completed.stdout!r}"
        ) from exc


class CodexBridgeSession:
    def __init__(
        self,
        *,
        working_directory: str | None = None,
        model_reasoning_effort: str = "low",
    ) -> None:
        self._working_directory = working_directory
        self._model_reasoning_effort = model_reasoning_effort
        self._process: subprocess.Popen[str] | None = None

    def start(self) -> None:
        if self._process is not None:
            return
        self._process = subprocess.Popen(
            ["node", str(INTERACTIVE_RUNNER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=ROOT,
        )
        response = self._send(
            {
                "action": "start",
                "working_directory": self._working_directory,
                "model_reasoning_effort": self._model_reasoning_effort,
            }
        )
        if not response.get("ok"):
            self.close()
            raise RuntimeError(response.get("error", "Failed to start session."))

    def ask(self, prompt: str) -> str:
        if self._process is None:
            self.start()
        response = self._send({"action": "ask", "prompt": prompt})
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "Codex ask failed."))
        return str(response.get("response", ""))

    def ask_stream(self, prompt: str):
        if self._process is None:
            self.start()
        self._write({"action": "ask_stream", "prompt": prompt})
        while True:
            response = self._read()
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "Codex ask_stream failed."))
            event_type = response.get("event")
            if event_type == "delta":
                text = str(response.get("text", ""))
                if text:
                    yield text
                continue
            if event_type == "completed":
                break

    def close(self) -> None:
        if self._process is None:
            return
        try:
            self._send({"action": "close"})
        except Exception:
            pass
        if self._process.stdin is not None:
            self._process.stdin.close()
        self._process.wait(timeout=5)
        self._process = None

    def _send(self, payload: dict) -> dict:
        self._write(payload)
        return self._read()

    def _write(self, payload: dict) -> None:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Session process is not available.")
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

    def _read(self) -> dict:
        if self._process is None or self._process.stdout is None:
            raise RuntimeError("Session process is not available.")
        line = self._process.stdout.readline()
        if not line:
            stderr_text = ""
            if self._process.stderr is not None:
                stderr_text = self._process.stderr.read().strip()
            raise RuntimeError(stderr_text or "No response from interactive runner.")
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Runner returned non-JSON output: {line!r}") from exc


class CodexCliSession:
    def __init__(
        self,
        *,
        working_directory: str | None = None,
        model_reasoning_effort: str = "low",
        use_pty: bool = False,
    ) -> None:
        self._working_directory = working_directory
        self._model_reasoning_effort = model_reasoning_effort
        self._use_pty = use_pty
        self._session_id: str | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def ask(self, prompt: str) -> tuple[str, float]:
        command = _build_codex_exec_command(
            prompt,
            working_directory=self._working_directory,
            session_id=self._session_id,
            model_reasoning_effort=self._model_reasoning_effort,
        )
        events, elapsed = _run_jsonl_command(command, cwd=ROOT, use_pty=self._use_pty)
        if self._session_id is None:
            self._session_id = _extract_thread_id(events)
        response = _extract_final_response(events)
        return response, elapsed


def main() -> int:
    try:
        single_turn = run_codex_sdk(
            (
                "Rewrite this sentence to sound more precise and academic: "
                "Industrial policy can improve coordination under uncertainty."
            ),
            working_directory=str(Path.cwd()),
        )
        multi_turn = run_codex_sdk_multi(
            [
                (
                    "Rewrite this sentence to sound more precise and academic: "
                    "Industrial policy can improve coordination under uncertainty."
                ),
                "Now make the revised sentence slightly shorter.",
            ],
            working_directory=str(Path.cwd()),
        )
        session = CodexBridgeSession(working_directory=str(Path.cwd()))
        interactive_turn_1 = session.ask(
            (
                "Rewrite this sentence to sound more precise and academic: "
                "Industrial policy can improve coordination under uncertainty."
            )
        )
        interactive_turn_2 = session.ask(
            "Make your previous answer shorter while keeping an academic tone."
        )
        streamed_chunks = list(
            session.ask_stream(
                "Now rewrite the previous answer again, but keep it concise and formal."
            )
        )
        session.close()
        cli_pipe_session = CodexCliSession(
            working_directory=str(Path.cwd()),
            use_pty=False,
        )
        cli_pipe_turn_1, cli_pipe_elapsed_1 = cli_pipe_session.ask(
            "Reply with exactly: ok"
        )
        cli_pipe_turn_2, cli_pipe_elapsed_2 = cli_pipe_session.ask(
            "Reply with exactly: still ok"
        )
        cli_pty_session = CodexCliSession(
            working_directory=str(Path.cwd()),
            use_pty=True,
        )
        cli_pty_turn_1, cli_pty_elapsed_1 = cli_pty_session.ask(
            "Reply with exactly: ok"
        )
        cli_pty_turn_2, cli_pty_elapsed_2 = cli_pty_session.ask(
            "Reply with exactly: still ok"
        )
    except FileNotFoundError:
        print("`node` is not installed or not on PATH.", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("[single-turn]")
    print(json.dumps(single_turn, ensure_ascii=True, indent=2))
    print("")
    print("[multi-turn]")
    print(json.dumps(multi_turn, ensure_ascii=True, indent=2))
    print("")
    print("[interactive-session]")
    print(
        json.dumps(
            {
                "turn_1": interactive_turn_1,
                "turn_2": interactive_turn_2,
                "turn_3_streamed": "".join(streamed_chunks),
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    print("")
    print("[direct-cli-comparison]")
    print(
        json.dumps(
            {
                "pipe": {
                    "session_id": cli_pipe_session.session_id,
                    "turn_1": cli_pipe_turn_1,
                    "turn_1_seconds": round(cli_pipe_elapsed_1, 3),
                    "turn_2": cli_pipe_turn_2,
                    "turn_2_seconds": round(cli_pipe_elapsed_2, 3),
                },
                "pty": {
                    "session_id": cli_pty_session.session_id,
                    "turn_1": cli_pty_turn_1,
                    "turn_1_seconds": round(cli_pty_elapsed_1, 3),
                    "turn_2": cli_pty_turn_2,
                    "turn_2_seconds": round(cli_pty_elapsed_2, 3),
                },
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
