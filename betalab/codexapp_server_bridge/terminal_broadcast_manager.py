from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

try:
    from .launch_terminal_codex import (
        OUTPUT_COMPLETE_MARKER,
        TERMINAL_OUTPUT_PROTOCOL,
        SessionTurn,
        TerminalTarget,
        load_terminal_binding,
        launch_terminal_codex,
        read_latest_completed_session_turn,
        read_latest_session_user_input,
        resolve_terminal_target_session,
        find_session_path,
    )
except ImportError:
    from launch_terminal_codex import (
        OUTPUT_COMPLETE_MARKER,
        TERMINAL_OUTPUT_PROTOCOL,
        SessionTurn,
        TerminalTarget,
        load_terminal_binding,
        launch_terminal_codex,
        read_latest_completed_session_turn,
        read_latest_session_user_input,
        resolve_terminal_target_session,
        find_session_path,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]
ZH_VOICE = "Eddy (Chinese (China mainland))"
EN_VOICE = "Eddy (English (US))"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_TTS_VOICE = "alloy"
OPENAI_TTS_SPEED = 1.2
SPEECH_REWRITE_SYSTEM_PROMPT = """你正在把终端里的 assistant 输出改写成适合 TTS 朗读的播报文本。

你会同时看到两段信息：
1. 当前轮用户输入
2. assistant 回复

你的目标不是重新创作，也不是优先做摘要，而是生成一段最适合用户此刻直接听到的播报文本。

核心原则：
- 默认高保真保留 assistant 回复中的核心信息、结论和顺序
- 优先做“可听化”处理，而不是“内容重写”
- 只有当原回复明显不适合直接朗读时，才做压缩、概括或重组
- 默认保持 assistant 回复的主要语言，不要自动翻译成中文
- 如果 assistant 回复主要是英文，就输出英文；如果主要是中文，就输出中文；只有用户明确要求翻译时才改变语言
- 不要添加原文没有的新事实
- 输出必须能直接拿去做 TTS
- 不要输出项目符号、编号、Markdown、代码块
- 不要输出“如果你愿意我可以继续”这类尾句
- 不要补空话、套话或没有信息增量的总结句
- 输出应像语音助手正在对用户说话，而不是像项目汇报、文档说明或书面总结

先按下面顺序决策：

第一步：判断用户这一轮更需要听到哪一种内容
- 原文正文
- 结果结论
- 简短进度
- 技术内容的压缩摘要

第二步：默认采用“高保真口语化”
也就是说：
- 尽量保留 assistant 回复中的原有信息和顺序
- 只做轻度处理，让它更适合耳朵去听
- 例如：
  - 去掉 Markdown 链接、反引号、代码格式
  - 把视觉格式改成自然口语
  - 把超长句拆短
  - 删掉明显不适合播报的尾句
  - 合并轻微重复

第三步：只有在以下情况才明显压缩或摘要
- 回复里混有路径、命令、文件树、工具日志、patch、diff、代码块
- 回复主要是技术清单、枚举或过程痕迹，直接朗读会很难听
- 用户更需要的是结果，而不是过程细节

当用户意图是“朗读/背诵/直接复述原文”时：
- 例如：背一下、念一下、朗读、读给我听、复述原文、直接说原话、quote、verbatim、read aloud，以及“读一下这段”、“读正文第一段”、“读这一版”这类阅读型指令
- 优先保留 assistant 回复中真正面向用户的正文内容
- 对这类朗读任务，默认尽量忠实保留原文措辞、顺序和关键信息，不要主动改写句子，不要替换措辞，不要总结化表达
- 不要把说明性外壳、候选列表框架、工具痕迹、结尾补充一起原样念出来
- 可以做轻微口语化整理，但不要改变原文含义和信息顺序

当用户意图不是“原文朗读”时：
- 如果 assistant 回复已经有明确结果，优先播结果，必要时补一句背景
- 如果 assistant 回复主要是过程更新，只输出一句简短进度同步，不展开工具细节
- 如果 assistant 回复主要是技术清单或结构说明，尽量保留原意，但压缩成更容易听懂的表达
- 默认只保留一个最适合朗读的版本，不要输出多个候选表达，除非保留一个备选明显更有帮助

长度原则：
- 默认尽量短，但不能丢掉关键事实
- 简短结果或进度：1 到 2 句
- 中等说明：2 到 4 句
- 只有当 assistant 回复本身就是完整分析，且这些信息对听者明显重要时，才到 5 句以上

输出要求：
- 只输出最终可播报文本本身
- 不要解释你的判断过程"""


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


