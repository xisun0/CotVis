from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

try:
    from .launch_terminal_codex import (
        OUTPUT_COMPLETE_MARKER,
        TERMINAL_OUTPUT_PROTOCOL,
        TerminalTarget,
        launch_terminal_codex,
    )
except ImportError:
    from launch_terminal_codex import (
        OUTPUT_COMPLETE_MARKER,
        TERMINAL_OUTPUT_PROTOCOL,
        TerminalTarget,
        launch_terminal_codex,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]
ZH_VOICE = "Eddy (Chinese (China mainland))"
EN_VOICE = "Eddy (English (US))"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_TTS_VOICE = "alloy"
OPENAI_TTS_SPEED = 1.2
SPEECH_SENTENCE_BOUNDARY_RE = re.compile(r"[。！？!?：:]\s*|\n+")
SPEECH_REWRITE_SYSTEM_PROMPT = """你正在把终端里的 assistant 输出改写成适合 TTS 朗读的中文短播报。

要求：
- 输出 1 到 3 句自然口语
- 优先保留对用户有价值的结果，其次才是简短进度
- 不要逐字复述路径、命令、文件树、工具动作
- 遇到文件清单、步骤清单、技术过程时，压缩成概括
- 如果输入包含 patch、diff、命令、路径或工具日志，不要复述这些细节，只提炼当前动作和对用户有价值的结果
- 不要添加原文没有的新事实
- 不要输出项目符号、编号、Markdown、代码块
- 不要输出“如果你愿意我可以继续”这类尾句
- 输出必须能直接拿去做 TTS"""


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
    client = OpenAI()
    suffix = ".mp3"
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
        with client.audio.speech.with_streaming_response.create(
            model=OPENAI_TTS_MODEL,
            voice=OPENAI_TTS_VOICE,
            input=cleaned,
            response_format="mp3",
            speed=OPENAI_TTS_SPEED,
        ) as response:
            response.stream_to_file(tmp_path)
        subprocess.run(
            ["afplay", tmp_path],
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def rewrite_for_speech_with_model(
    chunk: str,
    *,
    client: OpenAI | None = None,
    model: str = "gpt-4o-mini",
) -> str:
    cleaned = remove_completion_markers(chunk).strip()
    if not cleaned:
        return ""

    local_client = client or OpenAI()
    completion = local_client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SPEECH_REWRITE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "请把下面这段终端输出改写成适合语音播报的中文短文本：\n\n"
                    f"<chunk>\n{cleaned}\n</chunk>"
                ),
            },
        ],
    )
    message = completion.choices[0].message.content or ""
    return message.strip()


def strip_patch_and_diff_blocks(text: str) -> str:
    kept: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if stripped.startswith("Deleted ") or stripped.startswith("Added "):
            continue
        if stripped.startswith("*** Begin Patch") or stripped.startswith("*** End Patch"):
            continue
        if stripped.startswith("*** Update File:") or stripped.startswith("*** Add File:"):
            continue
        if stripped.startswith("*** Delete File:") or stripped.startswith("*** Move to:"):
            continue
        if stripped.startswith("@@"):
            continue
        if stripped.startswith("diff --git ") or stripped.startswith("index "):
            continue
        if stripped.startswith("--- ") or stripped.startswith("+++ "):
            continue
        # Drop patch-style line number / +/- prefixed detail lines such as:
        # "1 -# Voice Review CLI" or "378 +Architecture rule to preserve:"
        parts = stripped.split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            remainder = parts[1]
            if remainder.startswith(("+", "-")):
                continue
        kept.append(line)
    return "\n".join(kept)


def remove_completion_markers(text: str) -> str:
    kept: list[str] = []
    for raw_line in text.splitlines():
        if raw_line.strip() == OUTPUT_COMPLETE_MARKER:
            continue
        kept.append(raw_line)
    return "\n".join(kept)


def count_completion_marker_lines(text: str) -> int:
    count = 0
    for raw_line in text.splitlines():
        if raw_line.strip() == OUTPUT_COMPLETE_MARKER:
            count += 1
    return count


def strip_injected_prompt_text(text: str, target: TerminalTarget | None) -> str:
    if target is None:
        return text

    ignored_exact_lines = {"User request:"}
    initial_prompt_lines = set()
    ignored_fragments = [
        "When responding in the terminal, follow this output protocol strictly",
        "Write your normal user-facing response first",
        "After the response is fully complete, output this exact marker",
        "The marker must appear exactly once per completed assistant turn",
        "The marker must be on a line by itself",
        "Do not mention, explain, paraphrase, or discuss the marker",
        "Do not output the marker until the response is fully finished",
        "Do not place the marker inside code blocks, diffs, patches, quoted text, or examples",
        "Do not emit any other completion markers",
        "Never include the marker anywhere except as the final line of the turn",
        OUTPUT_COMPLETE_MARKER,
    ]
    if target.initial_prompt:
        initial_prompt_lines = {
            line.strip() for line in target.initial_prompt.splitlines() if line.strip()
        }
        ignored_fragments.extend(initial_prompt_lines)

    kept: list[str] = []
    in_protocol_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if in_protocol_block and line in initial_prompt_lines:
            in_protocol_block = False
            continue
        if any(fragment in line for fragment in ignored_fragments):
            in_protocol_block = True
            continue
        if line in {"Rules:", "line:"}:
            in_protocol_block = True
            continue
        if in_protocol_block:
            continue
        if line in ignored_exact_lines:
            continue
        if "\\012" in line:
            continue
        kept.append(raw_line)
    return "\n".join(kept)


