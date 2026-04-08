from __future__ import annotations

from dataclasses import dataclass

from realtime_asr.document.markdown import split_sentences
from realtime_asr.document.models import Paragraph, Sentence
from realtime_asr.patching.planner import TextPatch


def apply_patch_to_text(text: str, patch: TextPatch) -> str:
    if patch.operation != "replace":
        raise ValueError(f"Unsupported patch operation: {patch.operation}")
    if patch.original not in text:
        raise ValueError("Patch target was not found in source text.")
    return text.replace(patch.original, patch.replacement, 1)


@dataclass(slots=True)
class ParagraphApplyResult:
    paragraph_id: str
    sentence_id: str | None
    original_text: str
    updated_text: str
    paragraph_original_text: str
    paragraph_updated_text: str


def apply_sentence_replacement(
    paragraph: Paragraph,
    *,
    sentence_id: str,
    replacement: str,
) -> ParagraphApplyResult:
    paragraph_original_text = paragraph.text
    sentence_index = next((idx for idx, sentence in enumerate(paragraph.sentences) if sentence.id == sentence_id), None)
    if sentence_index is None:
        raise ValueError(f"Sentence id {sentence_id} was not found in paragraph {paragraph.id}.")

    original_text = paragraph.sentences[sentence_index].text
    sentence_texts = [sentence.text for sentence in paragraph.sentences]
    sentence_texts[sentence_index] = replacement.strip()
    updated_paragraph_text = " ".join(text for text in sentence_texts if text.strip())

    rebuilt_sentences = [
        Sentence(
            id=f"{paragraph.id}s{index}",
            index=index,
            text=text,
        )
        for index, text in enumerate(split_sentences(updated_paragraph_text), start=1)
    ]

    paragraph.text = updated_paragraph_text
    paragraph.sentences = rebuilt_sentences

    relocated_sentence_id: str | None = None
    if rebuilt_sentences:
        relocated_index = min(sentence_index + 1, len(rebuilt_sentences))
        relocated_sentence_id = rebuilt_sentences[relocated_index - 1].id

    return ParagraphApplyResult(
        paragraph_id=paragraph.id,
        sentence_id=relocated_sentence_id,
        original_text=original_text,
        updated_text=updated_paragraph_text,
        paragraph_original_text=paragraph_original_text,
        paragraph_updated_text=updated_paragraph_text,
    )
