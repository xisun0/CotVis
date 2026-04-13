from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CODEX_HOME = Path.home() / ".codex"
CODEX_HISTORY_PATH = CODEX_HOME / "history.jsonl"
CODEX_SESSIONS_DIR = CODEX_HOME / "sessions"
TERMINAL_BINDINGS_DIR = CODEX_HOME / "tmp" / "terminal_broadcast_manager"
OUTPUT_COMPLETE_MARKER = "[OUTPUT_COMPLETE_7F3A9C]"
TERMINAL_OUTPUT_PROTOCOL = f"""When responding in the terminal, follow this output protocol strictly:

Write your normal user-facing response first.
After the response is fully complete, output this exact marker on its own line:
{OUTPUT_COMPLETE_MARKER}

Rules:
- The marker must appear exactly once per completed assistant turn.
- The marker must be on a line by itself.
- Do not mention, explain, paraphrase, or discuss the marker.
- Do not output the marker until the response is fully finished.
- Do not place the marker inside code blocks, diffs, patches, quoted text, or examples.
- Do not emit any other completion markers.
- Never include the marker anywhere except as the final line of the turn."""


@dataclass(frozen=True)
class TerminalTarget:
    window_id: int
    tty: str
    initial_prompt: str | None = None
    working_directory: str | None = None
    launched_at: float | None = None
    session_id: str | None = None
    session_path: str | None = None


@dataclass(frozen=True)
class SessionTurn:
    turn_id: str
    text: str
    completed_at: float | None = None


def read_latest_session_user_input(session_path: str | Path) -> str | None:
    path = Path(session_path)
    if not path.exists():
        return None
    latest: str | None = None
    try:
        with path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                record_type = record.get("type")
                payload = record.get("payload") or {}
                if record_type == "event_msg" and payload.get("type") == "user_message":
                    message = payload.get("message")
                    if isinstance(message, str) and message.strip():
                        latest = message.strip()
                        continue
                if record_type != "response_item":
                    continue
                if payload.get("type") != "message" or payload.get("role") != "user":
                    continue
                contents = payload.get("content")
                if not isinstance(contents, list):
                    continue
                for item in contents:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") != "input_text":
                        continue
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        latest = text.strip()
    except OSError:
        return None
    return latest


def _binding_filename(target: TerminalTarget) -> str:
    tty_slug = target.tty.replace("/", "_")
    return f"{target.window_id}-{tty_slug}.json"


def get_terminal_binding_path(target: TerminalTarget) -> Path:
    return TERMINAL_BINDINGS_DIR / _binding_filename(target)


def save_terminal_binding(target: TerminalTarget) -> None:
    TERMINAL_BINDINGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "window_id": target.window_id,
        "tty": target.tty,
        "initial_prompt": target.initial_prompt,
        "working_directory": target.working_directory,
        "launched_at": target.launched_at,
        "session_id": target.session_id,
        "session_path": target.session_path,
    }
    get_terminal_binding_path(target).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_terminal_binding(target: TerminalTarget) -> TerminalTarget:
    path = get_terminal_binding_path(target)
    if not path.exists():
        return target
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return target
    loaded = replace(
        target,
        initial_prompt=payload.get("initial_prompt") or target.initial_prompt,
        working_directory=payload.get("working_directory") or target.working_directory,
        launched_at=payload.get("launched_at") or target.launched_at,
        session_id=payload.get("session_id") or target.session_id,
        session_path=payload.get("session_path") or target.session_path,
    )
    if loaded.session_id and not loaded.session_path:
        session_path = find_session_path(loaded.session_id)
        if session_path is not None:
            loaded = replace(loaded, session_path=str(session_path))
            save_terminal_binding(loaded)
    return loaded


def find_session_path(session_id: str) -> Path | None:
    matches = sorted(CODEX_SESSIONS_DIR.rglob(f"*{session_id}.jsonl"))
    if not matches:
        return None
    return matches[-1]


def _read_session_cwd(session_path: Path) -> str | None:
    try:
        with session_path.open(encoding="utf-8") as handle:
            first = handle.readline()
    except OSError:
        return None
    if not first.strip():
        return None
    try:
        payload = json.loads(first)
    except json.JSONDecodeError:
        return None
    meta = payload.get("payload") or {}
    cwd = meta.get("cwd")
    if not isinstance(cwd, str):
        return None
    return cwd


def _history_entries_reverse() -> list[dict]:
    if not CODEX_HISTORY_PATH.exists():
        return []
    try:
        lines = CODEX_HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def resolve_session_for_prompt(
    *,
    prompt_text: str,
    launched_at: float | None,
    working_directory: str | None,
) -> tuple[str | None, str | None]:
    if not prompt_text:
        return None, None
    working_dir = str(Path(working_directory).resolve()) if working_directory else None
    lower_bound = (launched_at or 0.0) - 5.0
    for entry in _history_entries_reverse():
        if entry.get("text") != prompt_text:
            continue
        timestamp = float(entry.get("ts") or 0.0)
        if timestamp < lower_bound:
            continue
        session_id = entry.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            continue
        session_path = find_session_path(session_id)
        if session_path is None:
            return session_id, None
        if working_dir:
            session_cwd = _read_session_cwd(session_path)
            if session_cwd and str(Path(session_cwd).resolve()) != working_dir:
                continue
        return session_id, str(session_path)
    return None, None


