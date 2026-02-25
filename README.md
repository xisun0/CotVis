# CotVis Real-time ASR MVP

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

Useful switches:

- `--lang en-US` (default) or `--lang zh-CN`
- `--no-print-transcript` to hide transcript logs
- `--no-jsonl` to hide top-term JSON output
- `--update-interval`, `--final-window`, `--partial-window`, `--top-k`

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

## Planned Package Layout

- `src/realtime_asr/events.py`: event dataclasses
- `src/realtime_asr/asr_backend/base.py`: backend interface
- `src/realtime_asr/asr_backend/mac_speech.py`: macOS streaming backend
- `src/realtime_asr/context/tokenizer.py`: tokenization + stopwords
- `src/realtime_asr/context/manager.py`: stable/ephemeral context and TopTerms
- `src/realtime_asr/cli.py`: runtime entrypoint
