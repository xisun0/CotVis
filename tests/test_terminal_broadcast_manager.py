from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from betalab.codexapp_server_bridge import launch_terminal_codex as ltc
from betalab.codexapp_server_bridge.launch_terminal_codex import (
    DEFAULT_STARTUP_CHECK_PROMPT,
    OUTPUT_COMPLETE_MARKER,
    TerminalTarget,
)
from betalab.codexapp_server_bridge import terminal_broadcast_manager as tbm


def _snapshot(*lines: str) -> str:
    return "\n".join(lines)


def _disable_front_tab_authorization_fallback(
    monkeypatch,
    *,
    front_target: TerminalTarget | None = None,
) -> None:
    monkeypatch.setattr(
        tbm,
        "get_front_terminal_target",
        lambda: front_target or TerminalTarget(window_id=1, tty="/dev/ttys999"),
    )


def _disable_activity_chime(monkeypatch) -> None:
    monkeypatch.setattr(tbm.TerminalBroadcastManager, "_play_activity_chime", lambda self: None)


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


def test_build_protocol_prompt_uses_default_startup_check_prompt() -> None:
    prompt = ltc.build_protocol_prompt(DEFAULT_STARTUP_CHECK_PROMPT)
    assert DEFAULT_STARTUP_CHECK_PROMPT in prompt
    assert OUTPUT_COMPLETE_MARKER in prompt


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
    _disable_front_tab_authorization_fallback(monkeypatch, front_target=target)

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


def test_terminal_broadcast_manager_front_only_resolves_session_and_uses_backend_reply(
    tmp_path,
    monkeypatch,
) -> None:
    session_path = tmp_path / "session.jsonl"
    session_path.write_text(
        "\n".join([
            '{"timestamp":"2026-04-12T20:00:00.000Z","type":"session_meta","payload":{"id":"sid","cwd":"/tmp/project"}}',
            '{"timestamp":"2026-04-12T20:00:03.000Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-1","last_agent_message":"来自 front-only 后台 session 的最终回复","completed_at":1776020003}}',
            "",
        ]),
        encoding="utf-8",
    )
    front_target = TerminalTarget(
        window_id=1,
        tty="/dev/ttys999",
        session_id="sid",
        session_path=str(session_path),
    )

    monkeypatch.setattr(tbm, "get_front_terminal_target", lambda: front_target)
    monkeypatch.setattr(tbm, "load_terminal_binding", lambda target: target)
    monkeypatch.setattr(tbm, "get_terminal_name", lambda _target: "Front Terminal")
    monkeypatch.setattr(tbm, "get_terminal_contents", lambda _target: _snapshot("› 问题"))

    manager = tbm.TerminalBroadcastManager(
        speak=False,
        print_speak_text=False,
        target=None,
        follow_front_window=True,
        verbose=False,
    )

    event = manager.poll()

    assert event is not None
    assert event.text == "来自 front-only 后台 session 的最终回复"


def test_build_explicit_session_target_uses_front_tab_and_session_path(
    tmp_path,
    monkeypatch,
) -> None:
    session_path = tmp_path / "session.jsonl"
    session_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        tbm,
        "get_front_terminal_target",
        lambda: TerminalTarget(window_id=7, tty="/dev/ttys777"),
    )
    monkeypatch.setattr(tbm, "find_session_path", lambda session_id: session_path)

    target = tbm.build_explicit_session_target("sid")

    assert target.window_id == 7
    assert target.tty == "/dev/ttys777"
    assert target.session_id == "sid"
    assert target.session_path == str(session_path)


def test_find_terminal_target_for_session_uses_saved_binding(
    tmp_path,
    monkeypatch,
) -> None:
    binding_dir = tmp_path / "bindings"
    sessions_dir = tmp_path / "sessions"
    session_id = "sid"
    session_path = sessions_dir / "2026" / "04" / "23" / f"rollout-{session_id}.jsonl"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(ltc, "TERMINAL_BINDINGS_DIR", binding_dir)
    monkeypatch.setattr(ltc, "CODEX_SESSIONS_DIR", sessions_dir)

    ltc.save_terminal_binding(
        TerminalTarget(
            window_id=9,
            tty="/dev/ttys009",
            launched_at=100.0,
            session_id=session_id,
            session_path=str(session_path),
        )
    )
    ltc.save_terminal_binding(
        TerminalTarget(
            window_id=5,
            tty="/dev/ttys005",
            launched_at=50.0,
            session_id=session_id,
            session_path=str(session_path),
        )
    )

    target = ltc.find_terminal_target_for_session(session_id)

    assert target is not None
    assert target.window_id == 9
    assert target.tty == "/dev/ttys009"
    assert target.session_id == session_id
    assert target.session_path == str(session_path)