def has_unclosed_pairs(text: str) -> bool:
    candidate = text.strip()
    if not candidate:
        return False
    if candidate.count("“") > candidate.count("”"):
        return True
    if candidate.count("(") > candidate.count(")"):
        return True
    if candidate.count("[") > candidate.count("]"):
        return True
    # Heuristic for straight quotes: odd count usually means a dangling quote.
    if candidate.count('"') % 2 == 1:
        return True
    return False


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
    return strip_patch_and_diff_blocks("\n".join(kept))


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
        speech_idle_seconds: float = 1.0,
        speech_rewrite_model: str = "gpt-4o-mini",
        speech_max_chars: int = 140,
    ) -> None:
        self._last_contents = ""
        self._last_reply_text = ""
        self._pending_speech_buffer = ""
        self._last_append_time = 0.0
        self._last_flush_time = 0.0
        self._completion_marker_count = 0
        self._speak = speak
        self._print_speak_text = print_speak_text
        self._target = target
        self._speech_idle_seconds = max(0.2, float(speech_idle_seconds))
        self._speech_rewrite_model = speech_rewrite_model
        self._speech_max_chars = max(30, int(speech_max_chars))
        self._openai_client: OpenAI | None = None

    def append_reply_increment(self, text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        if self._pending_speech_buffer:
            self._pending_speech_buffer = f"{self._pending_speech_buffer}\n{cleaned}"
        else:
            self._pending_speech_buffer = cleaned
        self._last_append_time = time.time()

    def flush_ready_speech_chunks(self, *, force_flush: bool = False) -> list[str]:
        if not self._pending_speech_buffer.strip():
            return []
        now = time.time()
        if not force_flush:
            force_flush = now - self._last_append_time >= self._speech_idle_seconds
        chunks: list[str] = []

        while True:
            next_chunk = self._pop_next_speech_chunk(force_flush=force_flush)
            if not next_chunk:
                break
            chunks.append(next_chunk)

        if chunks:
            self._last_flush_time = now
        return chunks

    def _pop_next_speech_chunk(self, *, force_flush: bool) -> str | None:
        buffer = self._pending_speech_buffer.strip()
        if not buffer:
            self._pending_speech_buffer = ""
            return None

        cutoff = self._find_speech_boundary(buffer)
        if cutoff is not None:
            chunk = buffer[:cutoff].strip()
            remainder = buffer[cutoff:].lstrip()
            if has_unclosed_pairs(chunk) and remainder:
                return None
            self._pending_speech_buffer = remainder
            return chunk or None

        if len(buffer) >= self._speech_max_chars:
            chunk = buffer[: self._speech_max_chars].strip()
            remainder = buffer[self._speech_max_chars :].lstrip()
            if has_unclosed_pairs(chunk) and remainder and not force_flush:
                return None
            self._pending_speech_buffer = remainder
            return chunk or None

        if force_flush:
            self._pending_speech_buffer = ""
            return buffer

        return None

    def _find_speech_boundary(self, buffer: str) -> int | None:
        boundaries: list[int] = []
        for match in SPEECH_SENTENCE_BOUNDARY_RE.finditer(buffer):
            boundaries.append(match.end())
        if not boundaries:
            return None

        # Prefer the latest sentence boundary that keeps the chunk compact enough
        # for continuous playback. If every boundary is already too long, fall back
        # to the first complete sentence.
        candidates = [pos for pos in boundaries if pos <= self._speech_max_chars]
        if candidates:
            return candidates[-1]
        return boundaries[0]

    def poll(self) -> BroadcastEvent | None:
        window_name = get_terminal_name(self._target)
        current = get_terminal_contents(self._target)
        _ = compute_increment(self._last_contents, current)
        self._last_contents = current
        current_reply_text = extract_codex_reply_text(current)
        current_reply_text = strip_injected_prompt_text(current_reply_text, self._target)
        current_marker_count = count_completion_marker_lines(current_reply_text)
        marker_completed = current_marker_count > self._completion_marker_count
        self._completion_marker_count = current_marker_count
        current_reply_text = remove_completion_markers(current_reply_text)
        reply_increment = compute_increment(self._last_reply_text, current_reply_text)
        self._last_reply_text = current_reply_text
        if reply_increment.strip():
            self.append_reply_increment(reply_increment)

        ready_chunks = self.flush_ready_speech_chunks(force_flush=marker_completed)
        if not ready_chunks:
            return None

        emitted_text = "\n\n".join(ready_chunks)
        event = BroadcastEvent(
            window_name=window_name,
            text=emitted_text,
            timestamp=time.time(),
        )
        if self._print_speak_text:
            print("")
            print("[speak]")
            print(emitted_text.rstrip())
        for chunk in ready_chunks:
            try:
                if self._openai_client is None:
                    self._openai_client = OpenAI()
                spoken = rewrite_for_speech_with_model(
                    chunk,
                    client=self._openai_client,
                    model=self._speech_rewrite_model,
                )
            except Exception as exc:
                print(f"[spoken-error] {exc}", file=sys.stderr)
                continue
            if spoken:
                print("")
                print("[spoken]")
                print(spoken.rstrip())
                if self._speak:
                    speak_text(spoken)
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
    parser.add_argument(
        "--speech-idle-seconds",
        type=float,
        default=1.0,
        help="Minimum idle time before buffered reply text is flushed as a speech chunk.",
    )
    parser.add_argument(
        "--speech-rewrite-model",
        default="gpt-4o-mini",
        help="Model used to rewrite buffered terminal output into speech-ready Chinese.",
    )
    parser.add_argument(
        "--speech-max-chars",
        type=int,
        default=140,
        help="Preferred maximum character count for one buffered speech chunk before it is split.",
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
        speech_idle_seconds=float(args.speech_idle_seconds),
        speech_rewrite_model=args.speech_rewrite_model,
        speech_max_chars=int(args.speech_max_chars),
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
