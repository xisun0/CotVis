from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from betalab.codexapp_server_bridge.launch_terminal_codex import (
    OUTPUT_COMPLETE_MARKER,
    TerminalTarget,
)
from betalab.codexapp_server_bridge import terminal_broadcast_manager as tbm


def _snapshot(*lines: str) -> str:
    return "\n".join(lines)


def test_terminal_broadcast_manager_detects_five_turns_with_lingering_old_markers(
    monkeypatch,
) -> None:
    target = TerminalTarget(window_id=1, tty="/dev/ttys999", initial_prompt="第一轮问题")
    old_reply = ["第一轮回答-句一", "第一轮回答-句二"]

    snapshots = [
        _snapshot(
            "When responding in the terminal, follow this output protocol strictly:",
            "Write your normal user-facing response first.",
            "After the response is fully complete, output this exact marker on its own line:",
            OUTPUT_COMPLETE_MARKER,
            "Rules:",
            "- The marker must appear exactly once per completed assistant turn.",
            "User request:",
            "第一轮问题",
        ),
        _snapshot(
            "When responding in the terminal, follow this output protocol strictly:",
            "User request:",
            "第一轮问题",
            "• 第一轮回答-句一",
        ),
        _snapshot(
            "When responding in the terminal, follow this output protocol strictly:",
            "User request:",
            "第一轮问题",
            "• 第一轮回答-句一",
            "  第一轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
        ),
        _snapshot(
            "• 第一轮回答-句一",
            "  第一轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第二轮问题",
        ),
        _snapshot(
            "• 第一轮回答-句一",
            "  第一轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第二轮问题",
            "• 第二轮回答-句一",
        ),
        _snapshot(
            "• 第一轮回答-句一",
            "  第一轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第二轮问题",
            "• 第二轮回答-句一",
            "  第二轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
        ),
        _snapshot(
            "• 第二轮回答-句一",
            "  第二轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第三轮问题",
        ),
        _snapshot(
            "• 第二轮回答-句一",
            "  第二轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第三轮问题",
            "• 第三轮回答-句一",
        ),
        _snapshot(
            "• 第二轮回答-句一",
            "  第二轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第三轮问题",
            "• 第三轮回答-句一",
            "  第三轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
        ),
        _snapshot(
            "• 第三轮回答-句一",
            "  第三轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第四轮问题",
        ),
        _snapshot(
            "• 第三轮回答-句一",
            "  第三轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第四轮问题",
            "• 第四轮回答-句一",
        ),
        _snapshot(
            "• 第三轮回答-句一",
            "  第三轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第四轮问题",
            "• 第四轮回答-句一",
            "  第四轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
        ),
        _snapshot(
            "• 第四轮回答-句一",
            "  第四轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第五轮问题",
        ),
        _snapshot(
            "• 第四轮回答-句一",
            "  第四轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第五轮问题",
            "• 第五轮回答-句一",
        ),
        _snapshot(
            "• 第四轮回答-句一",
            "  第四轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› 第五轮问题",
            "• 第五轮回答-句一",
            "  第五轮回答-句二",
            f"  {OUTPUT_COMPLETE_MARKER}",
        ),
    ]
    snapshots_iter = iter(snapshots)
    last_snapshot = snapshots[-1]

    def fake_terminal_contents(_target):
        nonlocal last_snapshot
        try:
            last_snapshot = next(snapshots_iter)
        except StopIteration:
            pass
        return last_snapshot

    monkeypatch.setattr(tbm, "get_terminal_name", lambda _target: "Test Terminal")
    monkeypatch.setattr(tbm, "get_terminal_contents", fake_terminal_contents)

    manager = tbm.TerminalBroadcastManager(
        speak=False,
        print_speak_text=False,
        target=target,
        verbose=False,
    )

    events = []
    for _ in snapshots:
        event = manager.poll()
        if event is not None:
            events.append(event.text.strip())

    assert events == [
        "\n".join(old_reply),
        "第二轮回答-句一\n第二轮回答-句二",
        "第三轮回答-句一\n第三轮回答-句二",
        "第四轮回答-句一\n第四轮回答-句二",
        "第五轮回答-句一\n第五轮回答-句二",
    ]