def test_main_session_id_prints_warning_when_binding_not_found(monkeypatch, capsys) -> None:
    target = TerminalTarget(
        window_id=9,
        tty="/dev/ttys009",
        session_id="sid",
        session_path="/tmp/session.jsonl",
        note="[warning] session-id target tab was not found in saved bindings; falling back to the current front Terminal tab.",
    )

    monkeypatch.setattr(sys, "argv", ["codex-speak", "--session-id", "sid"])
    monkeypatch.setattr(tbm, "build_explicit_session_target", lambda session_id: target)
    monkeypatch.setattr(tbm, "get_terminal_name", lambda _target: "Pinned Terminal")

    class FakeManager:
        def __init__(self, **kwargs):
            pass

        def poll(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(tbm, "TerminalBroadcastManager", FakeManager)

    exit_code = tbm.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "[warning] session-id target tab was not found in saved bindings" in out


def test_main_front_mode_prints_window_id_and_tty(monkeypatch, capsys) -> None:
    front_target = TerminalTarget(window_id=12, tty="/dev/ttys012")

    monkeypatch.setattr(sys, "argv", ["codex-speak", "--no-launch-codex", "--front-only"])
    monkeypatch.setattr(tbm, "get_front_terminal_target", lambda: front_target)
    monkeypatch.setattr(tbm, "get_front_terminal_name", lambda: "Front Terminal")

    class FakeManager:
        def __init__(self, **kwargs):
            pass

        def poll(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(tbm, "TerminalBroadcastManager", FakeManager)

    exit_code = tbm.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "[listen] mode=front window_id=12 tty=/dev/ttys012 window=Front Terminal" in out


def test_terminal_broadcast_manager_verbose_lines_include_window_id_and_tty(
    monkeypatch,
    capsys,
) -> None:
    target = TerminalTarget(window_id=7, tty="/dev/ttys777", initial_prompt="question")
    monkeypatch.setattr(tbm, "get_terminal_name", lambda _target: "Test Terminal")
    monkeypatch.setattr(tbm, "get_terminal_contents", lambda _target: _snapshot("› question"))

    manager = tbm.TerminalBroadcastManager(
        speak=False,
        print_speak_text=False,
        target=target,
        verbose=True,
    )

    manager.poll()
    err = capsys.readouterr().err

    assert "window_id=7 tty=/dev/ttys777" in err


def test_load_terminal_binding_keeps_explicit_session_over_stale_binding(
    tmp_path,
    monkeypatch,
) -> None:
    binding_dir = tmp_path / "bindings"
    monkeypatch.setattr(ltc, "TERMINAL_BINDINGS_DIR", binding_dir)

    stale_target = TerminalTarget(
        window_id=7,
        tty="/dev/ttys777",
        session_id="old-session",
        session_path="/tmp/old-session.jsonl",
    )
    ltc.save_terminal_binding(stale_target)

    explicit_target = TerminalTarget(
        window_id=7,
        tty="/dev/ttys777",
        session_id="new-session",
        session_path="/tmp/new-session.jsonl",
    )

    loaded = ltc.load_terminal_binding(explicit_target)

    assert loaded.session_id == "new-session"
    assert loaded.session_path == "/tmp/new-session.jsonl"


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
    _disable_front_tab_authorization_fallback(monkeypatch, front_target=target)

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


def test_rewrite_for_speech_with_model_includes_user_input_context(monkeypatch) -> None:
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            class Message:
                content = "播报文本"

            class Choice:
                message = Message()

            class Completion:
                choices = [Choice()]

            return Completion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    spoken = tbm.rewrite_for_speech_with_model(
        "assistant reply",
        user_input="user asks for a concise summary",
        client=FakeClient(),
    )

    assert spoken == "播报文本"
    system_message = captured["messages"][0]["content"]
    user_message = captured["messages"][1]["content"]
    assert "不要自动翻译成中文" in system_message
    assert "读正文第一段" in system_message
    assert "<user_input>\nuser asks for a concise summary\n</user_input>" in user_message
    assert "<chunk>\nassistant reply\n</chunk>" in user_message


def test_rewrite_for_speech_with_model_returns_exact_quoted_text_for_read_aloud() -> None:
    class FailingCompletions:
        def create(self, **kwargs):
            raise AssertionError("model should not be called for verbatim read-aloud")

    class FailingChat:
        completions = FailingCompletions()

    class FailingClient:
        chat = FailingChat()

    spoken = tbm.rewrite_for_speech_with_model(
        (
            "我不能直接在终端里发语音，但可以把下一段原文贴出来，方便你自己朗读或让我帮你改成更适合朗读的口语版：\n\n"
            "“近十年来，编程教育在全球范围内逐渐升温，中国少儿编程市场也进入快速发展阶段。学习编程被普遍认为有助于培养儿童的逻辑思维与问题解决能力，逐渐受到家长关注。与此同时，4G网络的普及推动了直播技术在教育场景中的广泛应用，在线教育模式由此也得以快速发展，进一步扩大了编程教育的地域覆盖范围。随着越来越多品牌涌入这一赛道，市场竞争迅速加剧。”\n\n"
            "如果你要，我下一条可以直接把它改成“适合朗读的顺口版本”。"
        ),
        user_input="那你朗读一下下一段给我听",
        client=FailingClient(),
    )

    assert spoken == (
        "近十年来，编程教育在全球范围内逐渐升温，中国少儿编程市场也进入快速发展阶段。学习编程被普遍认为有助于培养儿童的逻辑思维与问题解决能力，逐渐受到家长关注。与此同时，4G网络的普及推动了直播技术在教育场景中的广泛应用，在线教育模式由此也得以快速发展，进一步扩大了编程教育的地域覆盖范围。随着越来越多品牌涌入这一赛道，市场竞争迅速加剧。"
    )


def test_rewrite_for_speech_with_model_returns_exact_first_paragraph_for_reading_request() -> None:
    class FailingCompletions:
        def create(self, **kwargs):
            raise AssertionError("model should not be called for verbatim reading")

    class FailingChat:
        completions = FailingCompletions()

    class FailingClient:
        chat = FailingChat()

    spoken = tbm.rewrite_for_speech_with_model(
        (
            "以 `tex` 为准，正文第一段是：\n\n"
            "“2022年，在一次管理层会议上，核桃编程 COO 齐峰走进会议室，手中拿着一份刚出炉的定价实验报告。过去一个多月，公司围绕主打课程的定价进行了多轮实验，尝试评估将售价从2699元上调至2899元的可行性。实验结果显示，售价上调200元后，相关量化指标并未出现显著下滑：涨价似乎并未拖累销售转化率。若这一趋势能够持续，提价无疑将提升公司的收入水平。然而，这些结果是否足以支撑一次正式调价，仍需管理层讨论决定。”"
        ),
        user_input="那你现在读一下案例正文第一段",
        client=FailingClient(),
    )

    assert spoken == (
        "2022年，在一次管理层会议上，核桃编程 COO 齐峰走进会议室，手中拿着一份刚出炉的定价实验报告。过去一个多月，公司围绕主打课程的定价进行了多轮实验，尝试评估将售价从2699元上调至2899元的可行性。实验结果显示，售价上调200元后，相关量化指标并未出现显著下滑：涨价似乎并未拖累销售转化率。若这一趋势能够持续，提价无疑将提升公司的收入水平。然而，这些结果是否足以支撑一次正式调价，仍需管理层讨论决定。"
    )


def test_main_session_id_disables_front_only_follow(monkeypatch) -> None:
    captured = {}
    target = TerminalTarget(
        window_id=9,
        tty="/dev/ttys009",
        session_id="sid",
        session_path="/tmp/session.jsonl",
    )

    monkeypatch.setattr(sys, "argv", ["codex-speak", "--session-id", "sid", "--front-only"])
    monkeypatch.setattr(tbm, "build_explicit_session_target", lambda session_id: target)
    monkeypatch.setattr(tbm, "get_terminal_name", lambda _target: "Pinned Terminal")

    class FakeManager:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def poll(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(tbm, "TerminalBroadcastManager", FakeManager)

    exit_code = tbm.main()

    assert exit_code == 0
    assert captured["target"] == target
    assert captured["follow_front_window"] is False


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
    _disable_activity_chime(monkeypatch)

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
    _disable_activity_chime(monkeypatch)

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
    _disable_activity_chime(monkeypatch)

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


def test_detect_authorization_prompt_from_terminal_ui() -> None:
    prompt = tbm.detect_authorization_prompt(
        _snapshot(
            "│ Do you want to allow this action?",
            "│ Allow once",
            "│ Allow always",
            "│ Deny",
        )
    )

    assert prompt == "Do you want to allow this action?"


def test_detect_authorization_prompt_from_codex_run_command_ui() -> None:
    prompt = tbm.detect_authorization_prompt(
        _snapshot(
            "Would you like to run the following command?",
            "Reason: Do you want me to retry the GPT Image 2 polish pass with external network access?",
            "$ python3 /Users/sxi/.codex/skills/spotpaper/scripts/image2_edit.py -i input.png -o output.png",
            "› 1. Yes, proceed (y)",
            "2. Yes, and don't ask again for commands that start with `python3 /Users/sxi/.codex/skills/spotpaper/scripts/image2_edit.py` (p)",
            "3. No, and tell Codex what to do differently (esc)",
        )
    )

    assert prompt == "Would you like to run the following command?"


def test_detect_authorization_prompt_from_wrapped_codex_run_command_ui() -> None:
    prompt = tbm.detect_authorization_prompt(
        _snapshot(
            "Would you like to run the following",
            "command?",
            "Reason: Do you want me to retry the GPT Image 2 polish pass with external network access?",
            "› 1. Yes, proceed (y)",
            "2. Yes, and don't ask again for commands that start with `python3 /Users/sxi/.codex/skills/spotpaper/scripts/image2_edit.py` (p)",
            "3. No, and tell Codex what to do differently (esc)",
        )
    )

    assert prompt == "Would you like to run the following command?"


def test_detect_authorization_prompt_from_headline_only_prefix() -> None:
    prompt = tbm.detect_authorization_prompt(
        _snapshot(
            "Would you like to run the following",
            "Reason: Do you want me to retry the GPT Image 2 polish pass with external network access?",
        )
    )

    assert prompt == "Would you like to run the following"


def test_detect_authorization_prompt_from_partial_codex_run_command_ui() -> None:
    prompt = tbm.detect_authorization_prompt(
        _snapshot(
            "Reason: Do you want me to run the GPT Image 2 polish pass on the current reviewed figure using external network access?",
            "$ python3 /Users/sxi/.codex/skills/spotpaper/scripts/image2_edit.py -i input.png -o output.png",
            "› 1. Yes, proceed (y)",
            "2. Yes, and don't ask again for commands that start with `python3 /Users/sxi/.codex/skills/spotpaper/scripts/image2_edit.py` (p)",
            "3. No, and tell Codex what to do differently (esc)",
        )
    )

    assert prompt == "Would you like to run the following command?"


def test_detect_authorization_prompt_does_not_trigger_on_normal_reply_text() -> None:
    prompt = tbm.detect_authorization_prompt(
        _snapshot(
            "现在还能删的，主要就剩两类。",
            "如果你要，我可以先删第 1 类；按你的要求，删之前我会再向你请求授权。",
        )
    )

    assert prompt == ""


def test_terminal_broadcast_manager_prints_authorization_alert_once_per_prompt(
    monkeypatch,
    capsys,
) -> None:
    target = TerminalTarget(window_id=1, tty="/dev/ttys999", initial_prompt="question")
    snapshots = [
        _snapshot(
            "│ Do you want to allow this action?",
            "│ Allow once",
            "│ Allow always",
            "│ Deny",
        ),
        _snapshot(
            "│ Do you want to allow this action?",
            "│ Allow once",
            "│ Allow always",
            "│ Deny",
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

    manager.poll()
    manager.poll()
    out = capsys.readouterr().out

    assert out.count("[authorization]") == 1
    assert "Do you want to allow this action?" in out


def test_terminal_broadcast_manager_prints_authorization_alert_when_session_bound(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    session_path = tmp_path / "session.jsonl"
    session_path.write_text(
        "\n".join([
            '{"timestamp":"2026-04-12T20:00:00.000Z","type":"session_meta","payload":{"id":"sid","cwd":"/tmp/project"}}',
            "",
        ]),
        encoding="utf-8",
    )
    target = TerminalTarget(
        window_id=1,
        tty="/dev/ttys999",
        initial_prompt="question",
        working_directory="/tmp/project",
        launched_at=1776020000.0,
        session_id="sid",
        session_path=str(session_path),
    )

    monkeypatch.setattr(tbm, "get_terminal_name", lambda _target: "Test Terminal")
    monkeypatch.setattr(
        tbm,
        "get_terminal_contents",
        lambda _target: _snapshot(
            "Would you like to run the following",
            "command?",
            "Reason: Do you want me to run the GPT Image 2 polish pass with external network access?",
            "› 1. Yes, proceed (y)",
            "2. Yes, and don't ask again for commands that start with `python3 /Users/sxi/.codex/skills/spotpaper/scripts/image2_edit.py` (p)",
            "3. No, and tell Codex what to do differently (esc)",
        ),
    )
    _disable_activity_chime(monkeypatch)
    _disable_front_tab_authorization_fallback(monkeypatch, front_target=target)

    manager = tbm.TerminalBroadcastManager(
        speak=False,
        print_speak_text=False,
        target=target,
        verbose=False,
    )

    event = manager.poll()
    out = capsys.readouterr().out

    assert event is None
    assert "[authorization]" in out
    assert "Would you like to run the following command?" in out
    assert "[user_input]" not in out


def test_terminal_broadcast_manager_uses_front_tab_authorization_fallback_when_bound_tab_misses(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    session_path = tmp_path / "session.jsonl"
    session_path.write_text(
        "\n".join([
            '{"timestamp":"2026-04-12T20:00:00.000Z","type":"session_meta","payload":{"id":"sid","cwd":"/tmp/project"}}',
            "",
        ]),
        encoding="utf-8",
    )
    bound_target = TerminalTarget(
        window_id=1,
        tty="/dev/ttys999",
        initial_prompt="question",
        working_directory="/tmp/project",
        launched_at=1776020000.0,
        session_id="sid",
        session_path=str(session_path),
    )
    front_target = TerminalTarget(window_id=2, tty="/dev/ttys222")

    monkeypatch.setattr(tbm, "get_terminal_name", lambda _target: "Test Terminal")
    monkeypatch.setattr(tbm, "get_front_terminal_target", lambda: front_target)
    monkeypatch.setattr(tbm, "load_terminal_binding", lambda target: target)
    _disable_activity_chime(monkeypatch)

    def fake_terminal_contents(target):
        if target.window_id == 1:
            return _snapshot("no approval ui here")
        return _snapshot(
            "Would you like to run the following command?",
            "Reason: Do you want me to stage the 4 updated spotpaper files in the writing submodule?",
            "$ git -C writing/StateCap_policy_dynamics add spotpaper_draft/PAPER_TAKEAWAYS.md",
            "› 1. Yes, proceed (y)",
            "2. Yes, and don't ask again for commands that start with `git -C writing/StateCap_policy_dynamics add` (p)",
            "3. No, and tell Codex what to do differently (esc)",
        )

    monkeypatch.setattr(tbm, "get_terminal_contents", fake_terminal_contents)

    manager = tbm.TerminalBroadcastManager(
        speak=False,
        print_speak_text=False,
        target=bound_target,
        verbose=False,
    )

    event = manager.poll()
    out = capsys.readouterr().out

    assert event is None
    assert "[authorization]" in out
    assert "[note] authorization source=front_tab_fallback" in out
    assert "Would you like to run the following command?" in out
