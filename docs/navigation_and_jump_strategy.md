# Navigation and Jump Strategy

## Purpose

This document explains how reading navigation works in the voice review CLI and how jump commands should behave.

The main concern is consistency:

- the system should read from a stable anchor
- the runtime should distinguish preferred narrative paragraphs from merely readable blocks
- jump behavior should be predictable and explainable

## Reading Priorities

Paragraphs are classified into three reading priorities:

- `primary`
- `secondary`
- `skip`

### Primary

Primary paragraphs are the main narrative flow.

Examples:

- ordinary body paragraphs
- abstract paragraphs
- most substantive prose paragraphs

Primary paragraphs are:

- eligible as the default starting point
- included in the main reading flow
- preferred for `jump paragraph N`

### Secondary

Secondary paragraphs are readable but not ideal default entry points.

Examples:

- list items
- blockquotes
- contact-information-like front matter
- metadata-like prose blocks that still contain readable text

Secondary paragraphs are:

- readable
- reachable during reading
- not preferred for default startup positioning

### Skip

Skip blocks are excluded from the reading flow.

Examples:

- headings
- code fences
- separators
- HTML wrappers
- obvious layout artifacts

## Start Position Rules

### Default Start

Default startup chooses:

1. the first `primary` paragraph
2. if no `primary` paragraph exists, the first readable paragraph

### `--start-paragraph`

The CLI interprets `--start-paragraph N` against preferred reading paragraphs:

- first against `primary` paragraphs
- if no `primary` paragraphs exist, against readable paragraphs

### `--match`

The CLI currently scans readable paragraphs in document order and selects the first paragraph whose text contains the provided match string.

This is intentionally simple for the current phase.

## Interactive Jump Rules

### `jump paragraph N`

The interactive demo uses the same preferred-paragraph rule as startup:

- jump to the `N`th preferred paragraph
- update the anchor to that paragraph's first sentence
- set the runtime state to `reading`

### `jump match TEXT`

The interactive demo currently uses first-match behavior:

1. scan readable paragraphs in document order
2. select the first paragraph whose text contains the search text
3. jump to that paragraph's first sentence
4. set the runtime state to `reading`

This means that if multiple readable paragraphs match, the runtime does not yet present choices.

## Current Limitation

The current `jump match` implementation does not disambiguate multiple candidates.

Planned upgrade path:

1. if there is exactly one match, jump immediately
2. if there are multiple matches, print candidate paragraphs
3. require a follow-up `choose N` command

## Anchor Update Rules

After any jump:

- `anchor.paragraph_id` becomes the destination paragraph
- `anchor.sentence_id` becomes that paragraph's first sentence
- `last_known_paragraph_index` and `last_known_sentence_index` are refreshed
- session state becomes `reading` unless the session is already completed

## Why This Strategy

This approach keeps the early product predictable:

- default startup lands in narrative prose
- list items and quotes remain readable without hijacking startup
- jump behavior is simple enough to test in the terminal
- anchor updates remain explicit and debuggable

## Interactive Reading Control Semantics

Current terminal reading controls are intentionally explicit:

- `next` moves forward one sentence
- `previous` moves back one sentence and rereads it
- `again` rereads the current sentence without moving the anchor
- `paragraph` rereads the current paragraph from its first sentence without moving the anchor
- `next paragraph` jumps to the next readable paragraph
- `previous paragraph` jumps to the previous readable paragraph
- `next subsection` jumps out of the current finest subsection to the next readable paragraph beyond it
- `previous subsection` jumps to the first readable paragraph of the previous finest subsection
- `next section` jumps to the next top-level section's readable content
- `previous section` jumps to the first readable paragraph of the previous top-level section
- `pause` and `resume` control reading state
