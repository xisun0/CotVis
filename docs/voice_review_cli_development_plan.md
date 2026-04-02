# Voice Review CLI Development Plan

## Goal

Rebuild this repository around a single product:

`voice-first manuscript review CLI for Markdown documents`

The first supported workflow is:

1. User opens a Markdown document for review.
2. The CLI reads aloud from the start, from a paragraph number, or from a text match.
3. The user interrupts by voice to stop at a problematic sentence or paragraph.
4. The system diagnoses the issue, proposes candidate rewrites, and waits for spoken confirmation.
5. The chosen rewrite is applied to the document model.
6. The CLI resumes reading from the edited location.

The MVP is deliberately narrow. It is not a general coding agent, not a web app, and not a document editor replacement.

## Product Boundaries

### In Scope for MVP

- Local CLI runtime
- Markdown document loading
- Paragraph and sentence segmentation
- Reading-position tracking
- TTS readout of the current sentence or paragraph
- Voice interruption and short spoken commands
- Review and rewrite of the current sentence or paragraph
- Confirm-before-apply editing flow
- Export of an edited Markdown file

### Out of Scope for MVP

- LaTeX support
- DOCX round-trip preservation
- Web UI
- Continuous always-on voice mode
- Wake word detection
- Autonomous proactive stopping in the middle of a sentence
- Multi-document sessions
- Collaborative editing
- Full coding-agent integration

## User Experience Target

The target user is away from the keyboard and wants to review prose while walking or doing chores.

Typical session:

1. User runs `voice-review review draft.md`.
2. CLI confirms document and starting point.
3. TTS reads sentence by sentence.
4. User says `stop`, `this sentence is awkward`, or `read that again`.
5. CLI pauses reading and enters review mode.
6. CLI explains the issue briefly and proposes 2-3 rewrites.
7. User says `use version two`, `make it shorter`, or `keep the meaning`.
8. CLI applies the accepted patch.
9. Reading resumes from the current location.

## Architecture Overview

The product should be built as an independent CLI with a modular runtime.

### Core Modules

1. `runtime/`
   - Session orchestration
   - State machine
   - Progress persistence

2. `document/`
   - Markdown loading
   - Structural parsing
   - Paragraph and sentence indexing
   - Position lookup

3. `voice/`
   - ASR adapter
   - TTS adapter
   - Turn controller
   - Interrupt handling

4. `review/`
   - Problem diagnosis
   - Rewrite generation
   - Constraint handling
   - Candidate ranking

5. `patch/`
   - Target selection
   - Safe text replacement
   - Edit history
   - Export

6. `cli/`
   - Entrypoint
   - Terminal display
   - Command parsing
   - Session summaries

### Runtime States

- `idle`
- `loading_document`
- `locating_start`
- `reading`
- `paused`
- `reviewing`
- `awaiting_decision`
- `applying_patch`
- `resuming`
- `completed`

## Proposed Repository Shape

```text
src/realtime_asr/
  __init__.py
  cli.py
  events.py
  util/
    __init__.py
    time.py
  runtime/
    __init__.py
    session.py
    state_machine.py
  document/
    __init__.py
    loader.py
    markdown.py
    locator.py
    models.py
  voice/
    __init__.py
    asr.py
    tts.py
    turn_control.py
  review/
    __init__.py
    analyze.py
    rewrite.py
    constraints.py
  patching/
    __init__.py
    planner.py
    applier.py
    exporter.py
tests/
  test_markdown_loader.py
  test_locator.py
  test_state_machine.py
  test_patch_applier.py
  test_review_constraints.py
```

## Model and Service Strategy

### MVP Default

- ASR: hosted transcription model
- Review and rewrite: hosted text model
- TTS: system TTS first, hosted TTS optional later

### Design Rule

All model-backed behavior must sit behind adapters so the runtime does not depend on one provider.

Interfaces to define early:

- `SpeechToText.transcribe_turn(audio_chunk) -> str`
- `TextToSpeech.speak(text, interruptible=True) -> None`
- `ReviewBackend.diagnose(text, context) -> Diagnosis`
- `ReviewBackend.rewrite(text, instruction, context) -> list[Candidate]`

## Implementation Phases

### Phase 0: Reset and Skeleton

