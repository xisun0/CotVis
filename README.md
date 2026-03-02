# CotVis — Chain-of-Thought Visualization

## Ultimate Goal

When a person speaks, their ideas do not arrive all at once — they unfold, shift, and build on each other over time. CotVis makes that process visible to an audience in real time.

The ultimate goal is a **standalone tool that visualizes the live chain of thought of a human speaker** — not just which topics are present, but how concepts emerge, gain weight, fade, and connect as the talk or conversation progresses. An audience watching the visualization should be able to follow the arc of the speaker's thinking without reading a transcript.

This goes beyond a static word cloud. The envisioned end state is a display that communicates:

- **What** the speaker is currently focused on
- **How** the focus has shifted since they began
- **Which concepts are rising or fading** in the current flow of speech

## Roadmap

| Phase | Focus | Delivers |
|---|---|---|
| **1 — Signal correctness** | Fix stable-text diff logic; add deterministic replay tests | Trustworthy term weights as foundation for everything above |
| **2 — Concept state model** | Introduce per-term history: score, velocity, age, source | Backend knows whether each concept is new, rising, stable, or fading |
| **3 — Concept quality** | Move beyond word frequency: phrase chunking, named entities | The right concepts are tracked, not just the most frequent words |
| **4 — Shift & connection detection** | Co-occurrence graph; structured events (`focus_changed`, `concept_rising`, `concept_fading`) | Backend emits semantic events the UI can act on directly |
| **5 — Flow visualization** | 3-panel UI: current focus + trend timeline + concept-link graph; push transport (SSE/WebSocket) | Audience can see *what*, *how*, and *which* concepts are moving |
| **6 — Evaluation & hardening** | Replay benchmark set; measurable targets for latency, trend stability, false shift rate | Demonstrated, reliable quality ahead of live use |

Productization (config profiles, export, cross-platform backend) is deferred until after Phase 6.

## Current Stage (MVP)

This repository hosts an MVP for:

`macOS Speech Framework streaming ASR -> context management -> TopTerms JSONL`

## Requirements

- macOS 13+
- Python 3.11+
- Microphone + Speech Recognition permissions

## Setup

```bash
make setup
```

Optional beginner-friendly git setup:

```bash
make setup-local
```

This configures a commit message template (`.gitmessage.txt`) for this repo.
You can also print commit examples with:

```bash
make commit-help
```

## Run

```bash
make run
```

Default CLI behavior:

- prints transcript updates (`[PARTIAL] ...` / `[FINAL] ...`)
- prints one TopTerms JSON line every 2 seconds
- term ranking uses a local LM-style scorer to downweight generic words and surface more meaningful topic terms

Useful switches:

- `--lang en-US` (default) or `--lang zh-CN`
- `--no-print-transcript` to hide transcript logs
- `--no-jsonl` to hide top-term JSON output
- `--update-interval`, `--final-window`, `--partial-window`, `--top-k`
- `--full-session` to keep all FINAL transcript from the whole session (no 60s pruning)

## Optional Local LLM Reranking

You can enable a local instruct model (GGUF) to refine topic terms:

```bash
pip install -e ".[llm]"
make run-web PYTHON=python3.11 ARGS="--llm-model /path/to/model.gguf --open-browser"
```

Recommended small models:

- Qwen2.5-3B-Instruct (GGUF)
- Llama-3.2-3B-Instruct (GGUF)

Useful controls:

- `--llm-interval` (default 12s): how often to query local LLM
- `--llm-weight` (default 2.0): blend strength of LLM suggestions
- `--llm-top-k` (default 30): max LLM terms
- `--llm-ctx` (default 2048): context size for llama.cpp

Optional local path management (`.env.local`, untracked):

```bash
cat > .env.local <<'EOF'
LLM_MODEL_PATH=/path/to/model.gguf
EOF
set -a; source .env.local; set +a
make test-nlp PYTHON=python3.11 ARGS="--llm-model $LLM_MODEL_PATH --llm-primary --open-browser"
```
- `--llm-max-tokens` (default 420): max tokens in LLM response
- `--llm-primary` / `--no-llm-primary` (default on): when enabled, LLM scores replace rather than augment the frequency-based ranking

