from __future__ import annotations

from dataclasses import dataclass, field

from realtime_asr.document.locator import locate_start_paragraph
from realtime_asr.document.models import Document, Paragraph, Sentence
from realtime_asr.events import ReviewCandidate, ReviewInstruction
from realtime_asr.review.engine import ReviewEngine
from realtime_asr.review.models import ReviewCycle, ReviewTarget
from realtime_asr.runtime.navigator import (
    deepest_marker_id,
    first_readable_paragraph_of_marker_group,
    first_sentence,
    next_readable_paragraph,
    next_readable_paragraph_in_next_top_section,
    next_readable_paragraph_outside_marker,
    next_sentence,
    previous_readable_paragraph,
    previous_sentence,
    top_marker_id,
)
from realtime_asr.runtime.state_machine import SessionState


@dataclass(slots=True)
class ReadingAnchor:
    paragraph_id: str
    sentence_id: str | None
    fallback_direction: str
    last_known_paragraph_index: int
    last_known_sentence_index: int | None


@dataclass(slots=True)
class ReviewSession:
    document: Document
    state: SessionState
    anchor: ReadingAnchor
    document_overview: str = ""
    sentence_history: list[str] = field(default_factory=list)
    last_announced_marker_id: str | None = None
    active_review: ReviewCycle | None = None
    pending_revision: ReviewCandidate | None = None

    @classmethod
    def start(
        cls,
        document: Document,
        start_paragraph: int = 1,
        match_text: str | None = None,
    ) -> "ReviewSession":
        paragraph = locate_start_paragraph(
            document=document,
            paragraph_index=start_paragraph,
            match_text=match_text,
        )
        return cls(
            document=document,
            state=SessionState.LOCATING_START,
            anchor=ReadingAnchor(
                paragraph_id=paragraph.id,
                sentence_id=paragraph.sentences[0].id if paragraph.sentences else None,
                fallback_direction="forward",
                last_known_paragraph_index=paragraph.index,
                last_known_sentence_index=paragraph.sentences[0].index if paragraph.sentences else None,
            ),
        )

    @property
    def current_paragraph(self) -> Paragraph:
        return self.document.get_paragraph_by_id(self.anchor.paragraph_id)

    @property
    def current_sentence(self) -> Sentence | None:
        if self.anchor.sentence_id is None:
            return None
        for sentence in self.current_paragraph.sentences:
            if sentence.id == self.anchor.sentence_id:
                return sentence
        return None

    def begin_reading(self) -> Sentence | None:
        if self.state not in {SessionState.LOCATING_START, SessionState.RESUMING, SessionState.PAUSED}:
            if self.state is SessionState.COMPLETED:
                return None
        sentence = self._resolve_current_sentence()
        if sentence is None:
            self.state = SessionState.COMPLETED
            return None
        self.state = SessionState.READING
        self._remember_sentence(sentence)
        return sentence

    def pause(self) -> None:
        if self.state is SessionState.READING:
            self.state = SessionState.PAUSED

    def resume(self) -> Sentence | None:
        if self.state is not SessionState.PAUSED:
            return self.current_sentence
        self.state = SessionState.RESUMING
        return self.begin_reading()

    def advance(self) -> Sentence | None:
        if self.state is not SessionState.READING:
            return self.current_sentence

        current_paragraph = self.current_paragraph
        next_in_paragraph = next_sentence(current_paragraph, self.anchor.sentence_id)
        if next_in_paragraph is not None:
            self._set_anchor(current_paragraph, next_in_paragraph)
            self._remember_sentence(next_in_paragraph)
            return next_in_paragraph

        next_paragraph = next_readable_paragraph(self.document, current_paragraph.index)
        if next_paragraph is None:
            self.state = SessionState.COMPLETED
            return None
        sentence = first_sentence(next_paragraph)
        if sentence is None:
            self.state = SessionState.COMPLETED
            return None
        self._set_anchor(next_paragraph, sentence)
        self._remember_sentence(sentence)
        return sentence

    def repeat_previous(self) -> Sentence | None:
        current_paragraph = self.current_paragraph
        previous_in_paragraph = previous_sentence(current_paragraph, self.anchor.sentence_id)
        if previous_in_paragraph is not None:
            self._set_anchor(current_paragraph, previous_in_paragraph)
            return previous_in_paragraph

        previous_paragraph = previous_readable_paragraph(self.document, current_paragraph.index)
        if previous_paragraph is None or not previous_paragraph.sentences:
            return self.current_sentence
        sentence = previous_paragraph.sentences[-1]
        self._set_anchor(previous_paragraph, sentence)
        return sentence

    def replay_current(self) -> Sentence | None:
        return self.current_sentence

    def current_paragraph_sentences(self) -> list[Sentence]:
        return list(self.current_paragraph.sentences)

    def replay_paragraph(self) -> list[Sentence]:
        paragraph = self.current_paragraph
        return list(paragraph.sentences)

    def jump_to_paragraph(self, paragraph_index: int) -> Sentence | None:
        paragraph = locate_start_paragraph(
            document=self.document,
            paragraph_index=paragraph_index,
            match_text=None,
        )
        sentence = first_sentence(paragraph)
        if sentence is None:
            return None
        self._set_anchor(paragraph, sentence)
        if self.state is not SessionState.COMPLETED:
            self.state = SessionState.READING
        return sentence

    def jump_to_match(self, match_text: str) -> Sentence | None:
        paragraph = locate_start_paragraph(
            document=self.document,
            paragraph_index=1,
            match_text=match_text,
        )
        sentence = first_sentence(paragraph)
        if sentence is None:
            return None
        self._set_anchor(paragraph, sentence)
        if self.state is not SessionState.COMPLETED:
            self.state = SessionState.READING
        return sentence

    def next_paragraph(self) -> Sentence | None:
        paragraph = next_readable_paragraph(self.document, self.current_paragraph.index)
        return self._jump_to_paragraph_object(paragraph)

    def previous_paragraph(self) -> Sentence | None:
        paragraph = previous_readable_paragraph(self.document, self.current_paragraph.index)
        return self._jump_to_paragraph_object(paragraph)

    def next_subsection(self) -> Sentence | None:
        marker_id = deepest_marker_id(self.current_paragraph)
        paragraph = next_readable_paragraph_outside_marker(
            self.document,
            self.current_paragraph.index,
            marker_id,
        )
        return self._jump_to_paragraph_object(paragraph)

    def previous_subsection(self) -> Sentence | None:
        current_marker_id = deepest_marker_id(self.current_paragraph)
        candidate = previous_readable_paragraph(self.document, self.current_paragraph.index)
        while candidate is not None and deepest_marker_id(candidate) == current_marker_id:
            candidate = previous_readable_paragraph(self.document, candidate.index)
        if candidate is None:
            return None
        target_marker_id = deepest_marker_id(candidate)
        paragraph = first_readable_paragraph_of_marker_group(
            self.document,
            candidate,
            target_marker_id,
            mode="subsection",
        )
        return self._jump_to_paragraph_object(paragraph)

    def next_section(self) -> Sentence | None:
        marker_id = top_marker_id(self.current_paragraph)
        paragraph = next_readable_paragraph_in_next_top_section(
            self.document,
            self.current_paragraph.index,
            marker_id,
        )
        return self._jump_to_paragraph_object(paragraph)

    def previous_section(self) -> Sentence | None:
        current_marker_id = top_marker_id(self.current_paragraph)
        candidate = previous_readable_paragraph(self.document, self.current_paragraph.index)
        while candidate is not None and top_marker_id(candidate) == current_marker_id:
            candidate = previous_readable_paragraph(self.document, candidate.index)
        if candidate is None:
            return None
        target_marker_id = top_marker_id(candidate)
        paragraph = first_readable_paragraph_of_marker_group(
            self.document,
            candidate,
            target_marker_id,
            mode="section",
        )
        return self._jump_to_paragraph_object(paragraph)

    def consume_announcements(self) -> list[str]:
        label = self.current_paragraph.section_marker_label
        marker_id = self.current_paragraph.section_marker_id
        if not label or not marker_id:
            return []
        if marker_id == self.last_announced_marker_id:
            return []
        self.last_announced_marker_id = marker_id
        return [label]

    def ensure_document_overview(self, engine: ReviewEngine) -> str:
        if not self.document_overview:
            self.document_overview = engine.summarize_document(self.document)
        return self.document_overview

    def start_review(self, request_text: str, engine: ReviewEngine) -> ReviewCycle:
        current_sentence = self.current_sentence or self._resolve_current_sentence()
        if current_sentence is None:
            raise ValueError("No current sentence available for review")

        existing_cycle = None
        if self.active_review is not None and self.active_review.target.sentence_id == current_sentence.id:
            existing_cycle = self.active_review

        if existing_cycle is None:
            target = ReviewTarget(
                target_type="sentence",
                paragraph_id=self.current_paragraph.id,
                sentence_id=current_sentence.id,
                source_text=current_sentence.text,
                section_label=self.current_paragraph.section_marker_label or "",
                document_overview=self.ensure_document_overview(engine),
            )
            cycle = ReviewCycle(
                target=target,
                request_text=request_text,
                instruction=ReviewInstruction(raw_text=request_text, intent="", request_type="rewrite", rewrite_base="working", constraints=[]),
                working_text=current_sentence.text,
                proposed_text="",
                return_state=self.state if self.state in {SessionState.READING, SessionState.PAUSED} else SessionState.READING,
                conversation_history=[{"role": "user", "content": request_text}],
            )
        else:
            cycle = existing_cycle
            cycle.request_text = request_text
            cycle.round_index += 1
            cycle.conversation_history.append({"role": "user", "content": request_text})

        self.state = SessionState.REVIEWING
        instruction = engine.interpret_request(
            target=cycle.target,
            request_text=request_text,
            working_text=cycle.working_text or cycle.target.source_text,
            proposed_text=cycle.proposed_text,
            conversation_history=cycle.conversation_history,
        )
        cycle.instruction = instruction
        if instruction.rewrite_base == "original":
            effective_base = cycle.target.source_text
        elif instruction.rewrite_base == "proposed" and cycle.proposed_text:
            effective_base = cycle.proposed_text
        else:
            effective_base = cycle.working_text or cycle.target.source_text
        cycle.working_text = effective_base
        if instruction.request_type == "answer":
            cycle.candidates = []
            cycle.conversation_history.append(
                {
                    "role": "assistant",
                    "content": instruction.answer_text or "No grounded answer available.",
                }
            )
            self.active_review = cycle
            self.state = SessionState.PAUSED
            return cycle
        candidates = engine.generate_candidates(
            target=cycle.target,
            instruction=instruction,
            working_text=effective_base,
            conversation_history=cycle.conversation_history,
        )
        cycle.candidates = candidates
        if candidates:
            cycle.proposed_text = candidates[0].text
        cycle.conversation_history.append(
            {
                "role": "assistant",
                "content": _summarize_candidates_for_history(candidates),
            }
        )
        self.active_review = cycle
        self.state = SessionState.AWAITING_DECISION
        return cycle

    def clear_review(self) -> None:
        self.active_review = None

    def accept_review(self) -> ReviewCandidate | None:
        if self.active_review is None or not self.active_review.candidates:
            return None
        accepted = self.active_review.candidates[0]
        self.pending_revision = accepted
        self.clear_review()
        self.state = SessionState.PAUSED
        return accepted

    def discard_review(self) -> None:
        return_state = self.active_review.return_state if self.active_review is not None else SessionState.READING
        self.clear_review()
        self.state = return_state

    def exit_review(self) -> None:
        return_state = self.active_review.return_state if self.active_review is not None else SessionState.READING
        self.clear_review()
        self.state = return_state

    def _resolve_current_sentence(self) -> Sentence | None:
        sentence = self.current_sentence
        if sentence is not None:
            return sentence
        paragraph = self.current_paragraph
        sentence = first_sentence(paragraph)
        if sentence is not None:
            self._set_anchor(paragraph, sentence)
            return sentence
        next_paragraph = next_readable_paragraph(self.document, paragraph.index)
        if next_paragraph is None or not next_paragraph.sentences:
            return None
        sentence = first_sentence(next_paragraph)
        if sentence is not None:
            self._set_anchor(next_paragraph, sentence)
        return sentence

    def _jump_to_paragraph_object(self, paragraph: Paragraph | None) -> Sentence | None:
        if paragraph is None:
            return None
        sentence = first_sentence(paragraph)
        if sentence is None:
            return None
        self._set_anchor(paragraph, sentence)
        if self.state is not SessionState.COMPLETED:
            self.state = SessionState.READING
        return sentence

    def _set_anchor(self, paragraph: Paragraph, sentence: Sentence | None) -> None:
        if (
            self.active_review is not None
            and sentence is not None
            and self.active_review.target.sentence_id != sentence.id
        ):
            self.clear_review()
        self.anchor.paragraph_id = paragraph.id
        self.anchor.last_known_paragraph_index = paragraph.index
        self.anchor.sentence_id = sentence.id if sentence is not None else None
        self.anchor.last_known_sentence_index = sentence.index if sentence is not None else None

    def _remember_sentence(self, sentence: Sentence) -> None:
        if not self.sentence_history or self.sentence_history[-1] != sentence.id:
            self.sentence_history.append(sentence.id)


def _summarize_candidates_for_history(candidates: list[ReviewCandidate]) -> str:
    if not candidates:
        return "No candidates generated."
    parts = [f"v{candidate.version_id}: {candidate.text}" for candidate in candidates]
    return " | ".join(parts)
