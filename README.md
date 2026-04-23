# codex-speak

`codex-speak` is a terminal-side companion for Codex on macOS.

It launches or follows a real `Terminal.app` Codex session, binds that tab to
the matching backend session log, extracts the completed assistant reply, and
turns it into speech-ready output. It can either print the broadcast text or
play it with OpenAI TTS.

## Demo

`codex-speak` launches a Codex terminal, captures the completed assistant reply,
and broadcasts it as text or speech.

https://github.com/user-attachments/assets/b707f7b3-f938-4ef6-8ea7-bf1d791d1d66

## Requirements

- macOS
- Python 3.11+
- `Terminal.app`, `osascript`, and `afplay`
- `OPENAI_API_KEY`

## Setup

### Step 1. Clone the repository

```bash
git clone https://github.com/xisun0/CotVis.git
```

### Step 2. Install the package

```bash
cd CotVis
python3.11 -m pip install -e .
```

The `.` in the install command means "install the project in the current
directory", so this step must be run from the repository root.

This does two things:

- installs the dependencies declared by this repo
- registers `codex-speak` as a local command that points at this working tree

After the install finishes, `codex-speak` can be run from any directory.

### Step 3. Verify the command

```bash
codex-speak --help
```

## Quick Start

After setup, the shortest path is simply:

```bash
codex-speak
```

The default bare command now does all of the following:

- launch a new Codex terminal
- keep listening until you stop it
- enable spoken playback

If you want to seed the first turn immediately:

```bash
codex-speak --initial-prompt "请把这句话改得更学术一些：你好，我是小气。"
```

If you want text only without audio playback:

```bash
codex-speak --no-speak --silent-debug
```

If you want to follow the current front terminal instead of launching a new one:

```bash
codex-speak --front-only --no-launch-codex --silent-debug
```

If you want to follow an existing Codex session more reliably, bind to its
backend session ID directly:

```bash
codex-speak --no-launch-codex --session-id <session-id>
```

If you want to launch Codex in a specific directory:

```bash
codex-speak --working-directory /path/to/project
```

## Existing Sessions

There are two ways to follow an existing Codex conversation:

- `--front-only`: follow the current front `Terminal.app` window or tab
- `--session-id`: pin `codex-speak` to a specific backend Codex session

Use `--session-id` when you want stable tracking for an existing conversation.
This avoids relying on front-window switching or on matching the visible
terminal contents back to the correct backend session.

If you pass both flags, `--session-id` takes precedence and disables dynamic
front-window following.

## Approximate Cost

These estimates cover only the extra broadcast pipeline used by `codex-speak`:

- the `gpt-4o-mini` rewrite step
- the optional `gpt-4o-mini-tts` speech generation step

They do not include the separate cost of the main Codex conversation itself.

Current rough estimates:

- text-only mode such as `codex-speak --no-speak --silent-debug`
  - about `$0.0002` per turn
  - about `$0.02` for `100` turns
- spoken mode such as bare `codex-speak`
  - about `$0.0026` to `$0.0098` per turn
  - about `$0.26` to `$0.98` for `100` turns

These are ballpark numbers. Longer replies, longer spoken output, and future
OpenAI pricing changes will move the total.

## Testing

Run the focused broadcast-manager tests:

```bash
pytest -q tests/test_terminal_broadcast_manager.py
```

Implementation notes for the broadcast pipeline live in
[`betalab/codexapp_server_bridge/README.md`](betalab/codexapp_server_bridge/README.md).
Historical and legacy notes live in [`legacy/README.md`](legacy/README.md).

## Current Limits

- `codex-speak` currently supports macOS `Terminal.app` only
- it requires a working `OPENAI_API_KEY`
- spoken output may still be lightly rewritten for summary or editing-style replies
- the tool is best suited to normal Codex terminal replies, not every possible terminal program or screen layout
