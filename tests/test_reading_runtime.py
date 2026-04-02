from pathlib import Path

from realtime_asr.document.loader import load_document
from realtime_asr.runtime.session import ReviewSession
from realtime_asr.runtime.state_machine import SessionState


def test_reading_runtime_advances_sentence_then_paragraph(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("One. Two.\n\nThree.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)

    first = session.begin_reading()
    assert session.state is SessionState.READING
    assert first is not None
    assert first.id == "p1s1"

    second = session.advance()
    assert second is not None
    assert second.id == "p1s2"
    assert session.anchor.paragraph_id == "p1"

    third = session.advance()
    assert third is not None
    assert third.id == "p2s1"
    assert session.anchor.paragraph_id == "p2"


def test_reading_runtime_pause_resume_and_repeat(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("One. Two.\n\nThree.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)

    session.begin_reading()
    session.advance()
    session.pause()
    assert session.state is SessionState.PAUSED

    resumed = session.resume()
    assert session.state is SessionState.READING
    assert resumed is not None
    assert resumed.id == "p1s2"

    previous = session.repeat_previous()
    assert previous is not None
    assert previous.id == "p1s1"


def test_reading_runtime_replays_current_sentence_without_moving(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("One. Two.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)

    session.begin_reading()
    session.advance()

    current_before = session.current_sentence
    replayed = session.replay_current()

    assert replayed is not None
    assert current_before is not None
    assert replayed.id == current_before.id
    assert session.anchor.sentence_id == current_before.id


def test_reading_runtime_restarts_current_paragraph(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("One. Two.\n\nThree.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)

    session.begin_reading()
    session.advance()

    anchor_before = session.anchor.sentence_id
    replayed = session.replay_paragraph()

    assert [sentence.id for sentence in replayed] == ["p1s1", "p1s2"]
    assert session.anchor.sentence_id == anchor_before


def test_reading_runtime_completes_at_end(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("One.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)

    session.begin_reading()
    final = session.advance()

    assert final is None
    assert session.state is SessionState.COMPLETED


def test_reading_runtime_does_not_advance_while_paused(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("One. Two.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)

    session.begin_reading()
    session.pause()
    current = session.current_sentence
    advanced = session.advance()

    assert session.state is SessionState.PAUSED
    assert advanced == current


def test_reading_runtime_can_jump_to_preferred_paragraph(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("One.\n\nTwo.\n\nThree.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)

    sentence = session.jump_to_paragraph(3)

    assert sentence is not None
    assert sentence.id == "p3s1"
    assert session.anchor.paragraph_id == "p3"
    assert session.state is SessionState.READING


def test_reading_runtime_can_jump_to_text_match(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Alpha paragraph.\n\nBeta paragraph.\n\nGamma paragraph.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)

    sentence = session.jump_to_match("gamma")

    assert sentence is not None
    assert sentence.id == "p3s1"
    assert session.anchor.paragraph_id == "p3"


def test_reading_runtime_announces_abstract_and_headings_once(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text(
        "**Abstract**\n\nAbstract paragraph.\n\n# Introduction\n\nIntro first. Intro second.\n\n## Background\n\nBackground paragraph.",
        encoding="utf-8",
    )
    document = load_document(path)

    session = ReviewSession.start(document=document)
    session.begin_reading()

    assert session.consume_announcements() == ["Abstract"]
    assert session.consume_announcements() == []

    session.jump_to_paragraph(2)
    assert session.consume_announcements() == ["1 Introduction"]

    session.jump_to_paragraph(3)
    assert session.consume_announcements() == ["1.1 Background"]


def test_reading_runtime_section_navigation(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text(
        "# One\n\nOne intro.\n\n## One-One\n\nOne one body.\n\n### One-One-A\n\nOne one a body.\n\n## One-Two\n\nOne two body.\n\n# Two\n\nTwo intro.",
        encoding="utf-8",
    )
    document = load_document(path)
    session = ReviewSession.start(document=document)

    session.jump_to_match("One one a body")
    assert session.current_paragraph.id == "p6"

    next_subsection = session.next_subsection()
    assert next_subsection is not None
    assert next_subsection.id == "p8s1"

    previous_subsection = session.previous_subsection()
    assert previous_subsection is not None
    assert previous_subsection.id == "p6s1"

    next_section = session.next_section()
    assert next_section is not None
    assert next_section.id == "p10s1"

    previous_section = session.previous_section()
    assert previous_section is not None
    assert previous_section.id == "p2s1"


def test_reading_runtime_paragraph_navigation(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("# One\n\nAlpha.\n\nBeta.\n\nGamma.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)

    next_paragraph = session.next_paragraph()
    assert next_paragraph is not None
    assert next_paragraph.id == "p3s1"

    previous_paragraph = session.previous_paragraph()
    assert previous_paragraph is not None
    assert previous_paragraph.id == "p2s1"
