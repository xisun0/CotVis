from __future__ import annotations

import json
import os
import re

from openai import OpenAI

from realtime_asr.document.models import Document
from realtime_asr.events import ReviewCandidate, ReviewInstruction
from realtime_asr.review.models import ReviewTarget


class ReviewEngine:
    def summarize_document(self, document: Document) -> str:
        raise NotImplementedError

    def interpret_request(
        self,
        *,
        target: ReviewTarget,
        request_text: str,
        working_text: str,
        proposed_text: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> ReviewInstruction:
        raise NotImplementedError

    def generate_candidates(
        self,
        *,
        target: ReviewTarget,
        instruction: ReviewInstruction,
        working_text: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> list[ReviewCandidate]:
        raise NotImplementedError


class PlaceholderReviewEngine(ReviewEngine):
    def summarize_document(self, document: Document) -> str:
        return build_fallback_document_overview(document)

    def interpret_request(
        self,
        *,
        target: ReviewTarget,
        request_text: str,
        working_text: str,
        proposed_text: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> ReviewInstruction:
        text = request_text.strip()
        if "section" in text.lower() or "章节" in text or "小节" in text or "section" in text.lower():
            answer = target.section_label or "No section label is available for the current sentence."
            return ReviewInstruction(
                raw_text=request_text,
                intent="Answer the user's question about the current section.",
                request_type="answer",
                rewrite_base="working",
                answer_text=answer,
                constraints=[],
            )
        return ReviewInstruction(raw_text=request_text, intent=text, request_type="rewrite", rewrite_base="working", constraints=[])

    def generate_candidates(
        self,
        *,
        target: ReviewTarget,
        instruction: ReviewInstruction,
        working_text: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> list[ReviewCandidate]:
        source = (working_text or target.source_text).strip()
        compact = " ".join(source.split())
        return [
            ReviewCandidate(
                version_id=1,
                text=compact,
                rationale="I kept the response minimal and only adjusted the local wording requested by the user.",
            ),
        ]


class OpenAIReviewEngine(ReviewEngine):
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.model = model
        self.client = OpenAI(api_key=api_key)

    def summarize_document(self, document: Document) -> str:
        system_prompt = (
            "You summarize a prose document for a sentence-level revision assistant. "
            "Read the full document and produce a compact overview that helps future local edits stay aligned with the big picture. "
            "Return plain text with these labeled lines only: "
            "Document type, Central idea, Writing style, Structural outline, Editing principle. "
            "The editing principle should emphasize minimal local edits unless the user explicitly asks for larger changes."
        )
        user_prompt = _full_document_prompt(document)
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = completion.choices[0].message.content or ""
        summary = content.strip()
        return summary or build_fallback_document_overview(document)

    def interpret_request(
        self,
        *,
        target: ReviewTarget,
        request_text: str,
        working_text: str,
        proposed_text: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> ReviewInstruction:
        system_prompt = (
            "You are interpreting a spoken request during a manuscript review session. "
            "Decide whether the user is asking for a sentence rewrite or asking a direct question about the current location/content. "
            "The editable target is always the current sentence for this phase. "
            "You are given a document overview so you understand the manuscript's big picture, genre, and structure. "
            "Assume the document is coherent and the user usually wants a local revision that still fits the larger argument. "
            "Prefer minimal-edit interpretations unless the request clearly asks for a bigger rewrite. "
            "Return strict JSON with keys: request_type, intent, rewrite_base, constraints, answer_text. "
            "request_type must be either 'rewrite' or 'answer'. "
            "rewrite_base must be either 'proposed', 'working', or 'original'. "
            "intent should be one short sentence. "
            "constraints should be a short array of strings. "
            "If request_type is 'answer', answer_text must contain a short direct answer grounded in the current section and target context, and constraints should be empty. "
            "If request_type is 'answer', set rewrite_base to 'working'. "
            "If request_type is 'rewrite', answer_text must be an empty string. "
            "Use rewrite_base='proposed' when the new request should continue from the most recent proposed revision. "
            "Use rewrite_base='working' when the new request should continue from the stable working revision already established in the current review cycle. "
            "Use rewrite_base='original' when the user is effectively abandoning the current revision and wants to restart from the original sentence. "
            "Do not include markdown."
        )
        user_prompt = (
            f"Document overview:\n{target.document_overview}\n\n"
            f"Review conversation so far:\n{_format_conversation_history(conversation_history)}\n\n"
            f"Current section label:\n{target.section_label or 'unknown'}\n\n"
            f"Target text:\n{target.source_text}\n\n"
            f"Current working revision:\n{working_text}\n\n"
            f"Most recent proposed revision:\n{proposed_text or 'none'}\n\n"
            f"User request:\n{request_text}\n"
        )
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content or "{}"
        payload = json.loads(content)
        request_type = str(payload.get("request_type", "rewrite")).strip().lower() or "rewrite"
        if request_type not in {"rewrite", "answer"}:
            request_type = "rewrite"
        rewrite_base = str(payload.get("rewrite_base", "working")).strip().lower() or "working"
        if rewrite_base not in {"proposed", "working", "original"}:
            rewrite_base = "working"
        intent = str(payload.get("intent", request_text)).strip() or request_text.strip()
        answer_text = str(payload.get("answer_text", "")).strip()
        constraints = [
            str(item).strip()
            for item in payload.get("constraints", [])
            if str(item).strip()
        ]
        if request_type == "answer":
            constraints = []
        return ReviewInstruction(
            raw_text=request_text,
            intent=intent,
            request_type=request_type,
            rewrite_base=rewrite_base,
            answer_text=answer_text,
            constraints=constraints,
        )

    def generate_candidates(
        self,
        *,
        target: ReviewTarget,
        instruction: ReviewInstruction,
        working_text: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> list[ReviewCandidate]:
        constraints_text = "\n".join(f"- {item}" for item in instruction.constraints) or "- none"
        system_prompt = (
            "You rewrite one sentence from an academic manuscript. "
            "You are given a document overview so you preserve the sentence's role in the larger argument, tone, and structure. "
            "Return strict JSON with key 'candidate'. "
            "The candidate object must include: version_id, text, rationale. "
            "Keep the meaning unless the request explicitly asks to change it. "
            "Prefer minimal edits: keep the original structure, wording, and claims whenever possible, and only change what is necessary to satisfy the request. "
            "The rationale must be very short. It should briefly say how you responded to the request and what you changed. "
            "Do not automatically say you agree with the request. If the requested change is only partly appropriate, say that briefly and explain the local adjustment you made. "
            "Use one concise sentence only. "
            "Do not use markdown."
        )
        user_prompt = (
            f"Document overview:\n{target.document_overview}\n\n"
            f"Review conversation so far:\n{_format_conversation_history(conversation_history)}\n\n"
            f"Original sentence:\n{target.source_text}\n\n"
            f"Current working revision:\n{working_text}\n\n"
            f"Rewrite goal:\n{instruction.intent}\n\n"
            f"Constraints:\n{constraints_text}\n"
        )
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content or "{}"
        payload = json.loads(content)
        raw_candidate = payload.get("candidate", {})
        candidates: list[ReviewCandidate] = []
        if isinstance(raw_candidate, dict):
            text = str(raw_candidate.get("text", "")).strip()
            rationale = str(raw_candidate.get("rationale", "")).strip()
            if text:
                candidates.append(
                    ReviewCandidate(
                        version_id=_coerce_version_id(raw_candidate.get("version_id"), 1),
                        text=text,
                        rationale=rationale or "I made a minimal local revision in response to the request.",
                    )
                )
        if len(candidates) < 1:
            fallback = PlaceholderReviewEngine().generate_candidates(
                target=target,
                instruction=instruction,
                working_text=working_text,
                conversation_history=conversation_history,
            )
            for candidate in fallback:
                if len(candidates) >= 1:
                    break
                candidates.append(candidate)
        return candidates[:1]


def build_review_engine() -> ReviewEngine:
    if os.environ.get("OPENAI_API_KEY"):
        try:
            return OpenAIReviewEngine()
        except Exception:
            return PlaceholderReviewEngine()
    return PlaceholderReviewEngine()


def build_fallback_document_overview(document: Document) -> str:
    title = next(
        (paragraph.heading_text for paragraph in document.paragraphs if paragraph.kind == "heading" and paragraph.heading_text),
        None,
    )
    abstract = next(
        (
            paragraph.text.strip()
            for paragraph in document.primary_paragraphs
            if paragraph.section_marker_label == "Abstract" and paragraph.text.strip()
        ),
        None,
    )
    section_labels: list[str] = []
    for paragraph in document.paragraphs:
        label = paragraph.section_marker_label
        if not label:
            continue
        if label in section_labels:
            continue
        if label == "Abstract" or paragraph.kind == "heading":
            section_labels.append(label)
    section_summary = ", ".join(section_labels[:6]) if section_labels else "none"

    parts = [
        "Document type: sectioned prose document in Markdown.",
        f"Document title: {title or 'unknown'}.",
        f"Structural outline: {section_summary}.",
    ]
    if abstract:
        compact_abstract = " ".join(abstract.split())
        parts.append(f"Central idea: {compact_abstract}")
        parts.append("Writing style: formal expository prose with sectioned argumentation.")
    parts.append(
        "Editing principle: prefer minimal local edits that preserve the sentence's role, meaning, and tone unless the user explicitly asks for a larger rewrite."
    )
    return "\n".join(parts)


def _full_document_prompt(document: Document) -> str:
    chunks: list[str] = []
    for paragraph in document.paragraphs:
        if paragraph.kind == "heading" and paragraph.heading_text:
            chunks.append(f"# {paragraph.heading_text}")
            continue
        text = paragraph.text.strip()
        if not text:
            continue
        chunks.append(text)
    return "\n\n".join(chunks)


def _format_conversation_history(conversation_history: list[dict[str, str]] | None) -> str:
    if not conversation_history:
        return "none"
    lines: list[str] = []
    for item in conversation_history:
        role = item.get("role", "unknown")
        content = item.get("content", "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines) or "none"


def _coerce_version_id(value: object, fallback: int) -> int:
    if value is None:
        return fallback
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return fallback
    try:
        return int(text)
    except ValueError:
        match = re.search(r"\d+", text)
        if match:
            return int(match.group(0))
    return fallback
