from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
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
    )

    if script_path:
        # Give zsh enough time to exec the script before we delete it
        time.sleep(1.5)
        try:
            os.unlink(script_path)
        except OSError:
            pass

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
    print(f"Launched Terminal.app with codex at window_id={target.window_id} tty={target.tty}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
