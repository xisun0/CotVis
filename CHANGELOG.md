# Changelog

## codex-speak-v0.2.0

- Changed TTS playback to prefer the newest assistant turn, stopping stale audio and suppressing older speech-generation threads when a newer message is ready.

## codex-speak-v0.1.1

- Added `--session-id` for stable tracking of existing Codex sessions.
- Improved `--front-only` backend session resolution for front Terminal tabs.
- Added authorization-prompt detection and chime alerts in `Glass.aiff`.

## codex-speak-v0.1.0

- Initial release for macOS `Terminal.app`.
- Added the default launch-and-listen flow for broadcasting completed Codex replies.
- Added speech rewriting and optional TTS playback.
