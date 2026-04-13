# Legacy Notes

This directory documents the older project direction that remains in the
repository for reference but is no longer the main surface of this branch.

## What Is Legacy Here

The previous focus of this repository was a manuscript-review and ASR workflow
under `src/realtime_asr/`.

That code is still present, including:

- document parsing and reading-flow code
- manuscript review and rewrite flow
- microphone and ASR experiments
- the old CLI entrypoint

## Where It Lives

- [`src/realtime_asr/`](../src/realtime_asr/)
- legacy tests in [`tests/`](../tests/)

## Legacy Entry Point

If you explicitly need the old CLI on this branch, use:

```bash
make legacy-run
```

That expands to:

```bash
PYTHONPATH=src python -m realtime_asr.cli
```

## Why It Is Still Here

The code is kept so old experiments, tests, and implementation history are not
lost while the branch now treats `codex-speak` as the primary project.
