from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from betalab.codexapp_server_bridge import launch_terminal_codex as ltc
from betalab.codexapp_server_bridge.launch_terminal_codex import (
    OUTPUT_COMPLETE_MARKER,
    TerminalTarget,
)
from betalab.codexapp_server_bridge import terminal_broadcast_manager as tbm


def _snapshot(*lines: str) -> str:
    return "\n".join(lines)


def test_resolve_terminal_target_session_from_history(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "history.jsonl"
    sessions_dir = tmp_path / "sessions"
    binding_dir = tmp_path / "bindings"
    session_id = "019d9999-abcd-7000-8000-testsession0001"
    session_path = sessions_dir / "2026" / "04" / "12" / f"rollout-2026-04-12T20-00-00-{session_id}.jsonl"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        (
            '{"timestamp":"2026-04-12T20:00:00.000Z","type":"session_meta",'
            '"payload":{"id":"%s","cwd":"/tmp/project"}}\n'
        )
        % session_id,
        encoding="utf-8",
    )
    prompt_text = ltc.build_protocol_prompt("测试问题")
    history_path.write_text(
        (
            '{"session_id":"%s","ts":1001,"text":%s}\n'
        )
        % (session_id, json.dumps(prompt_text, ensure_ascii=False)),
        encoding="utf-8",
    )

    monkeypatch.setattr(ltc, "CODEX_HISTORY_PATH", history_path)
    monkeypatch.setattr(ltc, "CODEX_SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(ltc, "TERMINAL_BINDINGS_DIR", binding_dir)

    target = TerminalTarget(
        window_id=10,
        tty="/dev/ttys010",
        initial_prompt="测试问题",
        working_directory="/tmp/project",
        launched_at=1000.0,
    )

    resolved = ltc.resolve_terminal_target_session(target, timeout_seconds=0.0)

    assert resolved.session_id == session_id
    assert resolved.session_path == str(session_path)
    assert ltc.load_terminal_binding(resolved).session_id == session_id


def test_terminal_broadcast_manager_prefers_completed_session_turn(
    tmp_path,
    monkeypatch,
) -> None:
    session_path = tmp_path / "session.jsonl"
    session_path.write_text(
        "\n".join([
            '{"timestamp":"2026-04-12T20:00:00.000Z","type":"session_meta","payload":{"id":"sid","cwd":"/tmp/project"}}',
            '{"timestamp":"2026-04-12T20:00:03.000Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-1","last_agent_message":"来自后台 session 的最终回复","completed_at":1776020003}}',
            "",
        ]),
        encoding="utf-8",
    )
    target = TerminalTarget(
        window_id=1,
        tty="/dev/ttys999",
        initial_prompt="问题",
        working_directory="/tmp/project",
        launched_at=1776020000.0,
        session_id="sid",
        session_path=str(session_path),
    )

    monkeypatch.setattr(tbm, "get_terminal_name", lambda _target: "Test Terminal")
    monkeypatch.setattr(tbm, "get_terminal_contents", lambda _target: _snapshot("› 问题"))

    manager = tbm.TerminalBroadcastManager(
        speak=False,
        print_speak_text=False,
        target=target,
        verbose=False,
    )

    first = manager.poll()
    second = manager.poll()

    assert first is not None
    assert first.text == "来自后台 session 的最终回复"
    assert second is None


def test_read_latest_session_user_input_prefers_session_records(tmp_path) -> None:
    session_path = tmp_path / "session.jsonl"
    session_path.write_text(
        "\n".join([
            '{"timestamp":"2026-04-12T20:00:00.000Z","type":"session_meta","payload":{"id":"sid","cwd":"/tmp/project"}}',
            '{"timestamp":"2026-04-12T20:00:01.000Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"第一轮问题"}]}}',
            '{"timestamp":"2026-04-12T20:00:02.000Z","type":"event_msg","payload":{"type":"user_message","message":"第二轮问题"}}',
            "",
        ]),
        encoding="utf-8",
    )

    assert ltc.read_latest_session_user_input(session_path) == "第二轮问题"


def test_terminal_broadcast_manager_prints_user_input_from_session(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    session_path = tmp_path / "session.jsonl"
    prompt_text = ltc.build_protocol_prompt("请把这句话改得更学术一些：你好，我是小气。")
    session_path.write_text(
        "\n".join([
            '{"timestamp":"2026-04-12T20:00:00.000Z","type":"session_meta","payload":{"id":"sid","cwd":"/tmp/project"}}',
            json.dumps({
                "timestamp": "2026-04-12T20:00:01.000Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": prompt_text},
            }, ensure_ascii=False),
            '{"timestamp":"2026-04-12T20:00:03.000Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-1","last_agent_message":"后台回复","completed_at":1776020003}}',
            "",
        ]),
        encoding="utf-8",
    )
    target = TerminalTarget(
        window_id=1,
        tty="/dev/ttys999",
        initial_prompt="请把这句话改得更学术一些：你好，我是小气。",
        working_directory="/tmp/project",
        launched_at=1776020000.0,
        session_id="sid",
        session_path=str(session_path),
    )

    monkeypatch.setattr(tbm, "get_terminal_name", lambda _target: "Test Terminal")
    monkeypatch.setattr(tbm, "get_terminal_contents", lambda _target: _snapshot("› ignored"))

    manager = tbm.TerminalBroadcastManager(
        speak=False,
        print_speak_text=True,
        target=target,
        verbose=False,
    )

    manager.poll()
    out = capsys.readouterr().out

    assert "[user_input]" in out
    assert "请把这句话改得更学术一些：你好，我是小气。" in out
    assert "[reply]" in out
    assert "后台回复" in out


# Date noted: 2026-04-12
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


def test_terminal_broadcast_manager_does_not_repeat_same_reply_after_reflow(
    monkeypatch,
) -> None:
    target = TerminalTarget(window_id=1, tty="/dev/ttys999", initial_prompt="问题")
    snapshots = [
        _snapshot(
            "User request:",
            "问题",
            "• 这是同一轮的完整回答 第一部分 第二部分",
            f"  {OUTPUT_COMPLETE_MARKER}",
        ),
        _snapshot(
            "User request:",
            "问题",
            "• 这是同一轮的完整回答",
            "  第一部分",
            "  第二部分",
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

    first = manager.poll()
    second = manager.poll()

    assert first is not None
    assert second is None


def test_terminal_broadcast_manager_does_not_repeat_same_english_reply_after_reflow(
    monkeypatch,
) -> None:
    target = TerminalTarget(window_id=1, tty="/dev/ttys999", initial_prompt="question")
    snapshots = [
        _snapshot(
            "User request:",
            "question",
            "• this is the same reply with a terminal reflow test",
            f"  {OUTPUT_COMPLETE_MARKER}",
        ),
        _snapshot(
            "User request:",
            "question",
            "• this is the same reply",
            "  with a terminal reflow test",
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

    first = manager.poll()
    second = manager.poll()

    assert first is not None
    assert second is None


def test_terminal_broadcast_manager_ignores_old_completed_reply_after_new_user_input(
    monkeypatch,
) -> None:
    target = TerminalTarget(window_id=1, tty="/dev/ttys999", initial_prompt="old question")
    snapshots = [
        _snapshot(
            "• old reply first line",
            "  old reply second line",
            f"  {OUTPUT_COMPLETE_MARKER}",
        ),
        _snapshot(
            "• old reply first line",
            "  old reply second line",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› new question",
        ),
        _snapshot(
            "• old reply first line wrapped",
            "  differently after terminal reflow",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› new question",
            "Thinking…",
        ),
        _snapshot(
            "• old reply first line wrapped",
            "  differently after terminal reflow",
            f"  {OUTPUT_COMPLETE_MARKER}",
            "› new question",
            "• new reply first line",
            "  new reply second line",
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

    first = manager.poll()
    second = manager.poll()
    third = manager.poll()
    fourth = manager.poll()

    assert first is not None
    assert first.text.strip() == "old reply first line\nold reply second line"
    assert second is None
    assert third is None
    assert fourth is not None
    assert fourth.text.strip() == "new reply first line\nnew reply second line"
