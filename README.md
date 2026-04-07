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
- Phase 3.3 is underway: bilingual command normalization, explicit-trigger voice demo, and pause-based microphone turn ending are in place as a bridge to real spoken control.
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
- Bilingual command normalization for interactive controls:
  - English aliases
  - Chinese aliases
- Explicit-trigger voice demo with a typed ASR backend
- Optional OpenAI microphone-backed ASR backend for `voice-demo`
- Pause-based turn ending for microphone command capture
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

Run the explicit-trigger voice demo skeleton:

```bash
make run ARGS="review examples/research_article_sample.md --voice-demo --tts none"
```

Run the same demo with the OpenAI microphone backend:

```bash
OPENAI_API_KEY=... make run ARGS="review examples/research_article_sample.md --voice-demo --tts none --asr openai --command-language zh --voice-listen-seconds 6 --voice-silence-seconds 0.8"
```

If you want to bias command recognition toward one language, add:

```bash
--command-language zh
```

or:

```bash
--command-language en
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

The interactive demo accepts English and Chinese aliases for the same control intent. Examples:

- `pause` / `暂停`
- `resume` / `继续`
- `next` / `下一句`
- `previous` / `上一句`
- `paragraph` / `本段`
- `next section` / `下一节`
- `status` / `状态`
- `quit` / `退出`

The current `--voice-demo` uses Phase 3 Plan B:

- press `Enter` to trigger one listening turn
- in `--asr typed` mode, type a simulated spoken command at the listening prompt
- in `--asr openai` mode, speak once and let the recorder stop on silence
- `:skip` continues reading without issuing a command
- `:quit` exits the voice demo

The typed backend is still useful for validating the trigger -> transcript -> command -> runtime loop without involving the microphone.

You can also switch `--voice-demo` to `--asr openai` to record one microphone turn and transcribe it with `gpt-4o-mini-transcribe`. The OpenAI path now records until a short silence is detected, up to the configured maximum turn length. This is still explicit-trigger mode, not the later automatic listening-window design.
For short command turns, `--command-language zh` or `--command-language en` can improve recognition stability by narrowing the language space. `auto` keeps language detection open.

Useful tuning flags for the microphone path:

- `--voice-listen-seconds 6`
  - maximum recording length for one command turn
- `--voice-silence-seconds 0.8`
  - how long the system waits for silence before stopping
- `--voice-energy-threshold 0.005`
  - speech activity threshold for start/end detection

## Voice Demo Notes

Current Phase 3 voice behavior is intentionally narrow:

- If an utterance matches a known control command, it is executed immediately.
- Any other non-empty utterance is treated as a future review/rewrite request.
- Review/rewrite handling is not implemented yet, so the system reports:
  - `detected_request`
  - `review_mode_not_implemented_yet`

That means Phase 3 is for spoken reading control, not spoken rewriting.

## Voice Demo Troubleshooting

If microphone mode returns `no speech detected`:

- Start with Chinese or English explicitly:
  - `--command-language zh`
  - `--command-language en`
- Use a full short command first:
  - `下一句`
  - `继续读`
  - `next section`
- Speak after the `[listening] recording until silence ...` line appears.
- Lower the speech threshold if your microphone is quiet:
  - `--voice-energy-threshold 0.005`
  - if needed, try `0.002`
- Increase the maximum turn length if you pause before speaking:
  - `--voice-listen-seconds 8`

If you want to validate the control loop without microphone variables, use:

```bash
make run ARGS="review examples/research_article_sample.md --voice-demo --tts none --asr typed"
```

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
- bilingual command normalization
- explicit trigger turn control
- typed ASR command capture
- pause-based microphone turn ending
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

- explicit-trigger ASR command capture as the first Phase 3 voice demo
- spoken pause/resume/repeat/jump commands
- later iteration toward automatic listening windows after each reading unit
- real microphone-backed ASR for command turns
- review-mode transitions
- rewrite candidate generation
- local patch application and resume-after-edit