def resolve_terminal_target_session(
    target: TerminalTarget,
    *,
    prompt_text: str | None = None,
    timeout_seconds: float = 6.0,
    poll_seconds: float = 0.25,
) -> TerminalTarget:
    resolved = load_terminal_binding(target)
    if resolved.session_id and resolved.session_path:
        return resolved
    candidate_prompt = prompt_text
    if candidate_prompt is None and resolved.initial_prompt:
        candidate_prompt = build_protocol_prompt(resolved.initial_prompt)
    if not candidate_prompt:
        return resolved

    deadline = time.time() + max(0.0, timeout_seconds)
    latest = resolved
    while True:
        if latest.session_id and not latest.session_path:
            session_path = find_session_path(latest.session_id)
            if session_path is not None:
                latest = replace(latest, session_path=str(session_path))
                save_terminal_binding(latest)
                return latest
        session_id, session_path = resolve_session_for_prompt(
            prompt_text=candidate_prompt,
            launched_at=latest.launched_at,
            working_directory=latest.working_directory,
        )
        if session_id:
            latest = replace(
                latest,
                session_id=session_id,
                session_path=session_path,
            )
            save_terminal_binding(latest)
            return latest
        if time.time() >= deadline:
            return latest
        time.sleep(max(0.05, poll_seconds))


def read_latest_completed_session_turn(session_path: str | Path) -> SessionTurn | None:
    path = Path(session_path)
    if not path.exists():
        return None
    latest_turn: SessionTurn | None = None
    try:
        with path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") != "event_msg":
                    continue
                payload = record.get("payload") or {}
                if payload.get("type") != "task_complete":
                    continue
                turn_id = payload.get("turn_id")
                text = payload.get("last_agent_message")
                if not isinstance(turn_id, str) or not isinstance(text, str):
                    continue
                completed_at = payload.get("completed_at")
                latest_turn = SessionTurn(
                    turn_id=turn_id,
                    text=text,
                    completed_at=float(completed_at) if completed_at is not None else None,
                )
    except OSError:
        return None
    return latest_turn


def build_protocol_prompt(user_prompt: str) -> str:
    return f"{TERMINAL_OUTPUT_PROTOCOL}\n\nUser request:\n{user_prompt}"


def send_prompt_to_terminal(target: TerminalTarget, prompt: str) -> None:
    """Send a single-line prompt to the terminal via tty write."""
    tty_path = Path(target.tty)
    payload = prompt.strip().replace("\n", " ")
    if not payload.endswith("\n"):
        payload += "\n"
    with tty_path.open("w", encoding="utf-8", errors="ignore") as handle:
        handle.write(payload)
        handle.flush()


def _write_launch_script(*, working_directory: str, prompt: str) -> str:
    """Write a temp shell script that launches codex with prompt as a single argument.

    Using a script file sidesteps AppleScript string escaping — shlex.quote handles
    all special characters in the prompt without needing to embed them in the
    AppleScript do-script string.
    """
    script = "\n".join([
        "#!/bin/zsh",
        f"cd {shlex.quote(working_directory)}",
        f"exec codex --no-alt-screen {shlex.quote(prompt)}",
        "",
    ])
    fd, path = tempfile.mkstemp(suffix=".sh")
    with os.fdopen(fd, "w") as f:
        f.write(script)
    os.chmod(path, 0o755)
    return path


def launch_terminal_codex(
    *, working_directory: str | None = None, initial_prompt: str | None = None
) -> TerminalTarget:
    target_dir = working_directory or str(REPO_ROOT)
    launched_at = time.time()

    script_path: str | None = None
    if initial_prompt:
        full_prompt = build_protocol_prompt(initial_prompt)
        script_path = _write_launch_script(working_directory=target_dir, prompt=full_prompt)
        shell_command = f"zsh {shlex.quote(script_path)}"
    else:
        shell_command = f"cd {shlex.quote(target_dir)} && codex --no-alt-screen"

    applescript = f'''
tell application "Terminal"
    activate
    do script "{shell_command}"
    delay 0.3
    set targetWindow to front window
    set targetTty to tty of selected tab of targetWindow
    return (id of targetWindow as text) & ":" & targetTty
end tell
'''
    completed = subprocess.run(
        ["osascript", "-e", applescript],
        check=True,
        capture_output=True,
        text=True,
    )
    raw = completed.stdout.strip()
    window_text, tty = raw.split(":", 1)
    target = TerminalTarget(
        window_id=int(window_text),
        tty=tty,
        initial_prompt=initial_prompt,
        working_directory=target_dir,
        launched_at=launched_at,
    )
    save_terminal_binding(target)

    if script_path:
        # Give zsh enough time to exec the script before we delete it
        time.sleep(1.5)
        try:
            os.unlink(script_path)
        except OSError:
            pass

    if initial_prompt:
        target = resolve_terminal_target_session(
            target,
            prompt_text=full_prompt,
            timeout_seconds=6.0,
        )

    return target


def main() -> int:
    initial_prompt = None
    if len(sys.argv) > 1:
        initial_prompt = " ".join(sys.argv[1:])
    try:
        target = launch_terminal_codex(initial_prompt=initial_prompt)
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip() or str(exc), file=sys.stderr)
        return 1
    session_suffix = f" session_id={target.session_id}" if target.session_id else ""
    print(
        f"Launched Terminal.app with codex at window_id={target.window_id} "
        f"tty={target.tty}.{session_suffix}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
