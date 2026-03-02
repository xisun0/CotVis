# AGENTS.md

## Purpose
This file explains how contributors should work in this repo.
It is written for beginners and focuses on practical rules.

## Start Here (Beginner Flow)
1. Read `README.md` to understand what the app does and how to run it.
2. Pick one small task from the current GitHub issue.
3. Make small, focused code changes.
4. Run a quick check (at minimum: code compiles, CLI starts).
5. Commit with a clear message.
6. Link the commit to the issue with `Refs #<issue_number>`.

## Commit Convention
Use this format:

`<type>(<scope>): <short summary>`

Types:

- `feat`: new user-facing capability
- `fix`: bug fix
- `docs`: documentation-only changes
- `refactor`: internal code restructuring without behavior change
- `chore`: maintenance tasks
- `test`: tests added/updated

Scopes used in this project:

- `build`: packaging/dependencies/tooling setup
- `cli`: command entrypoint, flags, terminal output behavior
- `asr`: speech backend integration (macOS Speech Framework)
- `context`: buffering, tokenization, top-terms computation
- `lm`: language model scoring and local LLM reranking
- `web`: HTTP server and word cloud UI
- `docs`: README/spec/troubleshooting docs
- `infra`: local workflow files (e.g., Makefile)
- `scaffold`: initial project structure/bootstrap

Examples:

- `feat(asr): stream partial and final transcripts from macOS Speech`
- `feat(cli): add --no-jsonl switch for terminal output`
- `fix(context): prevent duplicate counting when final arrives`
- `docs(docs): add microphone permission troubleshooting`

For partial progress on an issue, add this line in commit body:

`Refs #1`

## Repo Boundaries
- Keep `README.md` user-facing (setup/run/usage).
- Keep contributor policy in `AGENTS.md`.
- Do not introduce cloud ASR dependencies in MVP.

## Keep Changes Small
- One commit should do one clear thing.
- Avoid mixing refactor + new feature in one commit.
- If unsure, choose simpler implementation first and leave a TODO.
