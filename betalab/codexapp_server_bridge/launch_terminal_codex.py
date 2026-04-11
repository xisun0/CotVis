from __future__ import annotations

import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TerminalTarget:
    window_id: int
    tty: str


def build_terminal_command(*, working_directory: str, initial_prompt: str | None = None) -> str:
    parts = [
        f"cd {shlex.quote(working_directory)}",
        "codex --no-alt-screen",
    ]
    if initial_prompt:
        parts[-1] += f" {shlex.quote(initial_prompt)}"
    return " && ".join(parts)


def launch_terminal_codex(
    *, working_directory: str | None = None, initial_prompt: str | None = None
) -> TerminalTarget:
    target_dir = working_directory or str(REPO_ROOT)
    shell_command = build_terminal_command(
        working_directory=target_dir,
        initial_prompt=initial_prompt,
    )
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
    return TerminalTarget(window_id=int(window_text), tty=tty)


def main() -> int:
    initial_prompt = None
    if len(sys.argv) > 1:
        initial_prompt = " ".join(sys.argv[1:])
    try:
        target = launch_terminal_codex(initial_prompt=initial_prompt)
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip() or str(exc), file=sys.stderr)
        return 1
    print(f"Launched Terminal.app with codex at window_id={target.window_id} tty={target.tty}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