## Run With Live Word Cloud

```bash
make run-web
```

One-command demo (start server + open browser + play sample audio + stop):

```bash
make demo PYTHON=python3.11
```

Note: this still uses microphone input. Keep speaker volume audible so the mic can capture playback.

By default this starts a local UI server at:

`http://127.0.0.1:8765`

UI review pages:

- Active page: `http://127.0.0.1:8765/wordcloud.html`
- Baseline snapshot: `http://127.0.0.1:8765/wordcloud_v1_baseline.html`
- Refined snapshot: `http://127.0.0.1:8765/wordcloud_v2_refined.html`
- Final snapshot: `http://127.0.0.1:8765/wordcloud_v3_final.html`

Optional examples:

- Chinese ASR + web UI:
  - `make run-web PYTHON=python3.11 ARGS="--lang zh-CN"`
- Custom UI port:
  - `make run-web PYTHON=python3.11 ARGS="--ui-port 8877"`
- Auto-open browser:
  - `make run-web PYTHON=python3.11 ARGS="--open-browser"`

## Regenerate Local Sample Audio

Sample text is stored in:

`examples/sample_script.txt`

Regenerate WAV test audio anytime:

```bash
make sample-wav
```

This creates `examples/sample.wav` locally (not committed).

## Two-Part Testing

Deterministic local regression tests:

```bash
make test PYTHON=python3.11
```

1) Demo / ASR smoke test (starts server, plays sample audio via mic loopback, prints output):

```bash
make test-asr PYTHON=python3.11
```

2) Transcript-understanding test (simulated live stream from text):

```bash
make test-nlp PYTHON=python3.11
```

This second mode replays `examples/sample_script.txt` as a live transcript stream
(`PARTIAL` + `FINAL`) and updates the same term pipeline/UI, without microphone dependency.

## Quick Validation

1. Run `make run`.
2. If prompted, allow:
   - Speech Recognition
   - Microphone
3. Speak continuously for ~20 seconds.
4. Confirm terminal shows:
   - transcript lines marked `PARTIAL` and `FINAL`
   - JSON output every 2 seconds with changing `terms`
5. Press `Ctrl+C` to stop.

For web mode validation:

1. Run `make run-web`.
2. Open the printed URL in browser.
3. Speak and confirm words resize/reflow every ~2 seconds without manual refresh.

## macOS Permission Path

If permission prompts were dismissed or denied, enable manually:

- `System Settings -> Privacy & Security -> Microphone`
- `System Settings -> Privacy & Security -> Speech Recognition`

Then re-run `make run`.

## Troubleshooting

`Failed to start backend: Speech recognition permission is not granted`
- Enable Speech Recognition permission in system settings and retry.

`Failed to start backend: Microphone permission is not granted`
- Enable Microphone permission in system settings and retry.

`Failed to start backend: Speech recognizer is currently unavailable`
- Check internet connectivity and macOS speech availability, then retry.

`Failed to start backend: No audio input device found`
- Connect/enable a microphone and verify system input device settings.

## Package Layout

- `src/realtime_asr/events.py` — `TranscriptEvent` and `TopTermsEvent` dataclasses
- `src/realtime_asr/cli.py` — main entrypoint and run loop
- `src/realtime_asr/simulate_transcript.py` — mic-free simulation mode from a text file
- `src/realtime_asr/asr_backend/base.py` — backend interface
- `src/realtime_asr/asr_backend/mac_speech.py` — macOS Speech Framework streaming backend
- `src/realtime_asr/context/tokenizer.py` — tokenization and stopwords (EN + ZH)
- `src/realtime_asr/context/manager.py` — rolling context window and TopTerms computation
- `src/realtime_asr/lm/scorer.py` — Zipf-frequency downweighting and bigram phrase scoring
- `src/realtime_asr/lm/llm_reranker.py` — optional local GGUF model reranking
- `src/realtime_asr/web/server.py` — HTTP server serving `/terms` JSON and static UI
- `src/realtime_asr/web/static/` — word cloud HTML pages