def get_front_terminal_target() -> TerminalTarget:
    script = (
        'tell application "Terminal"\n'
        "    set targetWindow to front window\n"
        "    set targetTab to selected tab of targetWindow\n"
        '    return (id of targetWindow as text) & ":" & (tty of targetTab)\n'
        "end tell"
    )
    raw = run_osascript(script).strip()
    window_text, tty = raw.split(":", 1)
    return TerminalTarget(window_id=int(window_text), tty=tty)


def build_explicit_session_target(session_id: str) -> TerminalTarget:
    front_target = get_front_terminal_target()
    session_path = find_session_path(session_id)
    return TerminalTarget(
        window_id=front_target.window_id,
        tty=front_target.tty,
        session_id=session_id,
        session_path=str(session_path) if session_path is not None else None,
    )


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


READ_ALOUD_INTENT_PATTERN = re.compile(
    r"(朗读|读给我听|读一下|念一下|背一下|复述原文|直接说原话|read aloud|verbatim|quote)",
    re.IGNORECASE,
)


def is_verbatim_read_request(user_input: str) -> bool:
    cleaned = user_input.strip()
    if not cleaned:
        return False
    return bool(READ_ALOUD_INTENT_PATTERN.search(cleaned))


def extract_verbatim_read_aloud_text(reply: str) -> str:
    cleaned = remove_completion_markers(reply).strip()
    if not cleaned:
        return ""

    quoted_candidates: list[str] = []
    quote_patterns = [
        r"“(?P<body>.+?)”",
        r'"(?P<body>.+?)"',
        r"「(?P<body>.+?)」",
        r"『(?P<body>.+?)』",
    ]
    for pattern in quote_patterns:
        for match in re.finditer(pattern, cleaned, flags=re.DOTALL):
            body = match.group("body").strip()
            if body:
                quoted_candidates.append(body)
    if quoted_candidates:
        return max(quoted_candidates, key=len)

    return ""


def rewrite_for_speech_with_model(
    chunk: str,
    *,
    user_input: str = "",
    client: OpenAI | None = None,
    model: str = "gpt-4o-mini",
) -> str:
    cleaned = remove_completion_markers(chunk).strip()
    if not cleaned:
        return ""
    cleaned_user_input = user_input.strip()
    if is_verbatim_read_request(cleaned_user_input):
        verbatim = extract_verbatim_read_aloud_text(cleaned)
        if verbatim:
            return verbatim

    local_client = client or OpenAI()
    completion = local_client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SPEECH_REWRITE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "下面有两段信息：当前轮用户输入，以及 assistant 的回复。\n"
                    "请输出最适合直接语音播报的文本。\n\n"
                    "要求：\n"
                    "- 默认尽量高保真保留 assistant 回复中的核心信息和顺序\n"
                    "- 只在确实不适合听的时候才压缩或摘要\n"
                    "- 默认保持 assistant 回复的主要语言，不要自动翻译\n"
                    "- 不要复述用户输入，除非这样做对说明结论是必要的\n\n"
                    f"<user_input>\n{cleaned_user_input}\n</user_input>\n\n"
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


def extract_latest_reply_segment(text: str) -> str:
    segments: list[list[str]] = [[]]
    for raw_line in text.splitlines():
        if raw_line.strip() == OUTPUT_COMPLETE_MARKER:
            segments.append([])
            continue
        segments[-1].append(raw_line)
    for segment in reversed(segments):
        cleaned = "\n".join(line for line in segment if line.strip()).strip()
        if cleaned:
            return cleaned
    return ""


def count_completion_marker_lines(text: str) -> int:
    count = 0
    for raw_line in text.splitlines():
        if raw_line.strip() == OUTPUT_COMPLETE_MARKER:
            count += 1
    return count