Goal:
- Remove old ASR visualization code
- Preserve package root and repo metadata
- Introduce a fresh module layout

Deliverables:
- Clean package skeleton
- This development plan
- Minimal placeholder CLI entrypoint

### Phase 1: Markdown Document Pipeline

Goal:
- Make Markdown the first-class source format

Tasks:
- Implement Markdown loader
- Normalize line endings
- Segment paragraphs
- Segment sentences conservatively
- Assign stable paragraph and sentence IDs
- Support:
  - start from beginning
  - start from paragraph number
  - start from text match

Definition of done:
- Tests cover parsing and locating
- CLI can print the current paragraph/sentence target without voice

### Phase 2: Reading Runtime

Goal:
- Build the reading loop before review logic

Tasks:
- Add session state machine
- Track reading position
- Add TTS adapter
- Support commands:
  - pause
  - resume
  - repeat previous sentence
  - skip next sentence

Definition of done:
- CLI can read a Markdown file linearly
- Position remains correct across pause/resume/repeat

### Phase 3: Voice Command Loop

Goal:
- Replace keyboard controls with spoken commands

Tasks:
- Add ASR adapter for short command turns
- Add turn controller
- Add interrupt path from voice input into reading runtime
- Map spoken commands to structured intents

Supported intents:
- `stop`
- `continue`
- `repeat`
- `this sentence has a problem`
- `review this paragraph`

Definition of done:
- User can interrupt reading and issue basic spoken control commands

### Phase 4: Review and Rewrite Loop

Goal:
- Make the paused state useful

Tasks:
- Implement diagnosis prompt
- Implement rewrite prompt
- Generate 2-3 candidate rewrites
- Add spoken refinement commands:
  - `shorter`
  - `more formal`
  - `keep the meaning`
  - `less repetitive`
- Add decision commands:
  - `use version one`
  - `use version two`
  - `discard`

Definition of done:
- User can revise the current sentence or paragraph fully by voice

### Phase 5: Safe Patch Application

Goal:
- Apply edits deterministically

Tasks:
- Build text replacement planner
- Replace only the targeted sentence or paragraph
- Track applied patches
- Export edited Markdown

Definition of done:
- Applied rewrite updates the document model and resumed reading uses the new text

### Phase 6: CLI Hardening

Goal:
- Make the system stable enough for repeated real use

Tasks:
- Improve terminal state display
- Add structured logs
- Add session save/resume
- Add failure recovery for ASR/TTS/model errors
- Add prompt regression fixtures

Definition of done:
- A 20-30 minute review session can finish without losing position or corrupting edits

## First-Week Execution Plan

### Day 1

- Rewrite repo README direction later; for now define the new package layout
- Add module skeletons
- Add tests for Markdown paragraph and sentence segmentation

### Day 2

- Implement document models and locator
- Support start position selection

### Day 3

- Implement reading state machine
- Add initial system TTS adapter

### Day 4

- Add manual terminal pause/resume/repeat control
- Verify reading loop before ASR integration

### Day 5

- Add ASR command loop for short spoken turns
- Add interrupt handling

### Day 6

- Implement review backend adapters and candidate generation
- Add terminal display for candidates

### Day 7

- Implement patch apply/export
- Run an end-to-end Markdown review session

## Risks

1. ASR accuracy on very short commands may be weaker than expected.
2. Sentence segmentation in Markdown can fail on abbreviations, lists, and headings.
3. Rewrite application can drift if sentence identity is not preserved carefully.
4. TTS interruption timing may feel sluggish if playback control is too coarse.
5. Long sessions may accumulate state inconsistencies unless position updates are centralized.

## Risk Mitigations

1. Keep command vocabulary small in MVP.
2. Prefer paragraph-level fallbacks when sentence targeting is ambiguous.
3. Use stable IDs and source spans instead of fuzzy replacement when possible.
4. Start with sentence-level playback instead of long paragraph playback.
5. Store all position changes through one session-state object.

## Immediate Next Steps

1. Replace old CLI entrypoint with a minimal command surface for document review.
2. Add new `document/` and `runtime/` packages.
3. Write tests for Markdown loading and location.
4. Stub TTS and ASR adapters behind interfaces.
5. Add a non-voice dry-run mode so the workflow can be tested before speech is integrated.
