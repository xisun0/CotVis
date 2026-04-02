from pathlib import Path

from realtime_asr.document.loader import load_document
from realtime_asr.runtime.session import ReviewSession
from realtime_asr.runtime.state_machine import SessionState


def test_review_session_starts_at_requested_paragraph(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("One.\n\nTwo.", encoding="utf-8")
    document = load_document(path)

    session = ReviewSession.start(document=document, start_paragraph=2)

    assert session.state is SessionState.LOCATING_START
    assert session.anchor.paragraph_id == "p2"
    assert session.anchor.sentence_id == "p2s1"
    assert session.anchor.last_known_paragraph_index == 2
    assert session.current_paragraph.index == 2