def has_trailing_completion_marker(text: str) -> bool:
    for raw_line in reversed(text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        return line == OUTPUT_COMPLETE_MARKER
    return False


def reply_fingerprint(text: str) -> str:
    # Terminal reflow frequently changes only line breaks / indentation while
    # leaving the semantic reply unchanged. Ignore all whitespace for
    # completion-level dedupe so a rewrapped old reply is not replayed.
    return re.sub(r"\s+", "", text)


def extract_latest_user_input(text: str) -> str:
    latest = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("›"):
            continue
        candidate = line.removeprefix("›").strip()
        if not candidate:
            continue
        latest = candidate
    return latest


def normalize_user_input_for_display(text: str, target: TerminalTarget | None) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    prefix = f"{TERMINAL_OUTPUT_PROTOCOL}\n\nUser request:\n"
    if cleaned.startswith(prefix):
        cleaned = cleaned[len(prefix) :].strip()
    if target is not None and target.initial_prompt and cleaned == target.initial_prompt.strip():
        return cleaned
    return cleaned


def spoken_reply_fingerprint(text: str) -> str:
    # Ignore punctuation / wrapping noise when suppressing accidental replays.
    alnum_only = re.sub(r"[^\w\u4e00-\u9fff]+", "", text, flags=re.UNICODE)
    return alnum_only.casefold()


def replies_are_effectively_same(current: str, previous: str) -> bool:
    current_fp = spoken_reply_fingerprint(current)
    previous_fp = spoken_reply_fingerprint(previous)
    if not current_fp or not previous_fp:
        return False
    if current_fp == previous_fp:
        return True
    if current_fp in previous_fp or previous_fp in current_fp:
        shorter = min(len(current_fp), len(previous_fp))
        longer = max(len(current_fp), len(previous_fp))
        if longer and shorter / longer >= 0.9:
            return True
    return difflib.SequenceMatcher(a=current_fp, b=previous_fp).ratio() >= 0.95


def strip_injected_prompt_text(text: str, target: TerminalTarget | None) -> str:
    if target is None:
        return text

    ignored_exact_lines = {"User request:"}
    initial_prompt_lines = set()
    # Use short substrings that survive word-wrap inside Codex's box UI.
    ignored_fragments = [
        "responding in the terminal",
        "output protocol strictly",
        "user-facing response first",
        "fully complete, output this exact marker",
        "output this exact marker on its own line",
        "marker on its own line",
        "marker must appear exactly once",
        "marker must be on a line by itself",
        "explain, paraphrase, or discuss the marker",
        "output the marker until the response",
        "place the marker inside code blocks",
        "code blocks, diffs, patches",
        "quoted text, or examples",
        "examples.",
        "emit any other completion markers",
        "include the marker anywhere except",
    ]
    if target.initial_prompt:
        initial_prompt_lines = {
            line.strip() for line in target.initial_prompt.splitlines() if line.strip()
        }

    kept: list[str] = []
    skip_next_marker_line = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if skip_next_marker_line and line == OUTPUT_COMPLETE_MARKER:
            skip_next_marker_line = False
            continue
        skip_next_marker_line = False
        if any(fragment in line for fragment in ignored_fragments):
            if "output this exact marker on its own line" in line or line == "line:":
                skip_next_marker_line = True
            continue
        if line in {"Rules:", "line:"}:
            skip_next_marker_line = True
            continue
        if line in ignored_exact_lines:
            continue
        if line in initial_prompt_lines:
            continue
        if "\\012" in line:
            continue
        kept.append(raw_line)
    return "\n".join(kept)


def compute_increment(previous: str, current: str) -> str:
    if not previous:
        return current
    if current.startswith(previous):
        return current[len(previous) :]
    previous_lines = previous.splitlines()
    current_lines = current.splitlines()
    # Fewer lines than before → user scrolled up, visible content shrank. Not new output.
    if len(current_lines) < len(previous_lines):
        return ""
    matcher = difflib.SequenceMatcher(a=previous_lines, b=current_lines)
    added_lines: list[str] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
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
        if line.startswith("╭") or line.startswith("╰"):
            continue
        if line.startswith("│"):
            line = line.removeprefix("│").rstrip("│").strip()
            if not line:
                continue
        if "esc to interrupt" in line:
            continue
        if "background terminal running" in line:
            continue
        if "gpt-" in line and "left" in line:
            continue
        if line.startswith("gpt-") and "·" in line:
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


ACTIVITY_SOUND = "/System/Library/Sounds/Pop.aiff"
ACTIVITY_INDICATOR_INTERVAL = 1.0  # seconds between activity chimes


class TerminalBroadcastManager:
    def __init__(
        self,
        *,
        speak: bool = False,
        print_speak_text: bool = True,
        target: TerminalTarget | None = None,
        follow_front_window: bool = False,
        speech_rewrite_model: str = "gpt-4o-mini",
        verbose: bool = False,
    ) -> None:
        self._target = load_terminal_binding(target) if target is not None else None
        self._follow_front_window = follow_front_window
        self._last_reply_text = ""
        self._reply_buffer = ""
        self._last_completed_reply_fingerprint = ""
        self._last_emitted_reply_text = ""
        self._last_session_turn_id = ""
        self._last_emitted_user_input = ""
        self._speak = speak
        self._print_speak_text = print_speak_text
        self._speech_rewrite_model = speech_rewrite_model
        self._openai_client: OpenAI | None = None
        self._openai_client_lock = threading.Lock()
        self._last_activity_chime_time = 0.0
        self._verbose = verbose

    def _reset_tracking_for_target_change(self) -> None:
        self._last_reply_text = ""
        self._reply_buffer = ""
        self._last_completed_reply_fingerprint = ""
        self._last_session_turn_id = ""
        self._last_emitted_user_input = ""

    def _sync_front_target(self) -> None:
        if not self._follow_front_window:
            return
        front_target = load_terminal_binding(get_front_terminal_target())
        if self._target is None:
            self._target = front_target
            self._reset_tracking_for_target_change()
            return
        if (
            self._target.window_id != front_target.window_id
            or self._target.tty != front_target.tty
        ):
            self._target = front_target
            self._reset_tracking_for_target_change()
            return
        self._target = front_target

    def _play_activity_chime(self) -> None:
        now = time.time()
        if now - self._last_activity_chime_time < ACTIVITY_INDICATOR_INTERVAL:
            return
        self._last_activity_chime_time = now
        subprocess.Popen(
            ["afplay", ACTIVITY_SOUND],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _chime_until_done(self, stop_event: threading.Event) -> None:
        """Background thread: play a chime every second until stop_event is set."""
        while not stop_event.wait(timeout=ACTIVITY_INDICATOR_INTERVAL):
            subprocess.Popen(
                ["afplay", ACTIVITY_SOUND],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        self._last_activity_chime_time = time.time()

    def _refresh_session_binding(self, latest_user_input: str) -> None:
        if self._target is None:
            return
        refreshed = load_terminal_binding(self._target)
        if refreshed.session_id and refreshed.session_path:
            self._target = refreshed
            return
        prompt_text: str | None = None
        if refreshed.initial_prompt and not refreshed.session_id:
            prompt_text = (
                f"{TERMINAL_OUTPUT_PROTOCOL}\n\nUser request:\n{refreshed.initial_prompt}"
            )
        elif latest_user_input:
            prompt_text = latest_user_input
        if not prompt_text:
            self._target = refreshed
            return
        self._target = resolve_terminal_target_session(
            refreshed,
            prompt_text=prompt_text,
            timeout_seconds=0.0,
        )

    def _build_event_from_reply(
        self,
        *,
        window_name: str,
        reply_text: str,
        timestamp: float,
        user_input: str,
    ) -> BroadcastEvent | None:
        if replies_are_effectively_same(reply_text, self._last_emitted_reply_text):
            if self._verbose:
                print("[verbose] suppress_replay same_as_last_emitted=True", file=sys.stderr)
            return None
        self._last_emitted_reply_text = reply_text

        if self._print_speak_text:
            print("")
            print("[reply]")
            print(reply_text.rstrip())

        event = BroadcastEvent(
            window_name=window_name,
            text=reply_text,
            timestamp=timestamp,
        )

        if self._speak or self._print_speak_text:
            threading.Thread(
                target=self._rewrite_and_speak,
                args=(reply_text, user_input),
                daemon=True,
            ).start()

        return event

    def _poll_session_event(self, window_name: str, latest_user_input: str) -> BroadcastEvent | None:
        if self._target is None or not self._target.session_path:
            return None
        session_turn = read_latest_completed_session_turn(self._target.session_path)
        if session_turn is None:
            return None
        if session_turn.turn_id == self._last_session_turn_id:
            return None
        self._last_session_turn_id = session_turn.turn_id
        reply_text = remove_completion_markers(session_turn.text).strip()
        if not reply_text:
            return None
        timestamp = (
            float(session_turn.completed_at)
            if session_turn.completed_at is not None
            else time.time()
        )
        return self._build_event_from_reply(
            window_name=window_name,
            reply_text=reply_text,
            timestamp=timestamp,
            user_input=latest_user_input,
        )

    def _get_latest_session_user_input(self) -> str:
        if self._target is None or not self._target.session_path:
            return ""
        return read_latest_session_user_input(self._target.session_path) or ""

    def _maybe_print_user_input(self, user_input: str) -> None:
        normalized = normalize_user_input_for_display(user_input, self._target)
        if not normalized:
            return
        if normalized == self._last_emitted_user_input:
            return
        self._last_emitted_user_input = normalized
        print("")
        print("[user_input]")
        print(normalized.rstrip())

    def poll(self) -> BroadcastEvent | None:
        self._sync_front_target()
        window_name = get_terminal_name(self._target)
        current = get_terminal_contents(self._target)
        terminal_user_input = extract_latest_user_input(current)
        self._refresh_session_binding(terminal_user_input)
        latest_user_input = self._get_latest_session_user_input() or terminal_user_input
        self._maybe_print_user_input(latest_user_input)
        session_event = self._poll_session_event(window_name, latest_user_input)
        if session_event is not None:
            if self._verbose and self._target is not None:
                print(
                    f"[verbose] session_source=session_file session_id={self._target.session_id!r}",
                    file=sys.stderr,
                )
            return session_event
        if self._target is not None and self._target.session_path:
            if self._verbose:
                print(
                    f"[verbose] session_bound awaiting_new_turn session_id={self._target.session_id!r}",
                    file=sys.stderr,
                )
            return None
        extracted_reply_text = extract_codex_reply_text(current)
        stripped_reply_text = strip_injected_prompt_text(extracted_reply_text, self._target)
        current_marker_count = count_completion_marker_lines(stripped_reply_text)
        current_reply_text = extract_latest_reply_segment(stripped_reply_text)
        current_reply_fingerprint = reply_fingerprint(current_reply_text)
        marker_completed = has_trailing_completion_marker(stripped_reply_text)
        completed_reply_is_new = marker_completed and (
            current_reply_fingerprint != self._last_completed_reply_fingerprint
        )
        reply_increment = compute_increment(self._last_reply_text, current_reply_text)
        if len(current_reply_text.splitlines()) >= len(self._last_reply_text.splitlines()):
            self._last_reply_text = current_reply_text

        if self._verbose:
            raw_has_marker = OUTPUT_COMPLETE_MARKER in current
            extracted_has_marker = OUTPUT_COMPLETE_MARKER in extracted_reply_text
            stripped_has_marker = OUTPUT_COMPLETE_MARKER in stripped_reply_text
            print(
                f"[verbose] marker_now={current_marker_count} completed={marker_completed} completed_is_new={completed_reply_is_new} "
                f"raw_has_marker={raw_has_marker} "
                f"extracted_has_marker={extracted_has_marker} "
                f"stripped_has_marker={stripped_has_marker} "
                f"increment_len={len(reply_increment.strip())} "
                f"buffer_len={len(self._reply_buffer)} "
                f"reply_lines={len(current_reply_text.splitlines())} "
                f"extracted_lines={len(extracted_reply_text.splitlines())} "
                f"stripped_lines={len(stripped_reply_text.splitlines())} "
                f"user_input={latest_user_input!r} "
                f"session_id={None if self._target is None else self._target.session_id!r}",
                file=sys.stderr,
            )
            if extracted_reply_text != stripped_reply_text:
                print(
                    f"[verbose] strip_delta extracted_len={len(extracted_reply_text.strip())} "
                    f"stripped_len={len(stripped_reply_text.strip())}",
                    file=sys.stderr,
                )
            if reply_increment.strip():
                preview = reply_increment.strip()[:80].replace("\n", "↵")
                print(f"[verbose] increment preview: {preview!r}", file=sys.stderr)

        if reply_increment.strip():
            if self._reply_buffer:
                self._reply_buffer = f"{self._reply_buffer}\n{reply_increment.strip()}"
            else:
                self._reply_buffer = reply_increment.strip()
            if self._speak and not marker_completed:
                self._play_activity_chime()

        if not completed_reply_is_new:
            return None

        if not self._reply_buffer.strip():
            # Completion can become visible in the same poll where no diff-style
            # increment is detected; fall back to the full current reply if it
            # differs from the last completed turn.
            self._reply_buffer = current_reply_text.strip()

        if not self._reply_buffer.strip():
            return None

        # Force-reset tracking to current terminal state so the next turn starts
        # fresh, regardless of whether the terminal UI shrank after this turn.
        self._last_reply_text = current_reply_text
        self._last_completed_reply_fingerprint = current_reply_fingerprint

        reply_text = self._reply_buffer
        self._reply_buffer = ""
        return self._build_event_from_reply(
            window_name=window_name,
            reply_text=reply_text,
            timestamp=time.time(),
            user_input=latest_user_input,
        )

    def _get_openai_client(self) -> OpenAI:
        with self._openai_client_lock:
            if self._openai_client is None:
                self._openai_client = OpenAI()
            return self._openai_client

    def _rewrite_and_speak(self, reply_text: str, user_input: str) -> None:
        stop_chime = threading.Event()
        if self._speak:
            threading.Thread(
                target=self._chime_until_done, args=(stop_chime,), daemon=True
            ).start()

        try:
            spoken = rewrite_for_speech_with_model(
                reply_text,
                user_input=user_input,
                client=self._get_openai_client(),
                model=self._speech_rewrite_model,
            )
        except Exception as exc:
            print(f"[spoken-error] rewrite failed: {exc}", file=sys.stderr)
            return
        finally:
            stop_chime.set()

        if not spoken:
            return

        if self._print_speak_text:
            print("")
            print("[spoken]")
            print(spoken.rstrip())

        if self._speak:
            try:
                speak_text(spoken)
            except Exception as exc:
                print(f"[spoken-error] tts failed: {exc}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Listen to front Terminal.app content updates and optionally speak them.",
    )
    parser.add_argument(
        "--launch-codex",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Open a fresh Terminal.app window and start codex before listening. Enabled by default.",
    )
    parser.add_argument(
        "--initial-prompt",
        default=None,
        help="Optional initial prompt used with --launch-codex.",
    )
    parser.add_argument(
        "--working-directory",
        default=None,
        help="Working directory for a newly launched Codex session. Defaults to the current shell directory.",
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
        default=0.0,
        help="Maximum listen duration before exit. Default is 0, which listens until Ctrl+C.",
    )
    parser.add_argument(
        "--speak",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use macOS say to read newly detected terminal text. Enabled by default.",
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
        "--session-id",
        default=None,
        help="Explicit Codex session ID to read backend replies from. Locks to the current front Terminal tab instead of following window switches.",
    )
    parser.add_argument(
        "--speech-rewrite-model",
        default="gpt-4o-mini",
        help="Model used to rewrite the completed reply into speech-ready text.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-poll pipeline diagnostics to stderr.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    target: TerminalTarget | None = None
    follow_front_window = bool(args.front_only)
    if args.session_id:
        target = build_explicit_session_target(str(args.session_id).strip())
        follow_front_window = False
    elif args.front_only:
        target = None
    elif args.launch_codex:
        launch_dir = str(Path(args.working_directory).resolve()) if args.working_directory else os.getcwd()
        target = launch_terminal_codex(
            working_directory=launch_dir,
            initial_prompt=args.initial_prompt,
        )
        time.sleep(2.0)

    manager = TerminalBroadcastManager(
        speak=bool(args.speak) and not bool(args.silent_debug),
        print_speak_text=True,
        target=target,
        follow_front_window=follow_front_window,
        speech_rewrite_model=args.speech_rewrite_model,
        verbose=bool(args.verbose),
    )
    started_at = time.time()
    if target is None:
        print(f"[listen] mode=front window={get_front_terminal_name()}")
    else:
        session_suffix = f" session_id={target.session_id}" if target.session_id else ""
        print(
            f"[listen] mode=bound window_id={target.window_id} tty={target.tty} "
            f"window={get_terminal_name(target)}{session_suffix}"
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
