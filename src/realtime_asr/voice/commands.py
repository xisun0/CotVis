from __future__ import annotations

from dataclasses import dataclass


TRIM_PUNCTUATION = " \t\r\n.,!?;:()[]{}\"'`。，！？；：（）【】《》“”‘’"


@dataclass(slots=True)
class NormalizedCommand:
    name: str
    argument: str | None = None


@dataclass(slots=True)
class ClassifiedUtterance:
    kind: str
    command: NormalizedCommand | None = None
    text: str | None = None


COMMAND_ALIASES: dict[str, str] = {
    "pause": "pause",
    "stop": "pause",
    "暂停": "pause",
    "停一下": "pause",
    "暂停一下": "pause",
    "先停一下": "pause",
    "停": "pause",
    "resume": "resume",
    "continue": "resume",
    "继续": "resume",
    "继续读": "resume",
    "接着读": "resume",
    "next": "next",
    "下一句": "next",
    "读下一句": "next",
    "next sentence": "next",
    "previous": "previous",
    "上一句": "previous",
    "重复上一句": "previous",
    "again": "again",
    "重复": "again",
    "再来一遍": "again",
    "再读一遍": "again",
    "重读这句": "again",
    "重复这句": "again",
    "paragraph": "paragraph",
    "本段": "paragraph",
    "读这段": "paragraph",
    "读下这段": "paragraph",
    "读一下这段": "paragraph",
    "读下这个段落": "paragraph",
    "读一下这个段落": "paragraph",
    "重读这个段落": "paragraph",
    "重读本段": "paragraph",
    "next paragraph": "next paragraph",
    "下一段": "next paragraph",
    "读下一段": "next paragraph",
    "previous paragraph": "previous paragraph",
    "上一段": "previous paragraph",
    "next subsection": "next subsection",
    "下一小节": "next subsection",
    "previous subsection": "previous subsection",
    "上一小节": "previous subsection",
    "next section": "next section",
    "下一节": "next section",
    "下一章节": "next section",
    "previous section": "previous section",
    "上一节": "previous section",
    "上一章节": "previous section",
    "status": "status",
    "状态": "status",
    "help": "help",
    "帮助": "help",
    "quit": "quit",
    "退出": "quit",
}


def normalize_command(raw: str) -> NormalizedCommand | None:
    text = " ".join((raw or "").strip().split())
    text = text.strip(TRIM_PUNCTUATION)
    if not text:
        return NormalizedCommand(name="next")

    lowered = text.lower()
    if lowered.startswith("jump paragraph "):
        value = lowered.removeprefix("jump paragraph ").strip()
        return NormalizedCommand(name="jump paragraph", argument=value)
    if text.startswith("跳到第") and text.endswith("段"):
        value = text.removeprefix("跳到第").removesuffix("段").strip()
        return NormalizedCommand(name="jump paragraph", argument=value)
    if lowered.startswith("jump match "):
        value = text[len("jump match ") :].strip()
        return NormalizedCommand(name="jump match", argument=value or None)
    if text.startswith("跳到 ") or text.startswith("跳转到 "):
        if text.startswith("跳到 "):
            value = text[len("跳到 ") :].strip()
        else:
            value = text[len("跳转到 ") :].strip()
        return NormalizedCommand(name="jump match", argument=value or None)

    mapped = COMMAND_ALIASES.get(lowered)
    if mapped is not None:
        return NormalizedCommand(name=mapped)
    mapped = COMMAND_ALIASES.get(text)
    if mapped is not None:
        return NormalizedCommand(name=mapped)
    return None


def classify_utterance(raw: str) -> ClassifiedUtterance:
    text = " ".join((raw or "").strip().split())
    text = text.strip(TRIM_PUNCTUATION)
    if not text:
        return ClassifiedUtterance(kind="unknown", text=text)

    command = normalize_command(text)
    if command is not None:
        return ClassifiedUtterance(kind="control", command=command, text=text)

    return ClassifiedUtterance(kind="request", text=text)
