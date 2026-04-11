from __future__ import annotations

import argparse
import difflib
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from .launch_terminal_codex import TerminalTarget, launch_terminal_codex
except ImportError:
    from launch_terminal_codex import TerminalTarget, launch_terminal_codex


REPO_ROOT = Path(__file__).resolve().parents[2]
ZH_VOICE = "Eddy (Chinese (China mainland))"
EN_VOICE = "Eddy (English (US))"


def run_osascript(script: str) -> str:
    completed = subprocess.run(
        ["osascript", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def get_front_terminal_name() -> str:
    script = 'tell application "Terminal" to get name of front window'
    return run_osascript(script).strip()


def get_terminal_name(target: TerminalTarget | None = None) -> str:
    if target is None:
        return get_front_terminal_name()
    script = (
        'tell application "Terminal" '
        f'to get name of window id {target.window_id}'
    )
    return run_osascript(script).strip()


def get_terminal_contents(target: TerminalTarget | None = None) -> str:
    if target is None:
        script = 'tell application "Terminal" to get contents of selected tab of front window'
        return run_osascript(script)
    script = (
        'tell application "Terminal"\n'
        f'    set targetWindow to window id {target.window_id}\n'
        "    repeat with t in tabs of targetWindow\n"
        f'        if tty of t is "{target.tty}" then return contents of (contents of t)\n'
        "    end repeat\n"
        '    error "Target tab not found."\n'
        "end tell"
    )
    return run_osascript(script)


def contains_cjk(text: str) -> bool:
    for char in text:
        code = ord(char)
        if (
            0x4E00 <= code <= 0x9FFF
            or 0x3400 <= code <= 0x4DBF
            or 0x20000 <= code <= 0x2A6DF
        ):
            return True
    return False


def speak_text(text: str) -> None:
    cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if not cleaned:
        return
    voice = ZH_VOICE if contains_cjk(cleaned) else EN_VOICE
    subprocess.run(
        ["say", "-v", voice, cleaned],
        check=False,
        capture_output=True,
        text=True,
    )


def compute_increment(previous: str, current: str) -> str:
    if not previous:
        return current
    if current.startswith(previous):
        return current[len(previous) :]
    # Terminal output often gets reflowed or rewritten. Use a line diff so
    # newly added assistant text is still detected when the snapshot no longer
    # has the previous text as a strict prefix.
    previous_lines = previous.splitlines()
    current_lines = current.splitlines()
    matcher = difflib.SequenceMatcher(a=previous_lines, b=current_lines)
    added_lines: list[str] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            added_lines.extend(current_lines[j1:j2])
    return "\n".join(added_lines)


def extract_codex_reply_text(text: str) -> str:
    kept: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Last login:"):
            continue
        if line.startswith("WARNING:"):
            continue
        if line.startswith("cd /"):
            continue
        if line.startswith("(base) ") and " % " in line:
            continue
        if line.startswith("›"):
            continue
        if line.startswith("•"):
            line = line.removeprefix("•").strip()
            if not line:
                continue
        if line.startswith("◦"):
            continue
        if line.startswith("[listen]") or line.startswith("[update"):
            continue
        if line.startswith("│") or line.startswith("╭") or line.startswith("╰"):
            continue
        if "esc to interrupt" in line:
            continue
        if "background terminal running" in line:
            continue
        if "gpt-" in line and "left" in line:
            continue
        if line.startswith("Tip:"):
            continue
        if line.startswith("model:"):
            continue
        if line.startswith("directory:"):
            continue
        if line.startswith(">_ OpenAI Codex"):
            continue
        if line.startswith("See full release notes:"):
            continue
        if "github.com/openai/codex/releases/latest" in line:
            continue
        if line.startswith("Added ") or line.startswith("Ran "):
            continue
        if line.startswith("────────────────"):
            continue
        if line.startswith("Working ("):
            continue
        kept.append(line)
    return "\n".join(kept)


@dataclass
class BroadcastEvent:
    window_name: str
    text: str
    timestamp: float


class TerminalBroadcastManager:
    def __init__(
        self,
        *,
        speak: bool = False,
        print_speak_text: bool = True,
        target: TerminalTarget | None = None,
    ) -> None:
        self._last_contents = ""
        self._last_reply_text = ""
        self._speak = speak
        self._print_speak_text = print_speak_text
        self._target = target

    def poll(self) -> BroadcastEvent | None:
        window_name = get_terminal_name(self._target)
        current = get_terminal_contents(self._target)
        _ = compute_increment(self._last_contents, current)
        self._last_contents = current
        current_reply_text = extract_codex_reply_text(current)
        reply_increment = compute_increment(self._last_reply_text, current_reply_text)
        self._last_reply_text = current_reply_text
        if not reply_increment.strip():
            return None
        event = BroadcastEvent(
            window_name=window_name,
            text=reply_increment,
            timestamp=time.time(),
        )
        if self._print_speak_text:
            print("")
            print("[speak]")
            print(reply_increment.rstrip())
        if self._speak:
            speak_text(reply_increment)
        return event


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Listen to front Terminal.app content updates and optionally speak them.",
    )
    parser.add_argument(
        "--launch-codex",
        action="store_true",
        help="Open a fresh Terminal.app window and start codex before listening.",
    )
    parser.add_argument(
        "--initial-prompt",
        default=None,
        help="Optional initial prompt used with --launch-codex.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=1.0,
        help="Polling interval for front Terminal content.",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=30.0,
        help="Maximum listen duration before exit. Use 0 or a negative value to listen until Ctrl+C.",
    )
    parser.add_argument(
        "--speak",
        action="store_true",
        help="Use macOS say to read newly detected terminal text.",
    )
    parser.add_argument(
        "--silent-debug",
        action="store_true",
        help="Do not call say; only print the text that would be spoken.",
    )
    parser.add_argument(
        "--front-only",
        action="store_true",
        help="Ignore launch binding and always follow the current front Terminal window.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    target: TerminalTarget | None = None
    if args.launch_codex:
        target = launch_terminal_codex(
            working_directory=str(REPO_ROOT),
            initial_prompt=args.initial_prompt,
        )
        time.sleep(2.0)
    if args.front_only:
        target = None

    manager = TerminalBroadcastManager(
        speak=bool(args.speak) and not bool(args.silent_debug),
        print_speak_text=True,
        target=target,
    )
    started_at = time.time()
    if target is None:
        print(f"[listen] mode=front window={get_front_terminal_name()}")
    else:
        print(
            f"[listen] mode=bound window_id={target.window_id} tty={target.tty} "
            f"window={get_terminal_name(target)}"
        )

    try:
        while True:
            if float(args.max_seconds) > 0 and time.time() - started_at >= float(args.max_seconds):
                break
            try:
                event = manager.poll()
            except subprocess.CalledProcessError as exc:
                print(exc.stderr.strip() or str(exc), file=sys.stderr)
                return 1
            if event is not None:
                print("")
                print(f"[update {event.timestamp:.3f}]")
                print(event.text.rstrip())
            time.sleep(max(0.2, float(args.poll_seconds)))
    except KeyboardInterrupt:
        print("")
        print("[listen] interrupted")
        return 0

    print("")
    print("[listen] finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
