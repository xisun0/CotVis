# Investigate Bluetooth headset microphone stability for spoken command capture

## Context

Phase 3 voice control is now usable with the built-in `MacBook Pro Microphone`, but Bluetooth headset microphones still produce unstable behavior during explicit-trigger command capture.

Current observations:

- `MacBook Pro Microphone` gives acceptable command recognition quality.
- `HUAWEI FreeBuds Pro 4` as the default input device is noticeably less stable.
- Lowering `voice_energy_threshold` improves detection but hurts recognition accuracy.
- Earlier iterations also showed PortAudio / AUHAL warnings and overflow-like behavior.
- The current Phase 3 path is good enough to continue if we temporarily treat the built-in microphone as the default supported baseline.

## Why This Is Deferred

This issue is not blocking the current Phase 3 milestone.

The current goal is to keep spoken control moving forward with a known-good microphone path, then return later to harden the Bluetooth / headset microphone experience.

## Suggested Follow-up Work

- Add `--input-device` support so the CLI does not depend on the system default microphone.
- Add microphone diagnostics:
  - active input device name
  - turn energy / threshold visibility
  - speech-start / silence-stop debug signals
- Improve turn detection beyond a single energy threshold:
  - min speech duration
  - pre-roll
  - separate start / stop thresholds
- Evaluate a stronger VAD approach instead of only RMS thresholding.
- Re-test with Bluetooth headset microphones after input-device selection is explicit.

## Current Baseline

For now, treat this as the supported Phase 3 workflow:

- use `MacBook Pro Microphone`
- keep explicit-trigger `voice-demo`
- keep spoken control scope narrow

This issue should be revisited before claiming robust headset-first voice interaction.
