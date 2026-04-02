# Editing Identity Strategy

## Purpose

This document defines how the voice review CLI should track document structure across edits.

The central rule is:

- `index` is for display and traversal
- `id` is for object identity inside the current document model
- reading progress should be tracked with anchors, not raw indexes

## Why This Matters

During review, users may:

- rewrite the current sentence
- rewrite the current paragraph
- delete a paragraph
- reorder sentences within a paragraph

If the runtime stores only `paragraph_index` or `sentence_index`, then any structural edit can invalidate the current reading position.

## Model Rules

### Paragraphs

- `Paragraph.id` is the paragraph identity in the current document graph
- `Paragraph.index` is the current visible order
- paragraph IDs should be preserved across local paragraph edits whenever possible

### Sentences

- `Sentence.id` is the sentence identity inside the current paragraph
- `Sentence.index` is the current visible order inside that paragraph
- sentence IDs may be rebuilt when a paragraph is fully rewritten

## Anchor Rules

The runtime should track reading state through an anchor object.

Minimum anchor fields:

- `paragraph_id`
- `sentence_id | None`
- `fallback_direction`
- `last_known_paragraph_index`
- `last_known_sentence_index | None`

Anchor lookup order after an edit:

1. Try to resolve `sentence_id` inside the current paragraph.
2. If sentence is gone, resolve `paragraph_id`.
3. If paragraph is gone, move to the nearest readable paragraph using `fallback_direction`.
4. If neither neighbor exists, mark the session as completed.

## Patch Rules

### Replace Current Sentence

- keep `Paragraph.id`
- update paragraph text
- rebuild sentence list for that paragraph
- attempt to preserve sentence identity only when the change is small and local

### Replace Current Paragraph

- keep `Paragraph.id`
- replace paragraph text
- rebuild all sentences in that paragraph

### Delete Current Paragraph

- remove the paragraph node
- keep all other paragraph IDs unchanged
- recompute paragraph indexes
- relocate the anchor to the next readable paragraph, or previous readable paragraph if no next one exists

### Reorder Sentences

- keep `Paragraph.id`
- preserve sentence IDs where possible
- recompute sentence indexes

## Practical Implementation Guidance

The system should avoid full-document reparsing for every local edit.

Preferred flow:

1. Load the document once into a document graph.
2. Apply local edits to targeted nodes.
3. Recompute indexes after edits.
4. Remap the reading anchor.

Full-document reload should be a fallback only when local repair is unsafe or unsupported.

## Current Phase Implication

Phase 1 does not yet implement local patch application, but the architecture should already assume:

- indexes are mutable
- IDs are not equivalent to indexes
- runtime state should be anchor-based
