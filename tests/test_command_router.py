from realtime_asr.voice.commands import classify_utterance, normalize_command, normalize_review_decision


def test_normalize_command_supports_english_aliases() -> None:
    assert normalize_command("pause").name == "pause"
    assert normalize_command("Next.").name == "next"
    assert normalize_command("continue").name == "resume"
    assert normalize_command("next section").name == "next section"


def test_normalize_command_supports_chinese_aliases() -> None:
    assert normalize_command("暂停").name == "pause"
    assert normalize_command("暂停一下").name == "pause"
    assert normalize_command("继续").name == "resume"
    assert normalize_command("继续读").name == "resume"
    assert normalize_command("下一句").name == "next"
    assert normalize_command("下一句。").name == "next"
    assert normalize_command("读下一句").name == "next"
    assert normalize_command("上一节").name == "previous section"
    assert normalize_command("重复").name == "again"
    assert normalize_command("重复上一句").name == "previous"
    assert normalize_command("读这段").name == "paragraph"
    assert normalize_command("读下这段").name == "paragraph"
    assert normalize_command("读一下这段").name == "paragraph"
    assert normalize_command("读下这个段落").name == "paragraph"
    assert normalize_command("读一下这个段落").name == "paragraph"


def test_normalize_command_extracts_jump_paragraph_arguments() -> None:
    cmd = normalize_command("jump paragraph 3")
    assert cmd is not None
    assert cmd.name == "jump paragraph"
    assert cmd.argument == "3"

    cmd_cn = normalize_command("跳到第 5 段")
    assert cmd_cn is not None
    assert cmd_cn.name == "jump paragraph"
    assert cmd_cn.argument == "5"


def test_normalize_command_extracts_jump_match_arguments() -> None:
    cmd = normalize_command("jump match Introduction")
    assert cmd is not None
    assert cmd.name == "jump match"
    assert cmd.argument == "Introduction"

    cmd_cn = normalize_command("跳到 数据与方法")
    assert cmd_cn is not None
    assert cmd_cn.name == "jump match"
    assert cmd_cn.argument == "数据与方法"


def test_normalize_command_defaults_blank_to_next() -> None:
    cmd = normalize_command("   ")
    assert cmd is not None
    assert cmd.name == "next"


def test_normalize_command_returns_none_for_unknown_command() -> None:
    assert normalize_command("abracadabra") is None


def test_classify_utterance_treats_non_command_text_as_request() -> None:
    classified_cn = classify_utterance("这一句太绕了")
    classified_en = classify_utterance("make this sentence shorter")
    classified_cn_question = classify_utterance("看一下这一句是不是太短了")
    classified_neutral = classify_utterance("我想处理这里")

    assert classified_cn.kind == "request"
    assert classified_en.kind == "request"
    assert classified_cn_question.kind == "request"
    assert classified_neutral.kind == "request"


def test_classify_utterance_marks_controls_separately() -> None:
    classified = classify_utterance("下一句")

    assert classified.kind == "control"
    assert classified.command is not None
    assert classified.command.name == "next"


def test_classify_utterance_marks_unknown_when_no_rule_matches() -> None:
    classified = classify_utterance("   ")

    assert classified.kind == "unknown"


def test_normalize_review_decision_supports_accept_and_discard_aliases() -> None:
    assert normalize_review_decision("用这个").name == "accept"
    assert normalize_review_decision("就这样").name == "accept"
    assert normalize_review_decision("放弃").name == "discard"
    assert normalize_review_decision("算了").name == "discard"
