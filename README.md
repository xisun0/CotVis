# CotVis Real-time ASR MVP

This repository hosts an MVP for:

`macOS Speech Framework streaming ASR -> context management -> TopTerms JSONL`

## Status

Project skeleton is initialized. `MacSpeechBackend` is currently a TODO placeholder and will be implemented next.

## Requirements

- macOS 13+
- Python 3.11+
- Microphone + Speech Recognition permissions (needed once backend is implemented)

## Setup

```bash
make setup
```

## Run

```bash
make run
```

Current behavior: CLI starts, then exits with a clear message that `MacSpeechBackend` is not implemented yet.

## Planned Package Layout

- `src/realtime_asr/events.py`: event dataclasses
- `src/realtime_asr/asr_backend/base.py`: backend interface
- `src/realtime_asr/asr_backend/mac_speech.py`: macOS streaming backend (TODO)
- `src/realtime_asr/context/tokenizer.py`: tokenization + stopwords
- `src/realtime_asr/context/manager.py`: stable/ephemeral context and TopTerms
- `src/realtime_asr/cli.py`: runtime entrypoint
