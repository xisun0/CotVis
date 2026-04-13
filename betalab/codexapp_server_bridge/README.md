# Codex Speak Implementation Notes

This directory now serves two roles:

- the current implementation backend for the repo's main `codex-speak` flow
- a holding area for related Codex bridge, SDK, and PTY experiments

The primary user-facing entrypoint for this branch is documented in the root
[`README.md`](../../README.md). This file focuses on the implementation details
inside the broadcast pipeline and the surrounding lab code.

## Current Goal

Turn raw Codex terminal output into a speech-ready broadcast flow:

1. launch a real Codex Terminal.app session
2. bind to that exact terminal tab instead of following the front window
3. extract assistant reply text from terminal snapshots
4. buffer small increments before flush
5. rewrite buffered chunks into short Chinese TTS-ready speech
6. optionally synthesize audio with OpenAI TTS

## Files

- `bridge.py`
  - Python experiments for Codex SDK, direct CLI session reuse, and PTY timing checks
- `runner.mjs`
  - one-shot Node.js runner for `@openai/codex-sdk`
- `interactive_runner.mjs`
  - long-lived Node.js session for true multi-turn SDK chat
- `launch_terminal_codex.py`
  - opens Terminal.app, starts Codex, and returns the launched tab target
- `terminal_broadcast_manager.py`
  - binds to one Terminal tab, polls terminal contents, buffers reply increments,
    rewrites speech-ready text, and can pass the result to OpenAI TTS
- `pexpect_cli_driver.py`
  - separate PTY experiment for driving the interactive Codex CLI directly
- `package.json`
  - local Node dependency for the SDK experiments only

## Dependencies

Python side:

- Python 3.11+
- `openai` Python package
- valid `OPENAI_API_KEY` for speech-rewrite and TTS steps

Node side:

- `node`
- `npm install` inside this directory for the SDK runner files

macOS side:

- `Terminal.app`
- `osascript`
- `afplay`

Install the local SDK dependency when you want the Node bridge experiments:

```bash
cd betalab/codexapp_server_bridge
npm install
```

Install the editable Python package once if you want to call the broadcast command
from any working directory. This command must be run from the repository root,
because `.` means "install the current directory as a Python project".

Then run:

```bash
python3.11 -m pip install -e .
```

After that, you can run:

```bash
codex-speak --help
```

Bare `codex-speak` now defaults to:

- `--launch-codex`
- `--max-seconds 0`
- `--speak`

Use `--no-launch-codex` or `--no-speak` when you want to override those defaults.

## Recommended Entry Points

### 1. Direct bridge experiments

Run the Python bridge demo:

```bash
python betalab/codexapp_server_bridge/bridge.py
```

This covers:

- one-shot SDK calls
- multi-turn SDK calls
- direct `codex exec --json` session reuse
- PTY versus pipe timing experiments

### 2. Launch a real Codex terminal

```bash
python betalab/codexapp_server_bridge/launch_terminal_codex.py
```

Or start with an initial prompt:

```bash
python betalab/codexapp_server_bridge/launch_terminal_codex.py \
  "请把这句话改得更学术一些：你好，我是小气。"
```

### 3. Listen and inspect speech chunks

Recommended first run:

```bash
codex-speak \
  --launch-codex \
  --initial-prompt "请把这句话改得更学术一些：你好，我是小气。" \
  --max-seconds 0 \
  --silent-debug \
  --verbose
```

This prints:

- `[user_input]`
  - the latest user turn detected from the bound Codex session
- `[reply]`
  - the completed assistant reply chosen for broadcast
- `[update]`
  - the same reply text with a timestamped flush marker
- `[spoken]`
  - the `gpt-4o-mini` rewrite intended for speech

### 4. Enable TTS playback

```bash
codex-speak \
  --launch-codex \
  --initial-prompt "请把这句话改得更学术一些：你好，我是小气。" \
  --max-seconds 0 \
  --speak \
  --verbose
```

Current TTS path:

- rewrite model: `gpt-4o-mini`
- speech model: `gpt-4o-mini-tts`
- local playback: `afplay`

## Approximate API Cost

These estimates cover only the extra broadcast pipeline in this directory:

- the `gpt-4o-mini` speech rewrite
- the optional `gpt-4o-mini-tts` speech generation

They do not include the separate cost of the main Codex conversation itself.

Current rough assumptions:

- the rewrite call uses about `1,000` input tokens and `80` output tokens per turn
- a spoken turn is usually about `5` to `20` seconds long
- pricing is based on the current OpenAI docs for:
  - `gpt-4o-mini`: `$0.15 / 1M` input tokens and `$0.60 / 1M` output tokens
  - `gpt-4o-mini-tts`: `$0.60 / 1M` text input tokens and `$12.00 / 1M` audio output tokens

Practical estimates:

- `--silent-debug`
  - no audio generation
  - about `$0.0002` per turn
  - about `$0.02` for `100` turns
- `--speak`
  - includes rewrite plus TTS audio
  - about `$0.0026` to `$0.0098` per turn
  - about `$0.26` to `$0.98` for `100` turns

These are only ballpark numbers. Long spoken summaries, very verbose replies, or future
pricing changes will move the total.

## Current Behavior Notes

- The broadcast manager uses polling, not a true event stream.
- Default polling is controlled by `--poll-seconds`.
- Bound listening is the default when `--launch-codex` is used.
- Once a Terminal tab is bound to a Codex session, completed replies are read from the
  backend session log instead of only from terminal snapshots.
- `--front-only` disables tab binding and follows the current front Terminal window instead.
- Reply increments are buffered before flush; the manager no longer speaks every tiny terminal delta immediately.
- The speech rewrite stage is model-based and should be reviewed before relying on it for production TTS.

## Known Limitations

- Terminal polling is still snapshot-based, so it is not as clean as a native event stream.
- Startup shell warnings and Codex UI formatting are filtered heuristically.
- The PTY experiment is informative but not a stable integration path.
- The speech rewrite may still over-compress or keep too much process detail for some outputs.

## Suggested Next Step

If this prototype continues to work, the next cleanup would be to separate:

- terminal extraction
- speech buffering
- speech rewrite
- final TTS playback

into smaller modules before any migration into `src/`.
