# Voice Review CLI

## Overview

This repository is being rebuilt as a voice-first manuscript review CLI.

The target workflow is:

1. Open a document review session from the terminal.
2. Let the system read a manuscript aloud from the beginning or a chosen starting point.
3. Interrupt by voice when a sentence or paragraph needs revision.
4. Review candidate rewrites.
5. Apply a local patch and continue reading.

The current codebase is in early rebuild status.

- Phase 0 is complete: old ASR/visualization code has been removed and a new package skeleton is in place.
- Phase 1 is complete: Markdown parsing, paragraph classification, stable IDs, reading anchors, and a structured dry-run preview are working.
- Phase 2 is complete: sentence-level reading runtime, terminal interaction, section announcements, navigation commands, and TTS demo backends are working.
- ASR command capture and the live review loop are not implemented yet.

## Current Scope

### Implemented

- Markdown and plain-text document loading
- Paragraph segmentation
- Conservative sentence segmentation
- Paragraph classification
- Reading priority model:
  - `primary`
  - `secondary`
  - `skip`
- Stable paragraph and sentence IDs inside the current document graph
- Anchor-oriented session bootstrap
- Structured dry-run preview for validation
- Sentence-by-sentence reading demo
- Interactive terminal demo for reading controls
- Section and abstract announcements before reading new parts
- Paragraph / subsection / section navigation in the interactive demo
- Demo TTS backends:
  - `none`
  - `console`
  - `system`

### Not Yet Implemented

- Voice interruption
- Rewrite generation with real model calls
- Patch application to the document graph
- Resume-after-edit behavior

## Requirements

- Python 3.11+
- `pytest` for local validation
- `pandoc` only if you want to generate Markdown test material from LaTeX yourself

## Setup

```bash
make setup
```

Optional beginner-friendly git setup:

```bash
make setup-local
```

## Main Demo

The current Phase 1 demo is the structured dry-run preview.

Run the real sample:

```bash
make run ARGS="review examples/research_article_sample.md --dry-run"
```

This prints:

- document summary
- paragraph counts
- reading-priority counts
- chosen starting point
- current anchor state
- current paragraph preview
- neighboring skipped/readable blocks

Example alternate entrypoints:

```bash
make run ARGS="review examples/research_article_sample.md --dry-run --match 'Industrial policy—targeted government interventions'"
make run ARGS="review examples/research_article_sample.md --dry-run --start-paragraph 3"
```

## Reading Demo

Phase 2 adds a sentence-by-sentence reading runtime demo.

Run a non-speaking version:

```bash
make run ARGS="review examples/research_article_sample.md --read-demo --max-sentences 5 --tts none"
```

Run a simple terminal-controlled interactive version:

```bash
make run ARGS="review examples/research_article_sample.md --interactive-demo --tts none"
```

The reading demos now announce structural markers before prose when available, for example:

- `Abstract`
- `1 Introduction`
- `1.1 Background`

Supported interactive commands:

- `pause`
- `resume`
- `next`
- `previous`
- `again`
- `paragraph`
- `next paragraph`
- `previous paragraph`
- `next subsection`
- `previous subsection`
- `next section`
- `previous section`
- `status`
- `jump paragraph N`
- `jump match TEXT`
- `help`
- `quit`

Current jump behavior:

- `jump paragraph N` jumps to the `N`th preferred paragraph in the reading flow
- `jump match TEXT` currently jumps to the first readable paragraph that contains the given text
- multi-candidate disambiguation is not implemented yet
- `next/previous subsection` use the current finest section path rather than a hard-coded heading depth
- `next/previous section` use the top-level section path

Command semantics:

- `previous` moves back one sentence and rereads it
- `again` rereads the current sentence without moving the anchor
- `paragraph` rereads the full current paragraph from the beginning without moving the anchor
- `next paragraph` and `previous paragraph` jump between readable paragraphs
- `next subsection` and `previous subsection` move across the current finest subsection boundary
- `next section` and `previous section` move across top-level sections

## Testing

Run the current automated checks:

```bash
make test
```

Current tests cover:

- Markdown loading
- paragraph kind classification
- start-paragraph location
- anchor bootstrap
- reading progression
- pause/resume/repeat
- paragraph/subsection/section navigation
- section and abstract announcement behavior
- jump paragraph and jump match behavior
- patch-target skeleton behavior

## Key Sample

The main realistic test sample is:

- [examples/research_article_sample.md](/Users/sxi/SunXi/1-Research/14_CotVis/examples/research_article_sample.md)

This sample was converted from a LaTeX research draft and intentionally retains structural noise such as wrappers and front matter, which makes it useful for parser validation.

## Design Notes

Two planning documents are especially relevant:

- [docs/voice_review_cli_development_plan.md](/Users/sxi/SunXi/1-Research/14_CotVis/docs/voice_review_cli_development_plan.md)
- [docs/editing_identity_strategy.md](/Users/sxi/SunXi/1-Research/14_CotVis/docs/editing_identity_strategy.md)
- [docs/navigation_and_jump_strategy.md](/Users/sxi/SunXi/1-Research/14_CotVis/docs/navigation_and_jump_strategy.md)

The important architecture rule is:

- `index` is display order
- `id` is object identity inside the current document graph
- reading progress should be tracked by anchors, not raw indexes

## Current Package Layout

- `src/realtime_asr/cli.py` — CLI entrypoint, dry-run preview, reading demo, interactive demo
- `src/realtime_asr/document/` — document loading, parsing, locating, models
- `src/realtime_asr/runtime/` — session bootstrap, reading navigator, and state machine
- `src/realtime_asr/review/` — placeholder review interfaces
- `src/realtime_asr/patching/` — patch-target skeleton
- `src/realtime_asr/voice/` — demo TTS backends and future voice adapters
- `tests/` — Phase 1 and Phase 2 tests

## Next Step

The next implementation focus is the live review loop:

- ASR command capture
- spoken pause/resume/repeat/jump commands
- review-mode transitions
- rewrite candidate generation
- local patch application and resume-after-edit
