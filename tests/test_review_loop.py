from pathlib import Path

from realtime_asr.events import ReviewCandidate, ReviewInstruction
from realtime_asr.review.engine import PlaceholderReviewEngine, ReviewEngine, _coerce_version_id
from realtime_asr.review.models import ReviewTarget
from realtime_asr.runtime.session import ReviewSession
from realtime_asr.runtime.state_machine import SessionState
from realtime_asr.document.loader import load_document


class TrackingReviewEngine(ReviewEngine):
    def __init__(self) -> None:
        self.working_text_inputs: list[str] = []
        self.rewrite_base_map: dict[str, str] = {}
        self.answer_map: dict[str, str] = {}

    def summarize_document(self, document) -> str:
        return "Document type: test document."

    def interpret_request(
        self,
        *,
        target: ReviewTarget,
        request_text: str,
        working_text: str,
        proposed_text: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> ReviewInstruction:
        if request_text in self.answer_map:
            return ReviewInstruction(
                raw_text=request_text,
                intent=request_text,
                request_type="answer",
                rewrite_base=self.rewrite_base_map.get(request_text, "working"),
                answer_text=self.answer_map[request_text],
                constraints=[],
            )
        return ReviewInstruction(
            raw_text=request_text,
            intent=request_text,
            request_type="rewrite",
            rewrite_base=self.rewrite_base_map.get(request_text, "working"),
            constraints=[],
        )

    def generate_candidates(
        self,
        *,
        target: ReviewTarget,
        instruction: ReviewInstruction,
        working_text: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> list[ReviewCandidate]:
        self.working_text_inputs.append(working_text)
        version = f"{working_text} -> {instruction.raw_text}"
        return [ReviewCandidate(version_id=1, text=version, rationale="tracked")]


def test_request_enters_reviewing_and_awaiting_decision(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("This sentence is too long and awkward.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()

    cycle = session.start_review("Make this shorter.", PlaceholderReviewEngine())

    assert session.state is SessionState.AWAITING_DECISION
    assert cycle.target.target_type == "sentence"
    assert cycle.target.sentence_id == "p1s1"
    assert session.document_overview
    assert cycle.target.document_overview == session.document_overview
    assert len(cycle.candidates) == 1
    assert cycle.instruction.request_type == "rewrite"


def test_review_cycle_keeps_return_state(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("One sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()
    session.pause()

    cycle = session.start_review("Make it more formal.", PlaceholderReviewEngine())

    assert cycle.return_state is SessionState.PAUSED


def test_document_overview_is_cached_per_session(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("# Title\n\nAlpha sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    engine = PlaceholderReviewEngine()

    first = session.ensure_document_overview(engine)
    second = session.ensure_document_overview(engine)

    assert first == second
    assert "Document type:" in first


def test_review_cycle_reuses_history_for_follow_up_request(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Alpha sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()
    engine = PlaceholderReviewEngine()

    first = session.start_review("Make it shorter.", engine)
    second = session.start_review("Keep the meaning.", engine)

    assert first is second
    assert session.state is SessionState.AWAITING_DECISION
    assert session.active_review is not None
    assert session.active_review.round_index == 2
    assert any(item["role"] == "user" and item["content"] == "Make it shorter." for item in session.active_review.conversation_history)
    assert any(item["role"] == "user" and item["content"] == "Keep the meaning." for item in session.active_review.conversation_history)


def test_placeholder_review_candidate_rationale_is_present_and_concise(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Alpha sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()

    cycle = session.start_review("Make it shorter.", PlaceholderReviewEngine())

    assert len(cycle.candidates) == 1
    assert cycle.candidates[0].rationale
    assert "agree" not in cycle.candidates[0].rationale.lower()


def test_question_request_returns_answer_and_does_not_enter_decision_state(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("# Intro\n\nAlpha sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()

    cycle = session.start_review("我们现在在哪个section", PlaceholderReviewEngine())

    assert cycle.instruction.request_type == "answer"
    assert cycle.instruction.answer_text == "1 Intro"
    assert cycle.candidates == []
    assert session.state is SessionState.PAUSED
    assert session.active_review is cycle
    assert any(item["role"] == "assistant" and item["content"] == "1 Intro" for item in session.active_review.conversation_history)


def test_answer_and_rewrite_share_sentence_level_history(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("# Intro\n\nAlpha sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()
    engine = PlaceholderReviewEngine()

    first = session.start_review("我们现在在哪个section", engine)
    second = session.start_review("Make it shorter.", engine)

    assert first is second
    assert session.active_review is not None
    assert session.active_review.round_index == 2
    assert any(item["role"] == "user" and item["content"] == "我们现在在哪个section" for item in session.active_review.conversation_history)
    assert any(item["role"] == "assistant" and item["content"] == "1 Intro" for item in session.active_review.conversation_history)
    assert any(item["role"] == "user" and item["content"] == "Make it shorter." for item in session.active_review.conversation_history)
    assert session.state is SessionState.AWAITING_DECISION


def test_exit_review_clears_active_review_memory(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Alpha sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()

    session.start_review("Make it shorter.", PlaceholderReviewEngine())
    session.exit_review()

    assert session.active_review is None
    assert session.state is SessionState.READING


def test_accept_review_stores_pending_revision_and_pauses(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Alpha sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()

    cycle = session.start_review("Make it shorter.", PlaceholderReviewEngine())
    applied = session.accept_review()

    assert applied is not None
    assert applied.original_text == cycle.target.source_text
    assert session.pending_revision is None
    assert session.active_review is None
    assert session.state is SessionState.PAUSED
    assert session.current_sentence is not None
    assert session.current_sentence.text == cycle.candidates[0].text


def test_discard_review_returns_to_previous_state(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Alpha sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()
    session.pause()

    session.start_review("Make it shorter.", PlaceholderReviewEngine())
    session.discard_review()

    assert session.active_review is None
    assert session.state is SessionState.PAUSED


def test_coerce_version_id_accepts_prefixed_string_values() -> None:
    assert _coerce_version_id("v1", 2) == 1
    assert _coerce_version_id("candidate-2", 1) == 2
    assert _coerce_version_id("", 3) == 3


def test_follow_up_rewrite_uses_previous_revision_as_working_text(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Alpha sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()
    engine = TrackingReviewEngine()
    engine.rewrite_base_map["make it more formal"] = "proposed"

    first = session.start_review("make it shorter", engine)
    session.start_review("make it more formal", engine)

    assert first.working_text == "Alpha sentence. -> make it shorter"
    assert first.proposed_text == "Alpha sentence. -> make it shorter -> make it more formal"
    assert engine.working_text_inputs[0] == "Alpha sentence."
    assert engine.working_text_inputs[1] == "Alpha sentence. -> make it shorter"


def test_follow_up_rewrite_can_reset_to_original_working_text(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Alpha sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()
    engine = TrackingReviewEngine()
    engine.rewrite_base_map["start over from the original"] = "original"

    session.start_review("make it shorter", engine)
    second = session.start_review("start over from the original", engine)

    assert engine.working_text_inputs[0] == "Alpha sentence."
    assert engine.working_text_inputs[1] == "Alpha sentence."
    assert second.working_text == "Alpha sentence."
    assert second.proposed_text == "Alpha sentence. -> start over from the original"


def test_answer_can_update_working_base_for_later_rewrites(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Alpha sentence.", encoding="utf-8")
    document = load_document(path)
    session = ReviewSession.start(document=document)
    session.begin_reading()
    engine = TrackingReviewEngine()
    engine.answer_map["where are we now"] = "Section 1"
    engine.rewrite_base_map["where are we now"] = "proposed"
    engine.rewrite_base_map["make it more formal"] = "working"

    session.start_review("make it shorter", engine)
    answer_cycle = session.start_review("where are we now", engine)
    session.start_review("make it more formal", engine)

    assert answer_cycle.working_text == "Alpha sentence. -> make it shorter"
    assert engine.working_text_inputs[0] == "Alpha sentence."
    assert engine.working_text_inputs[1] == "Alpha sentence. -> make it shorter"
