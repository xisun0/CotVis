# Codex SDK Bridge Demo

This experiment lets Python trigger a minimal Codex SDK interaction through a
thin Node.js runner.

Current structure:

- `bridge.py`: Python wrapper used by this repo
- `runner.mjs`: Node.js entrypoint that calls `@openai/codex-sdk`
- `interactive_runner.mjs`: long-lived Node.js session for true multi-turn chat
- `package.json`: local SDK dependency for the experiment only

Install the local SDK dependency:

```bash
cd betalab/codexapp_server_bridge
npm install
```

Run the Python-side demo:

```bash
python betalab/codexapp_server_bridge/bridge.py
```

What it does now:

- Python sends a plain prompt, or a list of prompts, to the Node runner over stdin.
- The Node runner starts a Codex SDK thread.
- The runner sends one or more prompts on that same thread.
- The result is returned as JSON to Python.
- For true interactive multi-turn flow, Python can keep one Node process alive and
  call `ask(...)` repeatedly on the same thread.

Notes:

- This is intentionally outside `src/realtime_asr`.
- `run_codex_sdk(prompt)` is the smallest single-turn API.
- `run_codex_sdk_multi(prompts)` shows how multi-turn dialogue works:
  it reuses one thread and calls `thread.run(...)` repeatedly.
- `CodexBridgeSession` shows the real usage pattern:
  `start()` once, then `ask(...)` after each visible response, then `close()`.
- `CodexBridgeSession.ask_stream(...)` yields text chunks early, which improves
  perceived latency compared with waiting for the final response.
- The demo thread defaults to `modelReasoningEffort="low"` and disables web
  search to reduce avoidable turn overhead for rewrite-style requests.
- `CodexCliSession` is a shorter path that calls `codex exec --json` directly
  from Python and resumes the same session id across turns.
- `CodexCliSession(..., use_pty=True)` enables a pseudo-terminal experiment. In
  local testing on 2026-04-11, PTY did not produce a material latency win over
  plain pipes for simple prompts.
- If this interface stabilizes, move the reusable adapter code into the
  formal review or LM layer later.
