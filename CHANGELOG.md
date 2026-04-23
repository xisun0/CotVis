# Changelog

## codex-speak-v0.1.1

- Added `--session-id` for stable tracking of existing Codex sessions.
- Fixed explicit session binding so saved terminal bindings do not override it.
- Improved `--front-only` backend session resolution for front Terminal tabs.
- Documented existing-session tracking in the main README.

## codex-speak-v0.1.0

- Initial release for macOS `Terminal.app`.
- Added the default launch-and-listen flow for broadcasting completed Codex replies.
- Added backend session-log binding for launched Codex terminals.
- Added `--front-only` mode for following the current front Terminal window or tab.
- Added speech rewriting and optional TTS playback.
